"""Graphiques SVG du client (SPEC-21 tâche 50) : échelles, accessibilité, échappement, cas limites."""

import re
import xml.etree.ElementTree as ET

import pytest

from src.client.charts import (
    Band,
    Mark,
    Series,
    SparkLine,
    Tick,
    bar_chart,
    diverging,
    line_chart,
    reliability_chart,
    sparkline,
)

NS = {"s": "http://www.w3.org/2000/svg"}


def parse(svg: str) -> ET.Element:
    """Le balisage rendu doit être du XML bien formé (sans espace de noms déclaré : on l'ajoute)."""
    return ET.fromstring(svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1))


def line(**kwargs):
    base = dict(
        series=[Series("Solo", [(0, 0), (10, 100)], stops=("var(--blue)", "var(--mint)"))],
        size=(1000, 500),
        x_domain=(0, 10),
        y_domain=(0, 100),
        uid="t",
        title="Rang",
        desc="Courbe",
        margin=(100, 50, 50, 50),
    )
    base.update(kwargs)
    return line_chart(**base)


# ---------- line_chart ----------


def test_les_points_sont_projetes_sur_la_zone_de_trace():
    root = parse(line())
    path = root.find(".//s:path[@class='ch-line']", NS).get("d")
    # x : 0 -> marge gauche (100), 10 -> 1000 - 50 ; y : 0 -> bas (450), 100 -> haut (50)
    assert path == "M100.0,450.0 L950.0,50.0"


def test_accessibilite_titre_description_et_role():
    root = parse(line())
    assert root.get("role") == "img"
    assert root.find("s:title", NS).text == "Rang"
    assert root.find("s:desc", NS).text == "Courbe"
    labelled = root.get("aria-labelledby").split()
    assert [root.find(f".//*[@id='{i}']", NS).tag.split("}")[1] for i in labelled] == [
        "title",
        "desc",
    ]


def test_les_libelles_sont_echappes():
    svg = line(
        title="<script>alert(1)</script>",
        y_ticks=[Tick(50, "<b>Or</b>")],
        marks=[Mark(5, 50, "var(--rose)", "<img onerror=x>")],
        series=[Series("x", [(0, 0), (10, 10)], end_label="<i>Or II</i>")],
    )
    assert "<script>" not in svg and "<b>" not in svg and "<img" not in svg and "<i>" not in svg
    parse(svg)  # reste du XML valide
    assert "&lt;script&gt;" in svg


def test_une_courbe_plate_utilise_un_degrade_en_espace_utilisateur():
    """En `objectBoundingBox`, une ligne horizontale (boîte de hauteur nulle) ne serait pas dessinée."""
    svg = line(series=[Series("plat", [(0, 40), (10, 40)])])
    assert 'gradientUnits="userSpaceOnUse"' in svg
    assert "objectBoundingBox" not in svg


def test_une_serie_de_moins_de_deux_points_n_est_pas_tracee():
    root = parse(line(series=[Series("seul", [(1, 1)]), Series("vide", [])]))
    assert root.findall(".//s:path", NS) == []
    assert root.findall(".//s:linearGradient", NS) == []


def test_sans_serie_le_graphique_reste_valide():
    parse(line(series=[]))


def test_les_identifiants_de_degrade_dependent_de_l_uid():
    one, two = line(uid="a"), line(uid="b")
    ids = lambda svg: set(re.findall(r'id="([^"]+)"', svg))
    assert not ids(one) & ids(two)


def test_bandes_filets_et_graduations():
    root = parse(
        line(
            bands=[Band(0, 50, "var(--blue)"), Band(80, 500, "var(--mint)")],
            y_ticks=[Tick(0, "Zéro"), Tick(50, "Moitié", dash="4 5")],
            x_ticks=[Tick(0, "début"), Tick(10, "fin")],
        )
    )
    rects = root.findall(".//s:rect", NS)
    assert len(rects) == 2  # la seconde bande est bornée au domaine (80 -> 100)
    assert float(rects[1].get("height")) == pytest.approx(0.2 * 400)
    texts = [t.text for t in root.findall(".//s:text", NS)]
    assert texts == ["Zéro", "Moitié", "début", "fin"]
    assert "stroke-dasharray:4 5" in ET.tostring(root, encoding="unicode")


def test_aire_derniere_etiquette_et_repere():
    root = parse(
        line(
            series=[
                Series(
                    "s",
                    [(0, 10), (5, 60), (10, 90)],
                    area=True,
                    dots=True,
                    end_label="Émeraude II · 47 LP",
                )
            ],
            marks=[Mark(5, 60, "var(--gold)", "Tour")],
        )
    )
    assert len(root.findall(".//s:circle[@class='ch-dot']", NS)) == 2  # tous sauf le dernier
    assert root.find(".//s:circle[@class='ch-end']", NS) is not None
    assert "Émeraude II · 47 LP" in [t.text for t in root.findall(".//s:text", NS)]
    assert "Tour" in [t.text for t in root.findall(".//s:text", NS)]
    assert len(root.findall(".//s:path", NS)) == 2  # l'aire et la ligne


def test_le_trace_porte_ses_durees():
    svg = line(series=[Series("s", [(0, 0), (1, 1)], trace_ms=1500, delay_ms=200)])
    assert 'data-trace="1500" data-delay="200"' in svg


# ---------- sparkline ----------


def test_sparkline_borne_les_valeurs_au_domaine():
    svg = sparkline(
        [SparkLine([-9, 0, 9])], size=(190, 40), uid="s", title="Tendance", y_domain=(-2, 2), pad=0
    )
    path = parse(svg).find(".//s:path", NS).get("d")
    assert path == "M0.0,40.0 L95.0,20.0 L190.0,0.0"


def test_sparkline_pointille_sans_trace_et_ligne_de_base():
    root = parse(
        sparkline(
            [SparkLine([1, 2, 3]), SparkLine([3, 2, 1], dashed=True)],
            size=(190, 40),
            uid="s",
            title="t",
            baseline=2,
        )
    )
    solid, dashed = root.findall(".//s:path", NS)
    assert solid.get("data-trace") and not dashed.get("data-trace")
    assert "stroke-dasharray:4 4" in dashed.get("style")
    assert root.find(".//s:line[@class='spark-base']", NS) is not None


def test_sparkline_sans_valeur_ni_un_seul_point():
    for lines in ([], [SparkLine([])], [SparkLine([5])]):
        root = parse(sparkline(lines, size=(100, 20), uid="s", title="t"))
        assert root.findall(".//s:path", NS) == []


# ---------- bar_chart ----------


def test_histogramme_divergent_hauteurs_et_sens():
    root = parse(bar_chart([10, -5, 0], size=(300, 100), uid="b", title="LP", desc="d", gap=0))
    up, down, zero = root.findall(".//s:rect", NS)
    assert up.get("class") == "ch-bar ch-pos" and down.get("class") == "ch-bar ch-neg"
    assert float(up.get("height")) == pytest.approx(48.0)  # milieu 50 - 2
    assert float(down.get("height")) == pytest.approx(24.0)
    assert float(up.get("y")) + float(up.get("height")) == pytest.approx(50.0)
    assert float(down.get("y")) == pytest.approx(50.0)
    assert float(zero.get("height")) == 1.0  # une valeur nulle reste visible


def test_histogramme_vide_et_libelles():
    parse(bar_chart([], size=(300, 100), uid="b", title="t", desc="d"))
    svg = bar_chart([1.5], size=(100, 50), uid="b", title="t", desc="d", labels=["<x>"])
    assert "&lt;x&gt;" in svg


# ---------- reliability_chart ----------


def test_diagramme_de_fiabilite():
    root = parse(
        reliability_chart(
            [(0.25, 0.2, 4), (0.55, 0.6, 16), (0.85, 0.9, 1)],
            size=(520, 420),
            uid="r",
            title="Fiabilité",
            desc="d",
        )
    )
    circles = root.findall(".//s:circle", NS)
    radii = [float(c.get("r")) for c in circles]
    assert radii[1] == max(radii) and radii[2] < radii[1]  # le rayon suit le nombre de parties
    assert root.find(".//s:line[@class='ch-diag']", NS) is not None
    assert "prédit 55 %, observé 60 %, 16 parties" in [c.find("s:title", NS).text for c in circles]


def test_diagramme_de_fiabilite_sans_point():
    parse(reliability_chart([], size=(520, 420), uid="r", title="t", desc="d"))


# ---------- diverging ----------


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, (50.0, 25.0)),
        (-1.0, (25.0, 25.0)),
        (9.0, (50.0, 50.0)),
        (-9.0, (0.0, 50.0)),
        (0, (50, 0)),
    ],
)
def test_barre_divergente(value, expected):
    assert diverging(value, scale=2.0) == pytest.approx(expected)


def test_barre_divergente_echelle_nulle():
    assert diverging(1.0, scale=0) == (50.0, 50.0)
