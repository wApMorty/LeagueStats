"""Régression écran Pool : changer de pool vidait la page, l'ajout d'un champion ne s'affichait pas.

Symptôme (@pj35, 2026-10-09) : sur /pool, un clic sur un autre pool de « Mes pools » laisse une page
vide ; un clic sur un champion recharge l'écran sans que le champion apparaisse dans le pool.

Cause racine : `#view` (base.html) pose `hx-boost`, `hx-target="#view"` et `hx-select="#view"`, hérités
par tout son contenu. `#pool-body` redéfinissait `hx-target` mais pas `hx-select` : les `hx-post`
visaient `#pool-body` en y sélectionnant `#view`, absent du fragment renvoyé (contenu vide) ; les liens
« Mes pools » injectaient le `#view` entier dans `#pool-body` (id dupliqué, transition figée).

Correctif : `hx-select="#pool-body"` sur `#pool-body`, et `hx-target`/`hx-select` = `#view` sur la liste
« Mes pools » pour que ses liens restent une navigation de page entière.

Prévention : ce test résout l'héritage htmx (attribut le plus proche, par attribut) et exige que la
cible et la sélection de chaque requête coïncident avec ce que le serveur renvoie.
"""

from html.parser import HTMLParser

from tests.test_client_pool import post, saved, web  # noqa: F401  (fixture `web`)

VOID = {"input", "br", "meta", "link", "img", "hr"}


class Tree(HTMLParser):
    """Liste les éléments avec leurs attributs et la pile de leurs ancêtres."""

    def __init__(self):
        super().__init__()
        self.stack, self.nodes = [], []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parents": list(self.stack)}
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack and self.stack.pop()["tag"] != tag:
            pass


def parse(html):
    tree = Tree()
    tree.feed(html)
    return tree.nodes


def inherited(node, attr):
    """Valeur htmx effective : l'élément lui-même, sinon l'ancêtre le plus proche qui la pose."""
    for n in [node, *reversed(node["parents"])]:
        if attr in n["attrs"]:
            return n["attrs"][attr]
    return None


def test_les_actions_du_pool_selectionnent_ce_qu_elles_ciblent(web):
    nodes = parse(web.get("/pool?nom=All Top Champions").text)
    posts = [
        n
        for n in nodes
        if "hx-post" in n["attrs"]
        and any(a["attrs"].get("id") == "pool-body" for a in n["parents"])
    ]
    assert posts
    for n in posts:
        assert inherited(n, "hx-target") == inherited(n, "hx-select") == "#pool-body", n["attrs"]


def test_les_liens_mes_pools_restent_une_navigation_de_page_entiere(web):
    nodes = parse(web.get("/pool").text)
    links = [
        n for n in nodes if n["tag"] == "a" and n["attrs"].get("href", "").startswith("/pool?nom=")
    ]
    assert links
    for n in links:
        assert inherited(n, "hx-target") == inherited(n, "hx-select") == "#view", n["attrs"]


def test_ajouter_un_champion_renvoie_le_fragment_pool_body_et_l_enregistre(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    reply = post(web, "/pool/ajouter?name=Main&arg=Zed")
    ids = [n["attrs"].get("id") for n in parse(reply.text)]
    assert "pool-body" in ids and "view" not in ids
    assert saved(web)["Main"]["champions"] == ["Zed"]
