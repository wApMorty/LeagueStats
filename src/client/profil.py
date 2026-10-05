"""Écran Profil : l'invocateur, ses rangs, sa régalia et ses défis, lus dans le LCU (SPEC-21 tâche 77).

Fonctions pures : les réponses du LCU entrent, un dictionnaire prêt pour Jinja sort. Une réponse absente
(None) donne une section « indisponible », jamais une erreur ; une valeur manquante dans une réponse reçue
lève `KeyError`, que l'écran traduit en « indisponible » (le LCU n'est pas garanti, §4.7).
"""

from typing import Any, Dict, List, Optional

from ..config_client import client_config
from .data import QUEUE_STYLE, fr, tier_name, thousands
from .lcu_proxy import LcuProxy

SUMMONER = "/lol-summoner/v1/current-summoner"
RANKED = "/lol-ranked/v1/current-ranked-stats"
REGALIA = "/lol-regalia/v2/current-summoner/regalia"
CHALLENGES = "/lol-challenges/v1/summary-player-data/local-player"

PRIVACY = {"PUBLIC": "Profil public", "PRIVATE": "Profil privé"}
SERIES = {"W": "V", "L": "D", "N": "·"}  # série de promotion : victoire, défaite, à jouer


def _tier(tier: str, division: str) -> str:
    """« Émeraude II » ; « Non classé » sans palier ; la division « NA » (Maître et au-delà) est omise."""
    if not tier:
        return "Non classé"
    return tier_name({"tier": tier, "division": "" if division in ("", "NA") else division})


def _queue_card(entry: Dict[str, Any]) -> dict:
    queue = entry["queueType"]
    style = QUEUE_STYLE[queue]
    wins, losses = entry["wins"], entry["losses"]
    games = wins + losses
    if not entry["tier"]:
        note = (
            f"Placement : {entry['provisionalGamesRemaining']} parties à jouer"
            if entry.get("isProvisional")
            else "Pas encore classé dans cette file."
        )
        return {"name": client_config.RANK_QUEUE_NAMES[queue], "empty": True, "note": note, **style}
    series = " ".join(SERIES.get(letter, "·") for letter in entry.get("miniSeriesProgress") or "")
    best = _tier(entry.get("highestTier", ""), entry.get("highestDivision", ""))
    return {
        "name": client_config.RANK_QUEUE_NAMES[queue],
        "empty": False,
        "tier": _tier(entry["tier"], entry["division"]),
        "lp": entry["leaguePoints"],
        "stats": [
            (str(wins), "victoires"),
            (str(losses), "défaites"),
            (f"{fr(100 * wins / games, 0)} %" if games else "—", "taux de victoire"),
        ],
        "note": f"Série de promotion : {series}" if series else f"Plus haut atteint : {best}",
        **style,
    }


def _queues(ranked: Optional[Dict[str, Any]]) -> Optional[List[dict]]:
    if ranked is None:
        return None
    by_queue = {entry["queueType"]: entry for entry in ranked["queues"]}
    return [_queue_card(by_queue[q]) for q in client_config.PROFILE_QUEUES if q in by_queue]


def _regalia(regalia: Optional[Dict[str, Any]]) -> Optional[List[tuple]]:
    if regalia is None:
        return None
    best, last = regalia["highestRankedEntry"], regalia["lastSeasonHighestRank"]
    return [
        ("Rang le plus élevé", _tier(best.get("tier", ""), best.get("division", ""))),
        ("Saison précédente", _tier(last, "") if last else "Non classé"),
        ("Emblème de prestige", f"n° {regalia['selectedPrestigeCrest']}"),
    ]


def _challenges(summary: Optional[Dict[str, Any]]) -> Optional[dict]:
    if summary is None:
        return None
    level = summary["overallChallengeLevel"]
    categories = [
        {
            "name": client_config.CHALLENGE_CATEGORIES.get(c["category"], c["category"].title()),
            "level": client_config.TIER_NAMES.get(c["level"], c["level"].title()),
            "current": thousands(c["current"]),
            "max": thousands(c["max"]),
            "percent": round(100 * c["current"] / c["max"]) if c["max"] else 0,
        }
        for c in summary["categoryProgress"]
    ]
    top = [
        {
            "name": t["name"],
            "text": t["descriptionShort"],
            "level": client_config.TIER_NAMES.get(t["currentLevel"], t["currentLevel"].title()),
            "value": thousands(t["currentValue"]),
            "next": thousands(t["nextThreshold"]) if t.get("nextLevel") else None,
            "percentile": fr(t["percentile"], 1),
        }
        for t in summary["topChallenges"]
    ]
    return {
        "level": client_config.TIER_NAMES.get(level, level.title()),
        "score": thousands(summary["totalChallengeScore"]),
        "missing": thousands(summary["pointsUntilNextRank"]),
        "percentile": fr(summary["positionPercentile"], 1),
        "title": (summary.get("title") or {}).get("name", ""),
        "categories": categories,
        "top": top,
    }


def read_profile(proxy: LcuProxy) -> Optional[dict]:
    """Lit les quatre réponses du LCU ; None si l'invocateur lui-même est illisible."""
    summoner = proxy.get(SUMMONER)
    if summoner is None:
        return None
    return profile_view(summoner, proxy.get(RANKED), proxy.get(REGALIA), proxy.get(CHALLENGES))


def profile_view(
    summoner: Dict[str, Any],
    ranked: Optional[Dict[str, Any]],
    regalia: Optional[Dict[str, Any]],
    challenges: Optional[Dict[str, Any]],
) -> dict:
    """L'écran Profil ; `summoner` est obligatoire, les trois autres sections peuvent manquer."""
    return {
        "name": summoner["gameName"],
        "tag": summoner["tagLine"],
        "level": summoner["summonerLevel"],
        "icon": f"/assets/profileicon/{summoner['profileIconId']}.png",
        "xp": {
            "percent": summoner["percentCompleteForNextLevel"],
            "since": thousands(summoner["xpSinceLastLevel"]),
            "until": thousands(summoner["xpUntilNextLevel"]),
        },
        "privacy": PRIVACY.get(summoner.get("privacy"), "Profil"),
        "queues": _queues(ranked),
        "regalia": _regalia(regalia),
        "challenges": _challenges(challenges),
    }
