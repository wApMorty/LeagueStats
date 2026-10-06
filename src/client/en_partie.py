"""Vue de l'écran « En partie » (SPEC-24 §4.9, tâches 108 à 110) : données seulement, aucun appel au LCU.

`ingame` est le dernier état du sujet `ingame` du bus (`LiveGame`), `analysis` la dernière analyse de
fin de draft (sujet `game`, `FinalAnalysis.to_payload()`). Sans analyse, l'écran dit que le Live Coach
n'a pas vu la draft de cette partie (ignorance visible) ; sans modèle, il dit comment l'entraîner.
"""

from typing import Any, Dict, List, Optional

from ..config_constants import draft_config

TRAIN_COMMAND = "python -m src.winprob.retrain --force"


def clock(seconds: Optional[float]) -> str:
    """Temps de jeu en m:ss."""
    total = int(seconds or 0)
    return f"{total // 60}:{total % 60:02d}"


def _points(value: Optional[float]) -> Optional[str]:
    return None if value is None else f"{value:+.1f}"


def _score(line: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Un champion du face-à-face ; `thin` quand ses données sont trop minces pour être chiffrées."""
    if line is None:
        return None
    thin = line["matchup"] is None
    return {
        "name": line["name"],
        "thin": thin,
        "matchup": None if thin else _points(line["matchup"]),
        "synergy": None if thin else _points(line["synergy"]),
        "total": None if thin else _points(line["total"]),
    }


def _duel(points: Optional[float]) -> Dict[str, Any]:
    """Le duel direct : camp avantagé et nombre de chevrons (paliers de SPEC-14)."""
    if points is None:
        return {"side": "none", "chevrons": 0, "text": "?"}
    chevrons = sum(abs(points) >= step for step in draft_config.DUEL_ARROW_THRESHOLDS)
    side = "even" if not chevrons else ("ally" if points > 0 else "enemy")
    return {"side": side, "chevrons": chevrons, "text": _points(points)}


def analysis_view(analysis: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Le face-à-face de la draft tel que `FinalAnalysis` le porte, None sans analyse."""
    if not analysis:
        return None
    rows: List[Dict[str, Any]] = [
        {"ally": _score(line["ally"]), "enemy": _score(line["enemy"]), "duel": _duel(line["duel"])}
        for line in analysis["lines"]
    ]
    return {
        "rows": rows,
        "probability": round(analysis["win_probability"] * 100, 1),
        "diff": _points(analysis["draft_diff"]),
        "evaluation": analysis["evaluation"],
    }


def en_partie_view(
    ingame: Optional[Dict[str, Any]], analysis: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """L'écran : état (`idle`, `live`, `ended`), horloge, win chance, analyse de la draft."""
    state = (ingame or {}).get("state", "idle")
    view: Dict[str, Any] = {"state": state, "train_command": TRAIN_COMMAND}
    if state != "idle":
        data = ingame or {}
        p, delta = data.get("p"), data.get("delta")
        view.update(
            clock=clock(data.get("game_time")),
            p=None if p is None else round(p * 100),
            delta=None if delta is None else round(delta * 100),
            model_missing=p is None,
            points=len(data.get("series") or []),
        )
    view["analysis"] = analysis_view(analysis)
    return view
