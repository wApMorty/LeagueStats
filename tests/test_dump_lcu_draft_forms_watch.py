"""SPEC-24 tâche 96 : `dump_lcu_draft_forms.py --watch` n'écrit que les formes nouvelles, anonymisées.

Faux LCU, répertoire temporaire : rien ne touche le vrai client ni `outputs/`.
"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

SCRIPT = Path(__file__).parent.parent / "scripts" / "dump_lcu_draft_forms.py"
spec = importlib.util.spec_from_file_location("dump_lcu_draft_forms", SCRIPT)
dump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dump)


def fake_lcu(responses):
    """``responses`` : endpoint -> liste de réponses successives (la dernière se répète)."""
    lcu = Mock()
    counters = {}

    def request(endpoint):
        queue = responses.get(endpoint)
        if not queue:
            return None
        index = counters.get(endpoint, 0)
        counters[endpoint] = index + 1
        return queue[min(index, len(queue) - 1)]

    lcu._make_request.side_effect = request
    return lcu


def test_ecrit_chaque_nouvelle_forme_une_seule_fois(tmp_path, capsys):
    session = "/lol-champ-select/v1/session"
    ban = {"timer": {"phase": "BAN_PICK", "adjustedTimeLeftInPhase": 20000}}
    ban_later = {"timer": {"phase": "BAN_PICK", "adjustedTimeLeftInPhase": 19000}}
    pick = {"timer": {"phase": "FINALIZATION", "adjustedTimeLeftInPhase": 9000}}
    lcu = fake_lcu({session: [ban, ban_later, pick]})
    dump.watch(lcu, tmp_path, interval=0, ticks=3, sleep=lambda _: None)
    # Le compteur qui avance seul n'est pas une forme : 2 écritures pour 3 lectures.
    assert capsys.readouterr().out.count("[DATA]") == 2


def test_identites_retirees_et_endpoint_absent_ignore(tmp_path):
    session = "/lol-champ-select/v1/session"
    lcu = fake_lcu(
        {
            session: [
                {"myTeam": [{"puuid": "x", "obfuscatedPuuid": "y", "gameName": "n", "cellId": 0}]}
            ]
        }
    )
    dump.watch(lcu, tmp_path, interval=0, ticks=1, sleep=lambda _: None)
    text = next(tmp_path.glob("*_session.json")).read_text(encoding="utf-8")
    assert '"cellId": 0' in text
    for secret in ('"x"', '"y"', '"n"'):
        assert secret not in text
    assert [f.name.split("_", 1)[1] for f in tmp_path.iterdir()] == ["session.json"]
