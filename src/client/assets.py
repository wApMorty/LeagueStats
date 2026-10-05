"""Images et données de Data Dragon, servies par le client depuis un cache disque (SPEC-21 tâche 86).

Portraits, sorts, objets, runes, skins et les trois JSON dont la draft a besoin (champions, skins d'un
champion, `runesReforged`). Le premier accès télécharge, les suivants lisent le disque : hors ligne, le
cache seul répond, et une image absente rend un emplacement neutre (jamais d'erreur dans la page).
La version est celle de la config, sinon la plus récente de `versions.json` (elle-même mise en cache).

Seules les formes de nom listées dans `_KINDS` sont acceptées : le front ne désigne jamais une URL.
"""

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from ..config_client import client_config

Fetch = Callable[[str], Optional[bytes]]

# kind -> (gabarit d'URL sous `cdn/`, forme du nom accepté, versionné ?)
_SEGMENT = r"[A-Za-z0-9_\-]+"
_KINDS: Dict[str, Tuple[str, "re.Pattern[str]", bool]] = {
    "champion": ("{v}/img/champion/{name}", re.compile(rf"{_SEGMENT}\.png"), True),
    "spell": ("{v}/img/spell/{name}", re.compile(r"Summoner[A-Za-z0-9]+\.png"), True),
    "item": ("{v}/img/item/{name}", re.compile(r"\d+\.png"), True),
    "perk": ("img/{name}", re.compile(rf"(?:{_SEGMENT}/)*{_SEGMENT}\.png"), False),
    "loading": ("img/champion/loading/{name}", re.compile(r"[A-Za-z0-9]+_\d+\.jpg"), False),
    "splash": ("img/champion/splash/{name}", re.compile(r"[A-Za-z0-9]+_\d+\.jpg"), False),
}
_DATA = {
    "champions": "{v}/data/{loc}/champion.json",
    "runes": "{v}/data/{loc}/runesReforged.json",
}
_SKIN_DATA = "{v}/data/{loc}/champion/{name}.json"
_CHAMPION_ID = re.compile(r"[A-Za-z0-9]+")
_VERSION = re.compile(r"\d+(?:\.\d+)+")

# Image neutre (GIF 1×1 transparent) pour une image introuvable.
PLACEHOLDER = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)


def _http_get(url: str) -> Optional[bytes]:
    try:
        response = requests.get(url, timeout=client_config.ASSETS_TIMEOUT_S)
        return response.content if response.status_code == 200 else None
    except requests.RequestException:
        return None


class Assets:
    """Cache disque de Data Dragon ; sans état partagé hors du verrou, utilisable depuis tous les fils."""

    def __init__(self, cache_dir: Path, fetch: Optional[Fetch] = None) -> None:
        self._dir = Path(cache_dir)
        self._fetch = fetch or _http_get
        self._lock = threading.Lock()
        self._failed: Dict[str, float] = {}

    # ---------- version ----------

    def version(self) -> Optional[str]:
        """Version à servir ; None si ni la config, ni le réseau, ni le cache n'en donnent."""
        if client_config.DDRAGON_VERSION:
            return client_config.DDRAGON_VERSION
        cached = self._dir / "versions.json"
        try:
            if cached.stat().st_mtime > time.time() - client_config.ASSETS_VERSIONS_TTL_S:
                return self._first_version(cached.read_bytes())
        except OSError:
            pass
        data = self._download(f"{client_config.DDRAGON_BASE}/api/versions.json", cached)
        if data is None:  # hors ligne : une liste périmée vaut mieux que rien
            try:
                data = cached.read_bytes()
            except OSError:
                return None
        return self._first_version(data)

    @staticmethod
    def _first_version(raw: bytes) -> Optional[str]:
        try:
            first = json.loads(raw)[0]
        except (ValueError, IndexError, TypeError):
            return None
        return first if isinstance(first, str) and _VERSION.fullmatch(first) else None

    # ---------- fichiers ----------

    def _download(self, url: str, target: Path) -> Optional[bytes]:
        """Télécharge `url` dans `target` (écriture atomique) ; un échec n'est pas retenté tout de suite."""
        with self._lock:
            if self._failed.get(url, 0.0) > time.monotonic():
                return None
        data = self._fetch(url)
        if not data:
            with self._lock:
                self._failed[url] = time.monotonic() + client_config.ASSETS_RETRY_S
            return None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f"{target.name}.{threading.get_ident()}.part")
            partial.write_bytes(data)
            partial.replace(target)
        except OSError:
            pass  # disque plein ou en lecture seule : la donnée reste servie cette fois-ci
        return data

    def _file(self, relative: str, url: str) -> Optional[bytes]:
        target = self._dir / relative
        try:
            return target.read_bytes()
        except OSError:
            return self._download(url, target)

    def image(self, kind: str, name: str) -> Optional[bytes]:
        """L'image `name` de la sorte `kind` ; None si le nom est refusé ou l'image introuvable."""
        entry = _KINDS.get(kind)
        if entry is None or not entry[1].fullmatch(name):
            return None
        template, _, versioned = entry
        version = self.version() if versioned else ""
        if versioned and version is None:
            return None
        path = template.format(v=version, name=name)
        return self._file(
            f"{kind}/{version}/{name}" if versioned else f"{kind}/{name}",
            f"{client_config.DDRAGON_BASE}/cdn/{path}",
        )

    def accepts(self, kind: str, name: str) -> bool:
        """Le couple (sorte, nom) a-t-il une forme valide ? (sinon la route répond 404)."""
        entry = _KINDS.get(kind)
        return entry is not None and bool(entry[1].fullmatch(name))

    # ---------- données ----------

    def _json(self, template: str, name: str = "") -> Any:
        version = self.version()
        if version is None:
            return None
        relative = template.format(v=version, loc=client_config.DDRAGON_LOCALE, name=name)
        raw = self._file(relative, f"{client_config.DDRAGON_BASE}/cdn/{relative}")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def champions(self) -> List[Dict[str, Any]]:
        """Tous les champions : `{key, id, name, tags}`, `key` étant l'identifiant numérique Riot."""
        data = self._json(_DATA["champions"])
        if not isinstance(data, dict):
            return []
        return [
            {
                "key": int(champion["key"]),
                "id": champion["id"],
                "name": champion["name"],
                "tags": champion.get("tags", []),
            }
            for champion in data.get("data", {}).values()
        ]

    def skins(self, champion: str) -> List[Dict[str, Any]]:
        """Les skins d'un champion (`champion` : son `id` Data Dragon) : `{num, name}`, base comprise."""
        if not _CHAMPION_ID.fullmatch(champion):
            return []
        data = self._json(_SKIN_DATA, champion)
        try:
            entry = data["data"][champion]["skins"]
            return [{"num": s["num"], "name": s["name"]} for s in entry]
        except (TypeError, KeyError):
            return []

    def rune_styles(self) -> List[Dict[str, Any]]:
        """`runesReforged.json` : les cinq arbres, leurs rangées et leurs runes (icônes comprises)."""
        data = self._json(_DATA["runes"])
        return data if isinstance(data, list) else []
