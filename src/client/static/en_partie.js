// Écran « En partie » (SPEC-24 tâche 108) : le corps de la page est relu (`/en-partie/stage`) à chaque
// événement du sujet `ingame` du bus. La pastille de phase de la barre de titre (SPEC-25) suit le sujet
// `phase` sur toutes les pages, sans jamais changer de page toute seule. Lecture seule : aucun POST.
(() => {
  let busy = false;
  let again = false;

  const body = () => document.getElementById("en-partie-body");

  function pill(payload) {
    const element = document.getElementById("tb-phase");
    if (!element || !payload) return;
    const labels = JSON.parse(element.dataset.labels);
    const kind = payload.kind in labels ? payload.kind : "unknown";
    element.classList.toggle("chip-closed", kind === "closed");
    element.classList.toggle("chip-ok", kind !== "closed");
    element.querySelector("#tb-phase-text").textContent = labels[kind];
  }

  async function refresh() {
    if (!body()) return; // une autre page est affichée
    if (busy) {
      again = true;
      return;
    }
    busy = true;
    try {
      const response = await fetch("/en-partie/stage");
      if (response.ok && body()) body().innerHTML = await response.text();
    } catch (error) {
      /* serveur indisponible : le prochain événement relance */
    } finally {
      busy = false;
      if (again) {
        again = false;
        refresh();
      }
    }
  }

  window.addEventListener("load", () => {
    Sse.open(["ingame", "phase"], (name, payload) => (name === "phase" ? pill(payload) : refresh()));
  });

  window.EnPartie = { refresh };
})();
