"""Grimoire des champions : la vue de l'overlay de pick et de ban manuel (SPEC-21 tâche 89).

Fonction pure du snapshot (champions annotés par le Live Coach : rôles, victoire prédite, gain de ban)
et des assets (noms français et portraits). Le tri est fixe : recommandations, puis pool, puis ordre
alphabétique ; recherche, rôle et pool se filtrent côté navigateur (`champions.js`).
"""

import unicodedata
from typing import Any, Dict, List, Optional, Set

from .draft_view import Champions, ROLE_LABELS, fr, games_short, signed

# Teinte (H) de chaque puce de rôle (README du handoff).
ROLE_HUES = (
    ("all", "Tous", 70),
    ("top", "Top", 55),
    ("jungle", "Jungle", 150),
    ("middle", "Mid", 290),
    ("bottom", "Bot", 85),
    ("support", "Support", 230),
)


def plain(text: str) -> str:
    """Minuscules sans accents ni apostrophes : la recherche ignore les accents."""
    stripped = unicodedata.normalize("NFD", text)
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").lower()


def _gone(snapshot: Dict[str, Any], mode: str) -> Dict[int, str]:
    """Champion indisponible -> raison (banni, allié, adverse, intention alliée, ton intention)."""
    reasons: Dict[int, str] = {}
    ban_ids = [b["champion_id"] for b in snapshot["ally_bans"] + snapshot["enemy_bans"]]
    if snapshot.get("my_ban"):
        ban_ids.append(snapshot["my_ban"]["champion_id"])
    for champion_id in ban_ids:
        reasons[champion_id] = "banni"
    me = next((p for p in snapshot["allies"] if p["is_local"]), None)
    for player in snapshot["allies"]:
        if player is me:
            continue
        taken = player["champion_id"] or (player["hover_id"] if mode == "ban" else 0)
        if taken:
            reasons.setdefault(taken, "intention alliée" if mode == "ban" else "allié")
    if mode == "pick":
        for player in snapshot["enemies"]:
            if player["champion_id"]:
                reasons.setdefault(player["champion_id"], "adverse")
    elif me and me["hover_id"]:
        reasons.setdefault(me["hover_id"], "ton intention")
    return reasons


def _info(
    mode: str,
    champion: Dict[str, Any],
    rec: Optional[Dict[str, Any]],
    ban: Optional[Dict[str, Any]],
    in_pool: bool,
    pool: str,
    role: str,
) -> str:
    win = champion.get("win_probability")
    if mode == "ban":
        gain = champion.get("ban_gain")
        if ban:
            return f"Gain estimé si banni : +{fr(ban['gain'])} pts · Ta meilleure réponse : {ban['best_response']} ({signed(ban['best_response_value'])} pts)"
        if gain is not None and gain > 0:
            return f"Gain estimé si banni : +{fr(gain)} pts"
        return "Hors des menaces identifiées pour ton pool"
    if rec:
        steps = ", ".join(
            (
                f"{s['champion']} ({ROLE_LABELS.get(s['lane'], s['lane'])})"
                if s["lane"]
                else s["champion"]
            )
            for s in rec["variation"]
        )
        suite = f" · suite attendue : {steps}" if steps else ""
        return f"Victoire prédite {fr(rec['win_probability'] * 100)} % · {games_short(rec['games'])} games{suite}"
    model = f" · victoire prédite {fr(win * 100)} % (modèle seul)" if win is not None else ""
    if in_pool:
        where = f" en {role}" if role else ""
        return f"Pool {pool} · sans données exploitables{where}{model}"
    return f"Hors pool{model.replace('(modèle seul)', '(modèle seul, sans historique perso)')}"


def grimoire_view(snapshot: Optional[Dict[str, Any]], assets: Any) -> Dict[str, Any]:
    """L'overlay : tuiles triées, puces de rôle, libellés selon le mode (ban ou pick)."""
    if not snapshot:
        return {"empty": True}
    champions = Champions(assets)
    names = {c["key"]: c["name"] for c in assets.champions()}
    mode = "ban" if snapshot.get("kind") == "ban" else "pick"
    gone = _gone(snapshot, mode)
    recs = {r["champion_id"]: r for r in snapshot["recommendations"] if r["champion_id"]}
    bans = {b["champion_id"]: b for b in snapshot["ban_advice"] if b["champion_id"]}
    pool: Set[str] = {n.lower() for n in snapshot.get("pool", [])}
    pool_name = snapshot.get("pool_name") or "personnelle"
    role = ROLE_LABELS.get(snapshot.get("local_role"), "")
    tiles: List[Dict[str, Any]] = []
    for champion in snapshot["champions"]:
        champion_id = champion["champion_id"]
        name = names.get(champion_id) or champion["champion"]
        in_pool = champion["champion"].lower() in pool
        rec, ban = recs.get(champion_id), bans.get(champion_id)
        reason = gone.get(champion_id, "")
        if mode == "ban":
            rank = 0 if ban else 1
            gain = champion.get("ban_gain")
            meta = reason or (
                f"+{fr(ban['gain'])} pts"
                if ban
                else (f"+{fr(gain)} pts" if gain and gain > 0 else "")
            )
            tone = "gone" if reason else "ban"
        else:
            rank = 0 if rec else (1 if in_pool else 2)
            win = champion.get("win_probability")
            meta = reason or (
                f"{fr(win * 100)} %" if win is not None else ("pool" if in_pool else "")
            )
            tone = "gone" if reason else ("win" if win is not None else "pool")
        tiles.append(
            {
                "id": champion_id,
                "name": name,
                "img": champions.image(champion_id),
                "search": plain(name) + " " + plain(champion["champion"]),
                "roles": " ".join(champion["roles"]),
                "pool": in_pool,
                "rank": rank,
                "gone": reason,
                "marked": rank == 0,
                "meta": meta,
                "tone": tone,
                "info": _info(mode, champion, rec, ban, in_pool, pool_name, role),
                "tip": f"{name} : {reason}" if reason else name,
            }
        )
    tiles.sort(key=lambda t: (t["rank"], plain(t["name"])))
    first = next((t for t in tiles if not t["gone"]), None)
    return {
        "empty": False,
        "mode": mode,
        "kicker": (
            "Ban · un par joueur · bans adverses révélés ensuite"
            if mode == "ban"
            else f"Pick{' · ' + role if role else ''}{' contre ' + snapshot['versus'] if snapshot.get('versus') else ''}"
        ),
        "verb": "bannir" if mode == "ban" else "verrouiller",
        "pool_label": f"Pool {pool_name} uniquement",
        "chips": [{"key": key, "label": label, "hue": hue} for key, label, hue in ROLE_HUES],
        "default_role": (
            snapshot.get("local_role") if snapshot.get("local_role") in ROLE_LABELS else "all"
        ),
        "tiles": tiles,
        "first": first,
    }
