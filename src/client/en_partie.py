"""Vue de l'écran « En partie » (SPEC-24 §4.9, tâches 108 à 110) : données seulement, aucun appel au LCU.

`ingame` est le dernier état du sujet `ingame` du bus (`LiveGame`), `analysis` la dernière analyse de
fin de draft (sujet `game`, `FinalAnalysis.to_payload()`). Sans analyse, l'écran dit que le Live Coach
n'a pas vu la draft de cette partie (ignorance visible) ; sans modèle, il dit comment l'entraîner.
"""

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from markupsafe import Markup

from ..config_client import client_config
from ..config_constants import draft_config
from .charts import Band, Mark, Series, Tick, line_chart
from .review import COST_COLOR, CURVE_STOPS, KIND_COLORS

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


# Famille d'objectif de la Live Client API -> clé de couleur de la page d'une partie, et libellé du repère.
MARK_KIND = {
    "dragon": "dragon",
    "herald": "herald",
    "baron": "baron",
    "turret": "tower",
    "inhibitor": "inhibitor",
}
MARK_LABEL = {
    "dragon": "Dragon",
    "herald": "Héraut",
    "baron": "Nashor",
    "turret": "Tour",
    "inhibitor": "Inhib.",
}


def _curve_at(points: Sequence[Sequence[float]], minute: float) -> float:
    """Win chance (0 à 100) de la série à `minute`, par interpolation entre deux points."""
    if minute <= points[0][0]:
        return points[0][1]
    for (m0, p0), (m1, p1) in zip(points, points[1:]):
        if m0 <= minute <= m1:
            return p0 + (p1 - p0) * ((minute - m0) / ((m1 - m0) or 1))
    return points[-1][1]


def curve_view(ingame: Dict[str, Any]) -> Dict[str, Any]:
    """La courbe de win chance en direct : le tracé (None sous deux points) et ce qu'il faut en dire."""
    series = ingame.get("series") or []
    if len(series) < 2:
        return {"chart": None, "note": "La courbe apparaît après quelques secondes de partie."}
    points = [(t / 60, p * 100) for t, p in series]
    mine = ((ingame.get("me") or {}).get("team")) or "ORDER"
    marks = []
    for objective in (ingame.get("objectives") or [])[-client_config.GAME_MARKS :]:
        minute = objective["t"] / 60
        if not points[0][0] <= minute <= points[-1][0]:
            continue  # avant le premier point : le client s'est ouvert en cours de partie
        ours = objective["team"] == mine
        kind = objective["kind"]
        marks.append(
            Mark(
                minute,
                _curve_at(points, minute),
                KIND_COLORS[MARK_KIND[kind]] if ours else COST_COLOR,
                MARK_LABEL[kind] if ours else f"{MARK_LABEL[kind]} adverse",
                above=ours,
            )
        )
    end = max(points[-1][0], 1.0)
    chart = line_chart(
        [
            Series(
                "Chance de victoire",
                points,
                stops=CURVE_STOPS,
                width=3,
                area=True,
                trace_ms=1200,
                delay_ms=200,
                end_label=f"{points[-1][1]:.0f} %",
            )
        ],
        size=client_config.GAME_CURVE_SIZE,
        margin=client_config.GAME_CURVE_MARGIN,
        x_domain=(0, end),
        y_domain=(0, 100),
        uid="enpartie",
        title="Chance de victoire en direct",
        desc=f"Probabilité de victoire de ton équipe depuis {points[0][0]:.0f} min, "
        f"{points[-1][1]:.0f} % maintenant",
        x_ticks=[
            Tick(m, f"{m} min") for m in range(0, int(end) + 1, client_config.GAME_CURVE_X_STEP_MIN)
        ],
        y_ticks=[
            Tick(0, "0 %", color="oklch(0.74 0.11 55 / 0.12)"),
            Tick(50, "50 %", color="oklch(0.74 0.11 55 / 0.45)", dash="4 5"),
            Tick(100, "100 %", color="oklch(0.74 0.11 55 / 0.12)"),
        ],
        bands=[
            Band(50, 100, "oklch(0.82 0.15 165 / 0.05)"),
            Band(0, 50, "oklch(0.72 0.21 345 / 0.06)"),
        ],
        marks=marks,
    )
    started_late = series[0][0] > client_config.INGAME_LATE_START_S
    return {
        "chart": Markup(chart),
        "note": (
            f"Courbe tracée depuis {clock(series[0][0])} : le client s'est ouvert en cours de partie, "
            "le début n'est pas tracé."
            if started_late
            else None
        ),
    }


# Blocs du plan dont les objets se visent un à un (le reste : alternatives, composants, situationnels).
NEXT_BLOCKS = ("Core", "Bottes")


def _remaining_cost(
    item_id: int, owned: Counter, items: Dict[int, Dict[str, Any]]
) -> Optional[int]:
    """Or qu'il reste à payer pour `item_id` : son coût d'assemblage plus celui des composants non possédés."""
    info = items.get(item_id)
    if info is None:
        return None
    cost = info["base"]
    for part in info["parts"]:
        if owned[part] > 0:
            owned[part] -= 1
        else:
            cost += _remaining_cost(part, owned, items) or 0
    return cost


def build_view(
    analysis: Optional[Dict[str, Any]],
    ingame: Dict[str, Any],
    items: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Plan d'objets de la draft, suivi des achats (objets possédés, prochain objet, or) et ordre des compétences.

    `items` : objets de Data Dragon (`Assets.items()`), pour les noms français et les coûts.
    """
    loadout = (analysis or {}).get("loadout")
    if not loadout:
        return {"available": False}
    items = items or {}
    names = loadout.get("item_names") or {}
    me = ingame.get("me")
    mine = None if me is None or me.get("items") is None else me["items"]
    owned: Counter = Counter()
    for item in mine or []:
        owned[item["id"]] += item.get("count") or 1

    def entry(item_id: int) -> Dict[str, Any]:
        return {
            "id": item_id,
            "name": (items.get(item_id) or {}).get("name") or names.get(str(item_id), str(item_id)),
            "img": f"/assets/item/{item_id}.png",
            "owned": owned[item_id] > 0,
        }

    blocks = [
        {"title": block["title"], "items": [entry(i) for i in block["items"]]}
        for block in loadout["item_blocks"]
        if block["items"]
    ]
    next_item = None
    if mine is not None:
        targets: List[Dict[str, Any]] = []
        for block in blocks:
            base = block["title"].split(" (")[0]
            if base == "Core":
                targets += block["items"]
            elif base == "Bottes" and not any(i["owned"] for i in block["items"]):
                targets += block["items"][:1]  # les suivantes sont des alternatives
        target = next((i for i in targets if not i["owned"]), None)
        if target is not None:
            cost = _remaining_cost(target["id"], Counter(owned), items)
            gold = (me or {}).get("gold")
            next_item = {
                **target,
                "cost": cost,
                "gold": None if gold is None else int(gold),
                "missing": None if cost is None or gold is None else max(0, cost - int(gold)),
            }
    skills = loadout.get("skills")
    return {
        "available": True,
        "label": loadout.get("label"),
        "blocks": blocks,
        "substitutions": loadout.get("substitutions") or [],
        "tracking": mine is not None,
        "next": next_item,
        "complete": mine is not None and next_item is None,
        "skills": (
            {
                "max_order": " > ".join(skills["max_order"]),
                "levels": " ".join(skills["levels"]),
                "playrate": round(skills["playrate"] * 100),
                "current": " ".join(
                    f"{key} {level}"
                    for key, level in (me or {}).get("abilities", {}).items()
                    if level
                ),
            }
            if skills
            else None
        ),
    }


def en_partie_view(
    ingame: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
    items: Optional[Dict[int, Dict[str, Any]]] = None,
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
            curve=curve_view(data),
            build=build_view(analysis, data, items),
        )
    view["analysis"] = analysis_view(analysis)
    return view
