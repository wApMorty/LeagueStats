"""Vue de la draft : le snapshot du bus devient ce que les gabarits dessinent (SPEC-21 §4.10).

Fonctions pures, sans HTTP ni LCU : le snapshot (`dataclasses.asdict` d'un `DraftSnapshot`) et les
assets entrent, un dictionnaire prêt pour Jinja sort. Toutes les valeurs affichées viennent du
snapshot ; les positions du pentacle et les teintes sont les seules constantes (README du handoff).
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from ..config_client import client_config
from ..config_constants import scraping_config
from ..utils.display import format_games_count

ROLE_LABELS = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "Bot",
    "support": "Support",
}

# Branches du pentacle de rayon 190 (pointe haute, puis dans le sens horaire), centre à (260, 260).
STAR = ((0.0, -190.0), (180.7, -58.7), (111.7, 153.7), (-111.7, 153.7), (-180.7, -58.7))
ALLY_BRANCHES = (4, 3, 2, 1)  # moi à la pointe haute, les autres sur ces branches
CENTER, PORTRAIT = 260, 92
REC_HUES = (
    "oklch(0.86 0.13 85)",
    "oklch(0.8 0.12 165)",
    "oklch(0.74 0.15 245)",
    "oklch(0.7 0.2 290)",
)
BAN_HUES = (
    "oklch(0.72 0.22 345)",
    "oklch(0.7 0.21 20)",
    "oklch(0.72 0.2 290)",
    "oklch(0.76 0.18 45)",
)

PHASE_TITLES = {
    "ban": "Phase de bans — choisis ton ban",
    "pick_turn": "Phase de picks — à toi de jouer",
    "pick_wait": "Phase de picks — en attente",
    "locked": "Verrouillé — en attente",
    "final": "Finalisation — runes et skin",
}
PHASE_ADVICE = {
    "ban": "Bannis la menace la plus forte contre ton pool",
    "pick_turn": "C'est le moment de sécuriser votre champion !",
    "pick_wait": "Prépare ton pick : survole les recommandations",
    "locked": "Finalisez runes, sorts et skin",
    "final": "Finalisez runes, sorts et skin",
}


def fr(value: float, digits: int = 1) -> str:
    """Nombre à la française : virgule décimale."""
    return f"{value:.{digits}f}".replace(".", ",")


def signed(value: float, digits: int = 1) -> str:
    """Écart signé : « + » ou « − » (vrai signe moins), virgule décimale."""
    return ("+" if value >= 0 else "−") + fr(abs(value), digits)


def games_short(games: Optional[int]) -> str:
    if games is None:
        return "—"
    return fr(games / 1000, 1) + "k" if games >= 1000 else str(games)


def signature(value: Any) -> str:
    """Empreinte courte d'une donnée affichée : le front ne remplace un nœud que si elle change."""
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]  # nosec - empreinte, pas de sécurité


class Champions:
    """Portraits par identifiant numérique Riot, via Data Dragon (`assets.champions()`)."""

    def __init__(self, assets: Any) -> None:
        self._by_key = {c["key"]: c for c in assets.champions()}

    def ddragon_id(self, champion_id: Optional[int]) -> Optional[str]:
        champion = self._by_key.get(champion_id)
        return champion["id"] if champion else None

    def image(self, champion_id: Optional[int]) -> Optional[str]:
        champion = self._by_key.get(champion_id)
        return f"/assets/champion/{champion['id']}.png" if champion else None

    def name(self, champion_id: Optional[int]) -> str:
        """Le nom affiché du champion ; « Champion 123 » quand Data Dragon est injoignable."""
        champion = self._by_key.get(champion_id)
        return champion["name"] if champion else f"Champion {champion_id}"


def _role_rank(role: Optional[str]) -> int:
    return (
        scraping_config.LANES.index(role)
        if role in scraping_config.LANES
        else len(scraping_config.LANES)
    )


def _branch_point(branch: int) -> Tuple[float, float]:
    x, y = STAR[branch]
    return round(CENTER + x - PORTRAIT / 2, 1), round(CENTER + y - PORTRAIT / 2, 1)


def _status(player: Dict[str, Any], kind: Optional[str]) -> str:
    if kind == "ban":
        return "intention" if player["team"] == "ally" else "en attente"
    if player["champion_id"]:
        if player["team"] == "ally":
            return "verrouillé"
        source = player.get("role_source")
        if source == "user":
            return "forcé"
        confidence = player.get("role_confidence")
        return (
            f"déduit {round(confidence * 100)} %"
            if source == "inferred" and confidence
            else "choisi"
        )
    return "survol" if player.get("hover_id") else "à choisir"


SWAP_NAMES = {"pick_order": "ordre", "position": "rôle"}


def _swap_buttons(snapshot: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    """Par cellule alliée, les boutons d'échange à poser sur sa légende (SPEC-24 tâche 104).

    Une entrée `AVAILABLE` se demande, une entrée `SENT` s'annule ; une demande reçue (`RECEIVED`) passe
    par le bandeau (`swap_requests`), une entrée `INVALID` n'offre rien. Le gain chiffré du coach s'ajoute
    au bouton d'échange de rôle.
    """
    gains = {
        a["cell_id"]: a["gain_pts"]
        for a in snapshot.get("swap_advice") or []
        if a["kind"] == "position"
    }
    buttons: Dict[int, List[Dict[str, Any]]] = {}
    for swap in snapshot.get("swaps") or []:
        name = SWAP_NAMES[swap["kind"]]
        gain = gains.get(swap["cell_id"]) if swap["kind"] == "position" else None
        if swap["state"] == "AVAILABLE":
            label = f"⇄ {name}" + (f" {signed(gain)} pts" if gain is not None else "")
            title = f"Demander l'échange de {name}" + (
                f" : le modèle estime {signed(gain)} pts de victoire prédite"
                if gain is not None
                else ""
            )
            action = "request"
        elif swap["state"] == "SENT":
            label, title, action = f"✕ {name}", f"Annuler ma demande d'échange de {name}", "cancel"
        else:
            continue
        buttons.setdefault(swap["cell_id"], []).append(
            {
                "kind": swap["kind"],
                "action": action,
                "state": swap["state"].lower(),
                "label": label,
                "title": title,
            }
        )
    return buttons


def swap_requests(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Les demandes d'échange reçues, pour le bandeau : qui, quel échange, à accepter ou refuser."""
    players = {p["cell_id"]: p for p in snapshot.get("allies", [])}
    mine = next((p for p in players.values() if p["is_local"]), None)
    gains = {
        a["cell_id"]: a["gain_pts"]
        for a in snapshot.get("swap_advice") or []
        if a["kind"] == "position"
    }
    found = []
    for swap in snapshot.get("swaps") or []:
        if swap["state"] != "RECEIVED":
            continue
        who = players.get(swap["cell_id"]) or {}
        name = (
            who.get("champion") or who.get("hover") or ROLE_LABELS.get(who.get("role"), "Un allié")
        )
        if swap["kind"] == "pick_order":
            theirs, ours = who.get("pick_order"), (mine or {}).get("pick_order")
            detail = (
                f"son ordre de pick (n° {theirs} contre ton n° {ours})"
                if theirs and ours
                else "son ordre de pick"
            )
        else:
            detail = "vos rôles"
        gain = gains.get(swap["cell_id"]) if swap["kind"] == "position" else None
        found.append(
            {
                "kind": swap["kind"],
                "cell_id": swap["cell_id"],
                "text": f"{name} te propose d'échanger {detail}",
                "gain": (
                    None
                    if gain is None
                    else f"Le modèle estime {signed(gain)} pts de victoire prédite"
                ),
            }
        )
    return found


def _member(
    player: Dict[str, Any],
    branch: int,
    champions: Champions,
    kind: Optional[str],
    delay: int,
    swap: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    left, top = _branch_point(branch)
    champion_id = player["champion_id"]
    hover_id = player.get("hover_id") or 0
    shown = champion_id or hover_id
    foe_hidden = player["team"] == "enemy" and (kind == "ban" or not champion_id)
    return {
        "team": player["team"],
        "cell_id": player["cell_id"],
        "champion_id": champion_id,
        "name": (
            "Inconnu"
            if (foe_hidden and kind == "ban")
            else (
                player["champion"] or player.get("hover") or ("En attente" if foe_hidden else "—")
            )
        ),
        "img": None if foe_hidden else champions.image(shown),
        "role": ROLE_LABELS.get(player["role"], "—") if player["role"] else "—",
        "status": _status(player, kind),
        "order": player.get("pick_order"),  # rang de pick 1 à 10, None sans actions du LCU
        "swap": swap or [],
        "acting": bool(player.get("is_acting")),
        "pending": foe_hidden or not shown,
        "hovering": bool(hover_id and not champion_id),
        "left": left,
        "top": top,
        "delay": delay,
    }


def seals(snapshot: Dict[str, Any], champions: Champions, intro: bool) -> Dict[str, Any]:
    """Les deux sceaux : moi à la pointe haute, mes alliés puis les adversaires sur les branches."""
    kind = snapshot.get("kind")
    allies = snapshot["allies"]
    me = next((p for p in allies if p["is_local"]), None)
    buttons = _swap_buttons(snapshot)
    others = sorted((p for p in allies if p is not me), key=lambda p: _role_rank(p["role"]))
    ally_members = [
        _member(
            p,
            ALLY_BRANCHES[i],
            champions,
            kind,
            1200 + i * 90 if intro else 0,
            buttons.get(p["cell_id"]),
        )
        for i, p in enumerate(others[: len(ALLY_BRANCHES)])
    ]

    free = list(range(len(STAR)))
    placed: List[Tuple[int, Dict[str, Any]]] = []
    unplaced = []
    for p in snapshot["enemies"]:
        branch = _role_rank(p["role"]) if p["champion_id"] and kind != "ban" else None
        if branch is not None and branch in free:
            free.remove(branch)
            placed.append((branch, p))
        else:
            unplaced.append(p)
    for p in unplaced[: len(free)]:
        placed.append((free.pop(0), p))
    foe_members = [
        _member(p, branch, champions, kind, 1250 + i * 90 if intro else 0)
        for i, (branch, p) in enumerate(sorted(placed, key=lambda item: item[0]))
    ]
    # Les emplacements adverses que le LCU ne liste pas encore restent des inconnus.
    for branch in free:
        foe_members.append(
            _member(
                {
                    "team": "enemy",
                    "cell_id": None,
                    "champion_id": 0,
                    "champion": None,
                    "role": None,
                    "hover_id": 0,
                },
                branch,
                champions,
                kind,
                0,
            )
        )

    me_view = None
    if me is not None:
        shown = me["champion_id"] or me["hover_id"]
        me_view = {
            "cell_id": me["cell_id"],
            "order": me.get("pick_order"),
            "acting": bool(me.get("is_acting")),
            "champion_id": me["champion_id"],
            "name": me["champion"] or me.get("hover") or "Choisir",
            "img": champions.image(shown),
            "role": ROLE_LABELS.get(me["role"] or snapshot.get("local_role"), "—"),
            "locked": bool(me["champion_id"]),
            "state": (
                "verrouillé" if me["champion_id"] else ("survol" if me["hover_id"] else "intention")
            ),
            "opacity": 1 if me["champion_id"] else 0.6,
        }
    return {"allies": ally_members, "foes": foe_members, "me": me_view}


def _ban_slot(
    champion_id: Optional[int], name: Optional[str], champions: Champions, **extra: Any
) -> Dict[str, Any]:
    return {"champion_id": champion_id, "name": name, "img": champions.image(champion_id), **extra}


def ban_strips(snapshot: Dict[str, Any], champions: Champions) -> Dict[str, Any]:
    """Les bans de l'en-tête : le mien (40 px), ceux de mon camp, ceux des adversaires (cachés en phase de bans)."""
    in_ban_phase = snapshot.get("kind") == "ban"
    mine = snapshot.get("my_ban")
    hover = snapshot.get("my_ban_hover")
    if mine:
        me_slot = _ban_slot(mine["champion_id"], mine["champion"], champions, state="done")
    elif hover:
        me_slot = _ban_slot(hover["champion_id"], hover["champion"], champions, state="aim")
    else:
        me_slot = _ban_slot(None, None, champions, state="open")
    mine_id = mine["champion_id"] if mine else None
    allied = [b for b in snapshot["ally_bans"] if b["champion_id"] != mine_id]
    ally_slots = [
        _ban_slot(b["champion_id"], b["champion"], champions, state="done") for b in allied
    ] + [_ban_slot(None, None, champions, state="hidden")] * max(0, 4 - len(allied))
    if in_ban_phase and not snapshot["enemy_bans"]:
        foe_slots = [_ban_slot(None, None, champions, state="hidden")] * 5
    else:
        foe_slots = [
            _ban_slot(b["champion_id"], b["champion"], champions, state="done")
            for b in snapshot["enemy_bans"]
        ]
    return {"me": me_slot, "allies": ally_slots[:4], "foes": foe_slots}


def recommendations(snapshot: Dict[str, Any], champions: Champions) -> List[Dict[str, Any]]:
    """Les cartes de pick : portrait, win %, écart, suite attendue (README : « Draft, phase de picks »)."""
    cards = []
    for index, rec in enumerate(snapshot["recommendations"][: client_config.DRAFT_REC_COUNT]):
        delta = rec["delta"]
        variation = ", ".join(
            (
                f"{step['champion']} ({ROLE_LABELS.get(step['lane'], step['lane'])})"
                if step["lane"]
                else step["champion"]
            )
            for step in rec["variation"]
        )
        cards.append(
            {
                "champion_id": rec["champion_id"],
                "name": rec["champion"],
                "img": champions.image(rec["champion_id"]),
                "hue": REC_HUES[index % len(REC_HUES)],
                "games": f"{games_short(rec['games'])} games",
                "win": fr(rec["win_probability"] * 100, 2) + " %",
                "delta": (None if delta is None else signed(delta) + " pts"),
                "up": delta is None or delta >= 0,
                "line": f"Suite attendue : {variation}" if variation else "Suite attendue : —",
                "delay": 500 + index * 90,
            }
        )
    return cards


def ban_cards(snapshot: Dict[str, Any], champions: Champions) -> List[Dict[str, Any]]:
    """Les bans conseillés : gain en points et justification (README : « Draft, phase de bans »)."""
    cards = []
    for index, advice in enumerate(snapshot["ban_advice"]):
        cards.append(
            {
                "champion_id": advice["champion_id"],
                "name": advice["champion"],
                "img": champions.image(advice["champion_id"]),
                "hue": BAN_HUES[index % len(BAN_HUES)],
                "gain": "+" + fr(advice["gain"]),
                "line": f"Ta meilleure réponse : {advice['best_response']} ({signed(advice['best_response_value'])} pts)",
                "delay": 500 + index * 90,
            }
        )
    return cards


def _phase(snapshot: Dict[str, Any], me: Optional[Dict[str, Any]]) -> str:
    if snapshot.get("kind") == "ban":
        return "ban"
    if me and me["locked"]:
        return "final" if snapshot.get("phase") == "FINALIZATION" else "locked"
    return "pick_turn" if snapshot.get("my_turn") else "pick_wait"


def skin_row(
    snapshot: Dict[str, Any], champions: Champions, skins: Optional[List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """La sélection de skin du champion verrouillé : cartes, skin choisi, possession (README : « Skins »)."""
    me = next((p for p in snapshot["allies"] if p["is_local"]), None)
    champion_id = (me or {}).get("champion_id") or 0
    ddragon = champions.ddragon_id(champion_id)
    chosen = (me or {}).get("skin_id") or champion_id * 1000
    cards = []
    for skin in skins or []:
        cards.append(
            {
                "id": skin["id"],
                "num": skin["num"],
                "name": "Classique" if skin["num"] == 0 or skin["base"] else skin["name"],
                "owned": skin["owned"],
                "img": f"/assets/loading/{ddragon}_{skin['num']}.jpg" if ddragon else None,
            }
        )
    current = next((c for c in cards if c["id"] == chosen), cards[0] if cards else None)
    return {
        "available": skins is not None,
        "cards": cards,
        "chosen_id": chosen,
        "chosen_name": current["name"] if current else "Classique",
        "owned": sum(1 for c in cards if c["owned"]),
        "splash": f"/assets/splash/{ddragon}_{current['num']}.jpg" if ddragon and current else None,
    }


def stage_view(
    snapshot: Optional[Dict[str, Any]],
    assets: Any,
    intro: bool = False,
    skins: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Tout ce que `partials/draft_stage.html` dessine ; `{"empty": True}` hors champ select."""
    if not snapshot:
        return {"empty": True}
    champions = Champions(assets)
    sealed = seals(snapshot, champions, intro)
    phase = _phase(snapshot, sealed["me"])
    recs = recommendations(snapshot, champions)
    bans = ban_cards(snapshot, champions)
    skin = skin_row(snapshot, champions, skins if phase in ("locked", "final") else None)
    base, projected = snapshot.get("base_probability"), snapshot.get("projected_probability")
    shown = projected if projected is not None else base
    # Ce que le script de l'écran lit à chaque rafraîchissement : le chrono, la balance, la sélection.
    state = {
        "phase": phase,
        "kind": snapshot.get("kind"),
        "my_turn": snapshot.get("my_turn"),
        "time_left_ms": snapshot.get("time_left_ms"),
        "time_total_ms": snapshot.get("time_total_ms"),
        "base": base,
        "projected": projected,
        "shown": shown,
        "win": {
            str(r["champion_id"]): r["win_probability"]
            for r in snapshot["recommendations"]
            if r["champion_id"]
        },
        "hover_id": (sealed["me"] or {}).get("champion_id") or snapshot_hover(snapshot),
        "locked_id": (sealed["me"] or {}).get("champion_id") or 0,
        "skin_id": skin["chosen_id"],
        "loadout": bool(snapshot.get("loadout")),
        "my_ban_id": (snapshot.get("my_ban") or {}).get("champion_id") or 0,
        "ban_hover_id": (snapshot.get("my_ban_hover") or {}).get("champion_id") or 0,
        "recs": [r["champion_id"] for r in recs],
        "bans": [b["champion_id"] for b in bans],
        "names": {str(r["champion_id"]): r["name"] for r in recs + bans if r["champion_id"]},
    }
    role = ROLE_LABELS.get(snapshot.get("local_role"), "")
    versus = snapshot.get("versus")
    skipped = snapshot["skipped"]
    parts = [f"Pool {snapshot['pool_name']}"] if snapshot.get("pool_name") else []
    if snapshot["recommendations"]:
        parts.append(f"profondeur atteinte : {snapshot['depth']} pick(s) anticipé(s)")
    if skipped:
        where = f" en {role}" if role else ""
        listed = ", ".join(
            f"{s['champion']} ({format_games_count(s['games'])} games)" for s in skipped
        )
        parts.append(f"sans données exploitables{where} : {listed}")
    return {
        "empty": False,
        "intro": intro,
        "rec_title": "Recommandations"
        + (f" · {role}" if role else "")
        + (f" contre {versus}" if versus else ""),
        "rec_sub": " · ".join(parts),
        "rec_empty": "Aucune recommandation pour le moment : un pick adverse ou le grimoire en donnera.",
        "phase": phase,
        "title": PHASE_TITLES[phase],
        "advice": PHASE_ADVICE[phase],
        "role": ROLE_LABELS.get(snapshot.get("local_role"), ""),
        "seals": sealed,
        "swap_requests": swap_requests(snapshot),
        "strips": ban_strips(snapshot, champions),
        "skin": skin,
        "recs": recs,
        "ban_cards": bans,
        "skipped": snapshot["skipped"],
        "depth": snapshot["depth"],
        "pool_name": snapshot.get("pool_name"),
        "balance": {"base": base, "projected": projected},
        "state": state,
    }


def snapshot_hover(snapshot: Dict[str, Any]) -> int:
    """Le champion que je survole, 0 si aucun."""
    me = next((p for p in snapshot["allies"] if p["is_local"]), None)
    return (me or {}).get("hover_id") or 0
