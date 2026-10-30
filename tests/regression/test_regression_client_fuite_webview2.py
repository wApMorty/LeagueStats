"""Régression client : la mémoire du renderer WebView2 monte tant que le client reste ouvert.

Symptôme (@pj35, 2026-10-30) : renderer du vrai client de 260 à 469 Mo en 48 min (4 à 7 Mo/min), sans
navigation, le tas JS et le DOM restant plats ; le processus pythonw ne bouge pas.

Cause racine : pywebview s'abonne sans condition à `WebResourceResponseReceived`, qui instrumente le
réseau de la page. Le renderer garde alors une trace de chaque réponse, dont le flux sans fin
`/events`. Reproduit dans Edge headless : +7,79 Mo/min avec `Network.enable`, -0,20 Mo/min sans, à
charge égale ; `Network.disable` arrête la pente et libère les nœuds retenus.

Correctif : `window._without_response_listener` retire l'abonnement avant la première navigation.
Le client n'utilise pas `events.response_received`.

Prévention : ce test joue l'initialisation avec un faux `EdgeChrome` et exige le désabonnement.
"""

import sys
import types

import pytest

from src.client import window


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class FakeEdgeChrome:
    def on_webview_ready(self, sender, args):
        if args.IsSuccess:
            sender.CoreWebView2.WebResourceResponseReceived += self.on_web_resource_response

    def on_web_resource_response(self, sender, args):
        """Écoute posée par pywebview."""


@pytest.fixture
def edge(monkeypatch):
    """`webview.platforms.edgechromium` factice : le vrai charge les assemblys de WebView2."""
    fake = types.ModuleType("webview.platforms.edgechromium")
    fake.EdgeChrome = type("EdgeChrome", (FakeEdgeChrome,), {})
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    monkeypatch.setitem(sys.modules, "webview.platforms", types.ModuleType("webview.platforms"))
    monkeypatch.setitem(sys.modules, "webview.platforms.edgechromium", fake)
    return fake.EdgeChrome


def ready(edge_class, success=True):
    event = FakeEvent()
    sender = types.SimpleNamespace(
        CoreWebView2=types.SimpleNamespace(WebResourceResponseReceived=event)
    )
    edge_class().on_webview_ready(sender, types.SimpleNamespace(IsSuccess=success))
    return event


def test_l_ecoute_des_reponses_est_retiree(edge):
    assert ready(edge).handlers  # sans le correctif, pywebview reste abonné
    window._without_response_listener()
    assert ready(edge).handlers == []


def test_retrait_idempotent_pour_le_repli_en_fenetre_standard(edge, capsys):
    window._without_response_listener()
    window._without_response_listener()
    assert ready(edge).handlers == []
    assert "[ALERTE]" not in capsys.readouterr().out


def test_echec_d_initialisation_sans_erreur(edge):
    window._without_response_listener()
    assert ready(edge, success=False).handlers == []


def test_pywebview_absent_ne_leve_pas(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview.platforms.edgechromium", None)
    window._without_response_listener()


def test_desabonnement_refuse_ne_casse_pas_l_ouverture(edge, capsys):
    class Refuse(FakeEvent):
        def __isub__(self, handler):
            raise ValueError("handler inconnu")

    window._without_response_listener()
    sender = types.SimpleNamespace(
        CoreWebView2=types.SimpleNamespace(WebResourceResponseReceived=Refuse())
    )
    edge().on_webview_ready(sender, types.SimpleNamespace(IsSuccess=True))
    assert "[ALERTE]" in capsys.readouterr().out
