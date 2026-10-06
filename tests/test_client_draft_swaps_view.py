"""SPEC-24 tâche 104 : boutons d'échange sur les légendes, bandeau d'une demande reçue, annulation.

Hermétique : bus en mémoire, snapshots fabriqués (les états `AVAILABLE`, `SENT`, `RECEIVED`, `INVALID`
sont ceux du relevé). Aucun client LoL, aucun test d'interface réel.
"""

import re
from pathlib import Path

import pytest

from tests.test_client_draft import (
    Tree,
    assets,
    bus,
    client,
    pick_snapshot,
)  # noqa: F401  (fixtures)


def swap(kind, cell, state):
    return {"kind": kind, "cell_id": cell, "state": state}


def stage(client, bus, swaps=(), advice=(), **overrides):  # noqa: F811
    bus.publish("draft", pick_snapshot(swaps=list(swaps), swap_advice=list(advice), **overrides))
    response = client.get("/draft/stage")
    assert response.status_code == 200
    return response.text


def caption_of(html, name):
    block = html.split(f'<div class="d-name">{name}</div>')[1].split("</div>\n</div>")[0]
    return block


def test_echanges_demandables_avec_le_gain_du_coach(client, bus):  # noqa: F811
    advice = [
        {
            "kind": "position",
            "cell_id": 1,
            "champion": "Alistar",
            "gain_pts": 1.234,
            "reason": "x",
        }
    ]
    html = stage(
        client,
        bus,
        [swap("pick_order", 1, "AVAILABLE"), swap("position", 1, "AVAILABLE")],
        advice,
    )
    caption = caption_of(html, "Alistar")
    assert 'data-swap="pick_order:request:1"' in caption and "⇄ ordre" in caption
    assert 'data-swap="position:request:1"' in caption and "⇄ rôle +1,2 pts" in caption
    assert "le modèle estime +1,2 pts" in caption


def test_sans_gain_le_bouton_de_role_n_annonce_rien(client, bus):  # noqa: F811
    html = stage(client, bus, [swap("position", 2, "AVAILABLE")])
    caption = caption_of(html, "Jinx")
    assert "⇄ rôle<" in caption and "pts" not in caption


def test_demande_envoyee_s_annule(client, bus):  # noqa: F811
    html = stage(client, bus, [swap("pick_order", 1, "SENT"), swap("position", 1, "INVALID")])
    caption = caption_of(html, "Alistar")
    assert 'data-swap="pick_order:cancel:1"' in caption and "✕ ordre" in caption
    assert "position:" not in caption  # INVALID : rien à offrir


def test_demande_recue_bandeau_accepter_refuser(client, bus):  # noqa: F811
    snapshot = pick_snapshot(swaps=[swap("pick_order", 1, "RECEIVED")])
    snapshot["allies"][1]["pick_order"], snapshot["allies"][0]["pick_order"] = 4, 1
    bus.publish("draft", snapshot)
    html = client.get("/draft/stage").text
    banner = html.split('class="d-swap-banner"')[1].split("</div>\n{% ")[0]
    assert "Alistar te propose d&#39;échanger son ordre de pick (n° 4 contre ton n° 1)" in banner
    assert (
        'data-swap="pick_order:accept:1"' in banner and 'data-swap="pick_order:decline:1"' in banner
    )
    assert 'data-swap="pick_order:request:1"' not in caption_of(html, "Alistar")


def test_demande_de_role_recue_porte_le_gain(client, bus):  # noqa: F811
    advice = [
        {"kind": "position", "cell_id": 2, "champion": "Jinx", "gain_pts": 2.0, "reason": "x"}
    ]
    html = stage(client, bus, [swap("position", 2, "RECEIVED")], advice)
    assert "te propose d&#39;échanger vos rôles" in html and "+2,0 pts" in html


def test_aucun_echange_aucun_bouton_aucun_bandeau(client, bus):  # noqa: F811
    html = stage(client, bus)
    assert "data-swap" not in html and "d-swap-banner" not in html


def test_le_bandeau_et_les_boutons_respectent_le_contrat_de_synchronisation(
    client, bus
):  # noqa: F811
    html = stage(
        client,
        bus,
        [swap("pick_order", 1, "RECEIVED"), swap("position", 2, "AVAILABLE")],
    )
    tree = Tree()
    tree.feed(f"<div data-sync>{html}</div>")
    assert tree.orphans == []
    sigs = lambda text: re.findall(r'data-sig="([^"]+)"', text)  # noqa: E731
    other = stage(
        client, bus, [swap("pick_order", 1, "AVAILABLE"), swap("position", 2, "AVAILABLE")]
    )
    assert sigs(html) != sigs(other)  # un changement d'état change l'empreinte


def test_le_front_ne_donne_jamais_l_id_de_l_echange():
    source = (Path(__file__).parent.parent / "src" / "client" / "static" / "draft.js").read_text(
        "utf-8"
    )
    call = re.search(r"post\(`/draft/swap/[^`]*`, \{([^}]*)\}\)", source)
    assert call and call.group(1).strip() == "cell_id: cell"
