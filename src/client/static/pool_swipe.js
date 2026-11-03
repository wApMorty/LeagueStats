// Écran Suggestions de pool (SPEC-49 tâche 244) : glisser la carte ou utiliser les flèches gauche et droite.
// Le script ne fait que cliquer le bouton de la carte (`data-swipe="take|pass"`) : l'écriture reste celle des
// routes. Délégation sur `document` : il survit aux échanges htmx de `#swipe-body` et ne fait rien hors de
// l'écran (pas de `.swipe-card`). L'animation de sortie ne joue que hors Motion réduit (`Motion.opts()`).
(() => {
  let drag = null; // { card, id, startX, dx } : glisser au pointeur en cours
  let busy = false; // un swipe est parti : on attend le remplacement de la carte par htmx

  const cardOf = (node) => node?.closest?.("#swipe-body .swipe-card") ?? null;
  const current = () => document.querySelector("#swipe-body .swipe-card");
  const reduced = () => !window.Motion || Motion.opts().reduced;

  // Déclenche le bouton du côté demandé. Retourne false si rien ne part (pas de bouton, swipe en cours).
  function swipe(card, side) {
    const button = document.querySelector(
      `#swipe-body [data-swipe="${side === "right" ? "take" : "pass"}"]`
    );
    if (!button || busy) return false;
    busy = true;
    if (reduced() || !card.animate) {
      button.click();
      return true;
    }
    const sign = side === "right" ? 1 : -1;
    const out = card.animate(
      [
        { transform: card.style.transform || "none", opacity: 1 },
        { transform: `translateX(${sign * 120}vw) rotate(${sign * 18}deg)`, opacity: 0 },
      ],
      { duration: 220, easing: "ease-in", fill: "forwards" }
    );
    out.onfinish = () => button.click();
    return true;
  }

  document.addEventListener("pointerdown", (event) => {
    const card = cardOf(event.target);
    if (!card || !event.isPrimary || event.button !== 0 || busy) return;
    drag = { card, id: event.pointerId, startX: event.clientX, dx: 0 };
    card.setPointerCapture?.(event.pointerId);
  });

  document.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    drag.dx = event.clientX - drag.startX;
    drag.card.classList.add("is-dragging");
    drag.card.style.transform = `translateX(${drag.dx}px) rotate(${drag.dx / 20}deg)`;
  });

  // Relâchement : au-delà de `data-drag` (posé par le gabarit depuis POOL_SWIPE_DRAG_PX), la carte part ;
  // sinon elle revient à sa place.
  const release = (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const { card, dx } = drag;
    drag = null;
    card.classList.remove("is-dragging");
    const sent = Math.abs(dx) >= Number(card.dataset.drag) && swipe(card, dx > 0 ? "right" : "left");
    if (!sent) card.style.transform = "";
  };
  document.addEventListener("pointerup", release);
  document.addEventListener("pointercancel", release);

  // Flèches : gauche passe, droite prend. Ignorées dans un champ de saisie et avec une touche de modification.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || busy || drag) return;
    if (event.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    const card = current();
    if (!card) return;
    event.preventDefault();
    swipe(card, event.key === "ArrowRight" ? "right" : "left");
  });

  // Le remplacement de la carte (ou un échec) débloque le swipe suivant.
  for (const name of ["htmx:afterSettle", "htmx:sendError", "htmx:responseError"]) {
    document.addEventListener(name, () => {
      busy = false;
    });
  }
})();
