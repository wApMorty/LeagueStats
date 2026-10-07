"""Relevé d'une fin de partie réelle (SPEC-25 tâche 112), en lecture seule.

À lancer client LoL ouvert, AVANT la fin d'une partie, puis à laisser tourner jusqu'après le retour
au lobby (cliquer « Rejouer » une fois dans les 3 s, une fois après 10 s si possible) ; Ctrl+C arrête.
Plusieurs relevés horodatés dans `outputs/lcu_endgame/<AAAAMMJJ_HHMMSS>/` (ignoré par git),
identités remplacées par `anon` :

- `events.jsonl` : chaque événement WebSocket `/lol-gameflow`, `/lol-ranked`, `/lol-end-of-game`
  (URI, type, données) avec l'instant en secondes depuis le lancement ;
- `polls.jsonl` : toutes les 0,5 s, la durée et la présence d'une réponse de `eog-stats-block` et de
  `current-lp-change-notification`, plus la phase `gameflow-phase` ;
- `first_<nom>.json` : la première réponse non vide de chaque endpoint (base des fixtures) ;
- `summary.txt` : les phases vues, et pour chaque endpoint le premier et le dernier instant où il a
  répondu, pour fixer `PHASE_POLL_S` et `PHASE_POST_POLL_S`.

Lectures GET seulement. USAGE : python scripts/dump_lcu_endgame.py
"""

import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.dump_lcu_draft_forms import anonymize  # noqa: E402
from src.client.lcu_events import LcuEvents  # noqa: E402
from src.lcu_client import LCUClient  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "lcu_endgame"
POLL_INTERVAL_S = 0.5
WATCHED_URI_PREFIXES = ("/lol-gameflow", "/lol-ranked", "/lol-end-of-game")
PHASE_ENDPOINT = "/lol-gameflow/v1/gameflow-phase"
TRANSIENTS = {
    "eog_stats_block": "/lol-end-of-game/v1/eog-stats-block",
    "lp_change_notification": "/lol-ranked/v1/current-lp-change-notification",
}


class Recorder:
    """Écrit les relevés d'un dossier ; sert de bus à `LcuEvents` (seul `publish` est appelé)."""

    def __init__(self, target_dir: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.dir = target_dir
        self._clock = clock
        self._start = clock()
        self._lock = threading.Lock()
        self.phases: List[tuple] = []  # (instant, phase)
        self.seen: Dict[str, List[float]] = {name: [] for name in TRANSIENTS}
        target_dir.mkdir(parents=True, exist_ok=True)

    def _at(self) -> float:
        return round(self._clock() - self._start, 3)

    def _append(self, name: str, row: dict) -> None:
        with self._lock, (self.dir / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _note_phase(self, at: float, phase) -> None:
        with self._lock:
            if not self.phases or self.phases[-1][1] != phase:
                self.phases.append((at, phase))

    def publish(self, _topic: str, event: dict) -> None:
        """Un événement WebSocket ; seuls les préfixes de `WATCHED_URI_PREFIXES` sont gardés."""
        if not str(event.get("uri", "")).startswith(WATCHED_URI_PREFIXES):
            return
        row = {"t": self._at(), **anonymize(event, False)}
        self._append("events.jsonl", row)
        if event["uri"] == PHASE_ENDPOINT:
            self._note_phase(row["t"], event.get("data"))

    def poll_once(self, lcu: LCUClient) -> None:
        """Lit la phase et les deux endpoints transitoires, mesure leur durée de réponse."""
        at = self._at()
        row: dict = {"t": at}
        phase = lcu._make_request(PHASE_ENDPOINT)
        row["phase"] = phase
        self._note_phase(at, phase)
        for name, endpoint in TRANSIENTS.items():
            began = self._clock()
            data = lcu._make_request(endpoint)
            row[name] = {"ms": round((self._clock() - began) * 1000), "filled": bool(data)}
            if not data:
                continue
            self.seen[name].append(at)
            first = self.dir / f"first_{name}.json"
            if not first.exists():
                first.write_text(
                    json.dumps(
                        anonymize(data, False), indent=2, ensure_ascii=False, sort_keys=True
                    ),
                    encoding="utf-8",
                )
                print(f"[DATA] {at:.1f} s {endpoint} : première réponse -> {first.name}")
        self._append("polls.jsonl", row)

    def summary(self) -> str:
        """Phases vues et fenêtre de réponse de chaque endpoint transitoire."""
        lines = ["Phases vues (instant en s, phase) :"]
        lines += [f"  {at:8.1f}  {phase}" for at, phase in self.phases]
        for name, times in self.seen.items():
            span = f"{times[0]:.1f} s -> {times[-1]:.1f} s" if times else "jamais de réponse"
            lines.append(f"{TRANSIENTS[name]} : {span} ({len(times)} lectures non vides)")
        return "\n".join(lines)


def watch(
    lcu: LCUClient,
    recorder: Recorder,
    ticks: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Sondage jusqu'à Ctrl+C (ou `ticks` lectures, pour les tests)."""
    count = 0
    try:
        while ticks is None or count < ticks:
            recorder.poll_once(lcu)
            count += 1
            sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        pass


def main() -> int:
    lcu = LCUClient()
    if not lcu.connect():
        print("[ALERTE] Client LoL introuvable : ouvre-le avant la fin de ta partie et relance")
        return 1
    recorder = Recorder(OUTPUT_DIR / time.strftime("%Y%m%d_%H%M%S"))
    events = LcuEvents(recorder, LCUClient().find_lcu_credentials)  # type: ignore[arg-type]
    events.start()
    print(f"[INFO] Relevé dans {recorder.dir} : Ctrl+C après le retour au lobby")
    try:
        watch(lcu, recorder)
    finally:
        events.stop()
        (recorder.dir / "summary.txt").write_text(recorder.summary(), encoding="utf-8")
        print(recorder.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
