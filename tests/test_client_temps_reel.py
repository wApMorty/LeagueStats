"""Temps réel du client LeagueStats (SPEC-21 tâche 70) : bus, flux SSE, WebSocket LCU."""

import asyncio
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from src.client import server
from src.client.app import create_app
from src.client.bus import EventBus
from src.client.lcu_events import LcuEvents, tracked
from src.config_client import client_config
from src.lcu_client import LCUCredentials

LOCAL = "http://127.0.0.1"


def wait_for(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ---------- bus ----------


def test_bus_diffuse_aux_abonnes_du_sujet():
    bus = EventBus()
    with bus.subscribe(["draft"]) as draft, bus.subscribe() as tout:
        bus.publish("draft", {"phase": "PICK"})
        bus.publish("lcu", {"uri": "/x"})
        assert draft.get(0.1) == ("draft", {"phase": "PICK"})
        assert draft.get(0.05) is None
        assert [tout.get(0.1)[0], tout.get(0.1)[0]] == ["draft", "lcu"]


def test_bus_abandonne_le_plus_ancien_quand_la_file_deborde(monkeypatch):
    monkeypatch.setattr(client_config, "BUS_QUEUE_SIZE", 3)
    bus = EventBus()
    with bus.subscribe() as sub:
        for i in range(10):
            bus.publish("t", i)  # personne ne lit : ne bloque jamais
        assert [sub.get(0.1)[1] for _ in range(3)] == [7, 8, 9]
        assert sub.get(0.05) is None


def test_bus_publier_sans_abonne_ne_fait_rien():
    EventBus().publish("t", 1)


def test_bus_publier_ne_leve_jamais_meme_si_un_abonne_casse():
    bus = EventBus()

    class Casse:
        def accepts(self, topic):
            return True

        def put(self, event):
            raise RuntimeError("abonné cassé")

    bus._subscriptions.append(Casse())
    bus.publish("t", 1)  # le monitoring de draft ne doit jamais s'arrêter ici


def test_bus_fermer_un_abonnement_le_retire():
    bus = EventBus()
    sub = bus.subscribe()
    sub.close()
    sub.close()
    assert bus._subscriptions == []


def test_bus_depuis_un_autre_fil():
    bus = EventBus()
    with bus.subscribe() as sub:
        threading.Thread(target=bus.publish, args=("t", "x")).start()
        assert sub.get(2) == ("t", "x")


# ---------- flux SSE ----------


def test_sse_sans_bus_404_et_sans_jeton_403(temp_db):
    sans_bus = TestClient(create_app(temp_db), base_url=LOCAL)
    token = {client_config.TOKEN_HEADER: sans_bus.app.state.session_token}
    assert sans_bus.get("/events").status_code == 403
    assert sans_bus.get("/events", headers=token).status_code == 404
    avec_bus = TestClient(create_app(temp_db, bus=EventBus()), base_url=LOCAL)
    assert avec_bus.get("/events").status_code == 403


@pytest.fixture
def live(temp_db):
    bus = EventBus()
    url = server.start(temp_db, bus=bus)
    token = {client_config.TOKEN_HEADER: server._server.config.app.state.session_token}
    yield bus, url, token
    server.stop()


def read_sse(url, token, query, publish, wanted: int):
    """Se connecte au flux, publie en boucle tant que rien n'est reçu, rend `wanted` messages."""
    got, stop = [], threading.Event()

    def pump():
        while not stop.is_set():
            publish()
            time.sleep(0.05)

    threading.Thread(target=pump, daemon=True).start()
    try:
        with httpx.stream("GET", f"{url}/events{query}", headers=token, timeout=10) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            event = {}
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event["event"] = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    event["data"] = json.loads(line.split(":", 1)[1])
                elif line == "" and event:
                    got.append(event)
                    event = {}
                    if len(got) >= wanted:
                        break
    finally:
        stop.set()
    return got


def test_sse_relaie_le_bus(live):
    bus, url, token = live
    got = read_sse(url, token, "", lambda: bus.publish("draft", {"phase": "BAN"}), 1)
    assert got == [{"event": "draft", "data": {"phase": "BAN"}}]


def test_sse_filtre_par_sujet(live):
    bus, url, token = live

    def publish():
        bus.publish("lcu", {"uri": "/bruit"})
        bus.publish("draft", {"phase": "PICK"})

    got = read_sse(url, token, "?topic=draft", publish, 2)
    assert {e["event"] for e in got} == {"draft"}


def test_sse_libere_l_abonnement_a_la_deconnexion(live):
    bus, url, token = live
    read_sse(url, token, "", lambda: bus.publish("t", 1), 1)
    assert wait_for(lambda: bus._subscriptions == [], timeout=5)


def test_arret_du_serveur_avec_un_flux_ouvert(live):
    bus, url, token = live
    opened = threading.Event()

    def hold():
        try:
            with httpx.stream("GET", f"{url}/events", headers=token, timeout=15) as response:
                opened.set()
                for _ in response.iter_lines():
                    pass
        except httpx.HTTPError:
            pass

    threading.Thread(target=hold, daemon=True).start()
    assert opened.wait(5)
    started = time.monotonic()
    server.stop()
    assert time.monotonic() - started < client_config.SERVER_STOP_TIMEOUT_S


# ---------- WebSocket LCU ----------


class FakeLcuServer:
    """Faux LCU : un serveur WebSocket sans TLS qui note ce qu'il reçoit et rejoue des messages."""

    def __init__(self, to_send=(), close_after_send=False):
        self.to_send, self.close_after_send = list(to_send), close_after_send
        self.headers, self.subscribes = [], []
        self.port = None
        self._ready, self._loop, self._stop = threading.Event(), None, None
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)

    async def _handler(self, websocket):
        self.headers.append(websocket.request.headers.get("Authorization"))
        self.subscribes.append(json.loads(await websocket.recv()))
        for message in self.to_send:
            await websocket.send(message)
        if not self.close_after_send:
            await websocket.wait_closed()

    async def _main(self):
        self._loop, self._stop = asyncio.get_running_loop(), asyncio.Event()
        async with serve(self._handler, "127.0.0.1", 0) as ws_server:
            self.port = ws_server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._stop.wait()

    def __enter__(self):
        self._thread.start()
        assert self._ready.wait(5)
        return self

    def __exit__(self, *exc):
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(5)

    @property
    def credentials(self):
        return LCUCredentials(self.port, "pw", f"https://127.0.0.1:{self.port}")


def event(uri, data=None, kind="Update"):
    return json.dumps([8, "OnJsonApiEvent", {"uri": uri, "eventType": kind, "data": data}])


@pytest.fixture(autouse=True)
def _reconnexion_rapide(monkeypatch):
    monkeypatch.setattr(client_config, "LCU_WS_BACKOFF_MIN_S", 0.05)
    monkeypatch.setattr(client_config, "LCU_WS_BACKOFF_MAX_S", 0.2)


def test_prefixes_suivis():
    assert tracked("/lol-gameflow/v1/gameflow-phase") and tracked("/lol-champ-select/v1/session")
    assert not tracked("/lol-store/v1/catalog") and not tracked("")


def test_websocket_publie_les_evenements_suivis_sur_le_bus():
    messages = [
        event("/lol-gameflow/v1/gameflow-phase", "ChampSelect"),
        event("/lol-store/v1/catalog", "bruit"),  # hors des préfixes suivis
        "pas du json",
        json.dumps([5, "OnJsonApiEvent"]),  # autre type de message
        json.dumps([8, "OnJsonApiEvent", {"data": 1}]),  # sans uri
        event("/lol-lobby/v2/lobby", {"members": []}, "Create"),
    ]
    bus = EventBus()
    with bus.subscribe(["lcu"]) as sub, FakeLcuServer(messages) as fake:
        events = LcuEvents(bus, lambda: fake.credentials, scheme="ws")
        events.start()
        try:
            got = [sub.get(5), sub.get(5)]
            assert sub.get(0.2) is None
        finally:
            events.stop()
    assert got == [
        (
            "lcu",
            {
                "uri": "/lol-gameflow/v1/gameflow-phase",
                "eventType": "Update",
                "data": "ChampSelect",
            },
        ),
        ("lcu", {"uri": "/lol-lobby/v2/lobby", "eventType": "Create", "data": {"members": []}}),
    ]
    assert fake.subscribes == [[5, "OnJsonApiEvent"]]
    assert fake.headers == [fake.credentials.auth_header]


def test_websocket_se_reconnecte_apres_une_coupure(capsys):
    bus = EventBus()
    with bus.subscribe() as sub, FakeLcuServer([event("/lol-chat/v1/me")], True) as fake:
        events = LcuEvents(bus, lambda: fake.credentials, scheme="ws")
        events.start()
        try:
            assert sub.get(5) and sub.get(5)  # un événement par connexion : il y a eu reconnexion
        finally:
            events.stop()
    assert len(fake.subscribes) >= 2
    out = capsys.readouterr().out
    assert out.count("[ALERTE]") == 1  # une annonce par panne, pas une par essai
    assert "[INFO] WebSocket LCU rétabli" in out


def test_websocket_client_ferme_puis_ouvert(capsys):
    bus = EventBus()
    with bus.subscribe() as sub, FakeLcuServer([event("/lol-gameflow/v1/x")]) as fake:
        calls = []

        def credentials():
            calls.append(1)
            return fake.credentials if len(calls) > 3 else None  # client LoL fermé au début

        events = LcuEvents(bus, credentials, scheme="ws")
        events.start()
        try:
            assert sub.get(5) is not None
        finally:
            events.stop()
    out = capsys.readouterr().out
    assert out.count("[ALERTE]") == 1 and "client LoL fermé" in out
    assert len(calls) >= 4


def test_websocket_port_ferme_alerte_sans_exception(capsys):
    bus = EventBus()
    with FakeLcuServer() as fake:
        credentials = fake.credentials
    events = LcuEvents(bus, lambda: credentials, scheme="ws")  # plus personne n'écoute
    events.start()
    out = []  # Windows met ~1 s à constater un port fermé
    assert wait_for(lambda: out.append(capsys.readouterr().out) or "[ALERTE]" in "".join(out), 10)
    time.sleep(0.5)  # d'autres essais : toujours une seule annonce
    events.stop()
    assert "".join(out + [capsys.readouterr().out]).count("[ALERTE]") == 1
    assert events._thread is None


def test_websocket_identifiants_en_echec_ne_plantent_pas():
    def boom():
        raise OSError("lockfile illisible")

    events = LcuEvents(EventBus(), boom, scheme="ws")
    events.start()
    time.sleep(0.2)
    assert events._thread.is_alive()  # il réessaie au lieu de mourir
    events.stop()


def test_websocket_arret_rapide_connecte_et_idempotent():
    with FakeLcuServer() as fake:
        events = LcuEvents(EventBus(), lambda: fake.credentials, scheme="ws")
        events.start()
        events.start()  # sans effet
        assert wait_for(lambda: len(fake.subscribes) == 1)
        thread = events._thread
        started = time.monotonic()
        events.stop()
        assert time.monotonic() - started < 2
        assert not thread.is_alive()
        events.stop()  # sans effet quand rien ne tourne
