// Coque du client LeagueStats (SPEC-21 tâches 68, 69 et 84) : jeton de session, réglage Motion, boutons
// de la barre de titre, redimensionnement par poignées. La classe `no-chrome` (barre de titre et poignées
// masquées) n'est retirée que si pywebview annonce une fenêtre sans bordure : en navigateur de
// repli ou en fenêtre standard, le cadre est celui du système.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const root = document.documentElement;

  // Toute requête htmx porte le jeton injecté dans la page (SPEC-21 §4.7).
  document.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers[meta("token-header")] = meta("session-token");
  });

  // Braises : montantes en continu (0,35 par image) sauf en mode Réduit, qui coupe tout.
  const EMBER_RATE = 0.35;
  const syncEmbers = () => Motion.embers(Motion.opts().reduced ? 0 : EMBER_RATE);
  syncEmbers();
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", syncEmbers);

  // Réglage Motion : appliqué tout de suite ; le `hx-post` du bouton le mémorise (user_prefs.json).
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".seg [data-mode]");
    if (!button) return;
    root.dataset.motion = button.dataset.mode;
    syncEmbers();
    button.parentElement.querySelectorAll("[data-mode]").forEach((other) =>
      other.setAttribute("aria-pressed", String(other === button)),
    );
  });

  // La pastille du client LoL est rechargée toutes les quelques secondes : sa pulsation se cale
  // sur l'horloge du document, sinon elle repartirait de zéro à chaque rechargement.
  // Chaque fragment chargé (page, pastille, écran de draft…) joue ses animations `data-*`.
  document.addEventListener("htmx:load", (event) => {
    Motion.intro(event.target, Motion.opts());
    Motion.ambient(event.target, Motion.opts());
    event.target.getAnimations?.({ subtree: true }).forEach((animation) => {
      if (animation.animationName === "pulse") animation.startTime = 0;
    });
  });

  const ready = new Promise((resolve) =>
    window.pywebview ? resolve() : addEventListener("pywebviewready", resolve, { once: true }),
  );

  ready.then(async () => {
    const api = pywebview.api;
    if (!(await api.frameless())) return; // fenêtre standard : le cadre est celui de Windows
    root.classList.remove("no-chrome");

    document.getElementById("tb-min").onclick = () => api.minimize();
    document.getElementById("tb-max").onclick = () => api.toggle_maximize();
    document.getElementById("tb-close").onclick = () => api.close();
    document.getElementById("titlebar-drag").ondblclick = () => api.toggle_maximize();

    // Une poignée tient le bord opposé fixe : est pour la gauche, sud pour le haut. Le pointeur
    // est capturé pour que le glissement continue hors de la fenêtre.
    document.querySelectorAll(".resize-handle").forEach((handle) => {
      const edge = handle.dataset.edge;
      const dx = edge.includes("e") ? 1 : edge.includes("w") ? -1 : 0;
      const dy = edge.includes("s") ? 1 : edge.includes("n") ? -1 : 0;
      let start = null;
      let want = null;
      let busy = false;
      // Un seul appel Python à la fois ; la dernière taille demandée n'est jamais perdue.
      const flush = () => {
        const { width, height } = want;
        want = null;
        busy = true;
        api.resize(width, height, dx < 0, dy < 0).finally(() => {
          busy = false;
          if (want) flush();
        });
      };
      handle.addEventListener("pointerdown", (event) => {
        handle.setPointerCapture(event.pointerId);
        start = { w: innerWidth, h: innerHeight, x: event.screenX, y: event.screenY };
      });
      handle.addEventListener("pointermove", (event) => {
        if (!start) return;
        want = {
          width: start.w + dx * (event.screenX - start.x),
          height: start.h + dy * (event.screenY - start.y),
        };
        if (!busy) flush();
      });
      const stop = () => (start = null);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    });
  });
})();
