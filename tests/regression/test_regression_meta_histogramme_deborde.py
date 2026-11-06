"""Régression client : le graphe des tirages de la Méta du poste déborde de sa colonne.

Symptôme (relecture de SPEC-51 dans le navigateur intégré, 2026-11-06) : à 1 440 px, la colonne principale
fait 655 px mais le graphe du top en demande 5 508 (145 colonnes) ; on ne voit que du vide et une barre de
défilement. Au mid, 35 colonnes.

Cause racine : une colonne par tranche de `BLINDABILITE_BIN_PP` (0,05 pp), sur toute l'étendue des tirages
du poste. Au seuil de 15 000 parties, Sylas sort à +3,58 pp au top quand tous les autres restent sous 1 pp.

Correctif : axe borné à ±`BLINDABILITE_MAX_PP` (1 pp), colonnes de 0,1 pp ; une valeur au-delà va dans la
colonne du bord, marquée « ≥ » ou « ≤ ».

Prévention : ces tests construisent l'histogramme d'un poste avec une valeur aberrante.
"""

from src.client.meta_poste import meta_view
from src.config_client import client_config


class _NoPortraits:
    def by_name(self, name):
        return None


def _histogram(draws):
    data = {"matchups": {"top": {"top": 1.0}}, "draws": {"top": draws}}
    return meta_view(data, _NoPortraits(), "top", (), [])["histogram"]


def test_une_valeur_aberrante_ne_deborde_pas_de_l_axe():
    columns = _histogram({"Sylas": 3.58, "Riven": -0.47, "Shen": -0.2, "Gwen": 0.77})

    bound = round(client_config.BLINDABILITE_MAX_PP / client_config.BLINDABILITE_BIN_PP)
    assert len(columns) == 2 * bound + 1 == 21
    assert [c["name"] for c in columns[-1]["champions"]] == ["Sylas"]
    assert columns[-1]["label"].startswith("≥")


def test_sans_valeur_aberrante_l_axe_suit_l_etendue():
    columns = _histogram({"Ahri": 0.3, "Zed": -0.12})

    assert len(columns) == 7  # ±0,3 pp en colonnes de 0,1 pp
    assert not any(c["label"].startswith(("≥", "≤")) for c in columns)
