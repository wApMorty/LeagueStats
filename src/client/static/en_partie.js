// Écran « En partie » (SPEC-24 tâche 108) : le corps de la page est relu (`/en-partie/stage`) à chaque
// événement du sujet `ingame` du bus ; la pastille de la barre de titre apparaît pendant la partie sur toutes
// les pages, sans jamais changer de page toute seule. Lecture seule : aucun POST.
(() => {
  let busy = false;
  let again = false;

  const body = () => document.getElementById("en-partie-body");

  function pill(live) {
    const element = document.getElementById("tb-ingame");
    if (element) element.hidden = !live;
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
    Sse.open("ingame", (name, payload) => {
      pill(payload?.state === "live");
      refresh();
    });
  });

  window.EnPartie = { refresh };
})();
