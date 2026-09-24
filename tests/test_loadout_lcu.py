"""SPEC-15 §3.3 et §3.5 (critères 4 à 7) : écritures LCU de la build.

Hermétique : un faux client LCU en mémoire, qui enregistre chaque appel. Les
formats des corps de requête sont ceux documentés par la communauté ; la
recette en partie réelle (tâche 14) les confirmera contre le client.
"""

import pytest

from src.config_constants import draft_config
from src.draft.loadout import Build, apply_build

PREFIX = draft_config.LOADOUT_PREFIX

BUILD = Build(
    primary_style=8000,
    sub_style=8300,
    perks=(8008, 8009, 8017, 8313, 8321, 9103),  # ordre OneTricks : trié par id
    shards=(5005, 5008, 5011),
    item_blocks=(
        ("Départ", (1086, 2003, 2003, 3340)),
        ("Core", (2523, 3085)),
        ("Bottes", (3006,)),
        ("Suite", ()),
    ),
    spells=(21, 4),
    games=500,
)

STYLES = [
    {"id": 8000, "slots": [{"perks": [8005, 8008, 8021, 8010]}, {"perks": [9101, 9111, 8009]},
                           {"perks": [9104, 9105, 9103]}, {"perks": [8014, 8017, 8299]}]},
    {"id": 8300, "slots": [{"perks": [8351, 8360, 8369]}, {"perks": [8306, 8304, 8321]},
                           {"perks": [8313, 8352, 8345]}, {"perks": [8347, 8410, 8316]}]},
]  # fmt: skip


class FakeLCU:
    def __init__(self, pages=None, owned=5, sets=None, my_spells=(4, 14), fail=()):
        self.pages = list(pages or [])
        self.owned = owned
        self.item_sets = {"accountId": 7, "itemSets": list(sets or []), "timestamp": 1}
        self.session = {
            "localPlayerCellId": 2,
            "myTeam": [
                {"cellId": 1, "spell1Id": 12, "spell2Id": 4},
                {"cellId": 2, "spell1Id": my_spells[0], "spell2Id": my_spells[1]},
            ],
        }
        self.fail = set(fail)
        self.calls = []

    def get_champion_select_session(self):
        return self.session

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint, data))
        if endpoint in self.fail or (method, endpoint) in self.fail:
            return None
        if endpoint == "/lol-perks/v1/styles":
            return STYLES
        if endpoint == "/lol-perks/v1/inventory":
            return {"ownedPageCount": self.owned}
        if endpoint == "/lol-perks/v1/pages":
            if method == "POST":
                self.pages.append(dict(data, id=99, isDeletable=True))
                return self.pages[-1]
            return list(self.pages)
        if endpoint.startswith("/lol-perks/v1/pages/") and method == "DELETE":
            self.pages = [p for p in self.pages if str(p["id"]) != endpoint.rsplit("/", 1)[1]]
            return {}
        if endpoint == "/lol-summoner/v1/current-summoner":
            return {"summonerId": 42}
        if endpoint == "/lol-item-sets/v1/item-sets/42/sets":
            if method == "PUT":
                self.item_sets = data
            return self.item_sets
        if endpoint == "/lol-champ-select/v1/session/my-selection":
            return {}
        return None

    def deleted(self):
        return [endpoint for method, endpoint, _ in self.calls if method == "DELETE"]


def player_page(page_id, name="Ma page"):
    return {"id": page_id, "name": name, "isDeletable": True}


class TestRunes:
    def test_coach_page_is_replaced_and_player_pages_untouched(self):
        """§3.5.4 : seule la page « LS » subit un DELETE."""
        lcu = FakeLCU(pages=[player_page(1), player_page(2, PREFIX + "Ahri mid"), player_page(3)])
        outcome = apply_build(lcu, BUILD, 222, "Jinx bot")

        assert outcome["runes"] is None
        assert lcu.deleted() == ["/lol-perks/v1/pages/2"]
        assert [p["name"] for p in lcu.pages] == ["Ma page", "Ma page", PREFIX + "Jinx bot"]

    def test_perks_are_sent_in_slot_order_then_shards(self):
        lcu = FakeLCU()
        apply_build(lcu, BUILD, 222, "Jinx bot")
        created = next(data for method, _, data in lcu.calls if method == "POST")
        assert created["selectedPerkIds"] == [8008, 8009, 9103, 8017, 8321, 8313, 5005, 5008, 5011]
        assert (created["primaryStyleId"], created["subStyleId"]) == (8000, 8300)
        assert created["current"] is True

    def test_unreadable_styles_keep_onetricks_order(self):
        lcu = FakeLCU(fail={"/lol-perks/v1/styles"})
        apply_build(lcu, BUILD, 222, "Jinx bot")
        created = next(data for method, _, data in lcu.calls if method == "POST")
        assert created["selectedPerkIds"][:6] == list(BUILD.perks)

    def test_no_free_slot_means_no_write(self):
        """Toutes les pages sont au joueur : on n'écrase rien, on explique."""
        lcu = FakeLCU(pages=[player_page(1), player_page(2)], owned=2)
        outcome = apply_build(lcu, BUILD, 222, "Jinx bot")

        assert outcome["runes"] == "aucun emplacement de page de runes libre"
        assert lcu.deleted() == []
        assert not any(method == "POST" for method, _, _ in lcu.calls)

    def test_the_coach_page_frees_its_own_slot(self):
        """Pages pleines, dont une « LS » : la remplacer reste possible."""
        lcu = FakeLCU(pages=[player_page(1), player_page(2, PREFIX + "Ahri mid")], owned=2)
        assert apply_build(lcu, BUILD, 222, "Jinx bot")["runes"] is None


class TestItems:
    def test_player_sets_are_kept_verbatim_and_one_coach_set_added(self):
        """§3.5.5."""
        mine = {"uid": "a", "title": "Mon set", "blocks": [], "associatedChampions": [1]}
        old = {"uid": "b", "title": PREFIX + "Ahri mid", "blocks": []}
        lcu = FakeLCU(sets=[mine, old])
        outcome = apply_build(lcu, BUILD, 222, "Jinx bot")

        assert outcome["items"] is None
        sets = lcu.item_sets["itemSets"]
        assert sets[0] == mine
        assert [s["title"] for s in sets] == ["Mon set", PREFIX + "Jinx bot"]
        assert lcu.item_sets["accountId"] == 7  # le reste de l'objet est renvoyé tel quel

    def test_blocks_count_duplicates_and_skip_empty_blocks(self):
        lcu = FakeLCU()
        apply_build(lcu, BUILD, 222, "Jinx bot")
        item_set = lcu.item_sets["itemSets"][-1]
        assert item_set["associatedChampions"] == [222]
        assert [b["type"] for b in item_set["blocks"]] == ["Départ", "Core", "Bottes"]
        assert item_set["blocks"][0]["items"] == [
            {"id": "1086", "count": 1},
            {"id": "2003", "count": 2},
            {"id": "3340", "count": 1},
        ]


class TestSpells:
    @pytest.mark.parametrize(
        "my_spells, expected",
        [
            ((4, 14), (4, 21)),  # Flash sur D : il y reste
            ((14, 4), (21, 4)),  # Flash sur F : il y reste
            ((12, 14), (21, 4)),  # pas de Flash : ordre OneTricks
        ],
    )
    def test_flash_stays_on_the_player_key(self, my_spells, expected):
        """§3.5.6."""
        lcu = FakeLCU(my_spells=my_spells)
        assert apply_build(lcu, BUILD, 222, "Jinx bot")["sorts"] is None
        patch_call = next(data for method, _, data in lcu.calls if method == "PATCH")
        assert (patch_call["spell1Id"], patch_call["spell2Id"]) == expected


class TestBestEffort:
    def test_each_write_fails_alone(self):
        """§3.5.7 : un 500 sur les runes n'empêche ni les items ni les sorts."""
        lcu = FakeLCU(fail={("POST", "/lol-perks/v1/pages")})
        outcome = apply_build(lcu, BUILD, 222, "Jinx bot")
        assert outcome == {
            "runes": "page de runes refusée par le client",
            "items": None,
            "sorts": None,
        }

    def test_client_exceptions_never_escape(self):
        class Broken(FakeLCU):
            def _make_request(self, *args, **kwargs):
                raise RuntimeError("client fermé")

            def get_champion_select_session(self):
                raise RuntimeError("client fermé")

        outcome = apply_build(Broken(), BUILD, 222, "Jinx bot")
        assert all(reason.startswith("erreur inattendue") for reason in outcome.values())

    def test_unknown_summoner_skips_items_only(self):
        lcu = FakeLCU(fail={"/lol-summoner/v1/current-summoner"})
        outcome = apply_build(lcu, BUILD, 222, "Jinx bot")
        assert outcome["items"] == "invocateur inconnu"
        assert outcome["runes"] is None and outcome["sorts"] is None
