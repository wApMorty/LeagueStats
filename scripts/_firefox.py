"""Firefox headless à taille intérieure exacte, pour les scripts qui rendent le client (SPEC-30, SPEC-34).

Partagé par `scripts/measure_en_partie.py` (mesure de l'écran « En partie ») et
`scripts/capture_screens.py` (captures de la vitrine).
"""

import time
from typing import Tuple

from selenium import webdriver
from selenium.webdriver.firefox.options import Options


def headless_firefox(taille: Tuple[int, int]) -> webdriver.Firefox:
    """Un Firefox headless démarré à `taille` (fenêtre externe ; voir `fenetre` pour l'intérieur)."""
    options = Options()
    options.add_argument("-headless")
    options.add_argument(f"--width={taille[0]}")
    options.add_argument(f"--height={taille[1]}")
    return webdriver.Firefox(options=options)


def fenetre(driver: webdriver.Firefox, taille: Tuple[int, int], reflux_s: float) -> None:
    """Fixe la taille intérieure de la fenêtre (la taille demandée est celle de la fenêtre externe),
    puis laisse `reflux_s` secondes à la page pour se recomposer."""
    largeur, hauteur = taille
    driver.set_window_size(largeur, hauteur)
    interieur = driver.execute_script("return [window.innerWidth, window.innerHeight];")
    if interieur != [largeur, hauteur]:
        driver.set_window_size(2 * largeur - interieur[0], 2 * hauteur - interieur[1])
    time.sleep(reflux_s)
