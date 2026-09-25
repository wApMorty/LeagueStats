"""Régression (@pj35, 2026-09-25) : les bans conseillés à un pool de tanks top
étaient des ADC, puis des picks top rarissimes (Zilean, Azir) jamais croisés.

Deux causes :
1. La popularité des adversaires était lue côté ``enemy`` des matchups. Or
   LoLalytics range dans les matchups d'un champion les 5 adversaires de la
   partie : pour Aatrox top, Kai'Sa est l'« ennemi » le plus fréquent.
2. La menace supposait qu'on contre-pick toujours avec le meilleur de la pool.
   Les seules menaces restantes étaient alors des picks de spécialistes à fort
   winrate. En soloQ, le ban protège surtout quand on a pické avant son
   adversaire de lane.
"""

from src.analysis.ban_recommendations import BanRecommender


def test_bans_target_frequent_lane_opponents(db, insert_duel, insert_matchup):
    # Adversaires de lane : Camille, fréquente et forte contre la pool ;
    # Zilean, rare mais au winrate de spécialiste.
    insert_duel("Shen", "Camille", 46.0, 0.0, -2.0, 10.0, 20000, lane="top")
    insert_duel("Sion", "Camille", 47.0, 0.0, -1.0, 10.0, 20000, lane="top")
    insert_duel("Shen", "Zilean", 45.0, 0.0, 1.0, 10.0, 300, lane="top")
    insert_duel("Sion", "Zilean", 45.0, 0.0, 1.0, 10.0, 300, lane="top")
    # Kai'Sa n'est qu'un « ennemi » des lignes top : elle joue ADC.
    insert_matchup("Shen", "Kaisa", 45.0, 0.0, -3.0, 10.0, 30000, lane="top")
    insert_matchup("Sion", "Kaisa", 45.0, 0.0, -3.0, 10.0, 30000, lane="top")

    recs = BanRecommender(db).get_ban_recommendations(["Shen", "Sion"], num_bans=5, lane="top")
    names = [enemy for enemy, *_ in recs]

    assert "Kaisa" not in names
    assert names[0] == "Camille"
