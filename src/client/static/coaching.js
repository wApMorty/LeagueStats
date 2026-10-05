// Écrans du coaching (SPEC-21 tâches 51 à 95) : animations qui n'ont pas de primitive dans motion.js.
// `data-bar="y|x"` : une barre qui pousse depuis son pied (ressort) ; `data-row` : une ligne qui entre
// par la gauche ; `data-stack` : un événement qui tombe sur la pile. `data-delay` en ms. En mode
// Réduit, rien ne joue : les éléments restent à leur place finale.
(() => {
  const RESSORT = "cubic-bezier(.2,.8,.2,1)";
  const play = (root) => {
    const { reduced, sp } = Motion.opts();
    if (reduced || !root.querySelectorAll) return;
    const delay = (el) => (+el.dataset.delay || 0) / sp;
    root.querySelectorAll("[data-bar]").forEach((el) => {
      const scale = el.dataset.bar === "x" ? "scaleX" : "scaleY";
      el.animate([{ transform: `${scale}(0)` }, { transform: `${scale}(1)` }], {
        duration: 700 / sp, delay: delay(el), easing: RESSORT, fill: "backwards",
      });
    });
    root.querySelectorAll("[data-row]").forEach((el) =>
      el.animate([{ opacity: 0, transform: "translateX(-14px)" }, { opacity: 1, transform: "none" }], {
        duration: 600 / sp, delay: delay(el), easing: Motion.E.entree, fill: "backwards",
      }),
    );
    root.querySelectorAll("[data-stack]").forEach((el) =>
      el.animate(
        [
          { opacity: 0, transform: "translateY(-26px)" },
          { opacity: 1, transform: "translateY(2px)", offset: 0.75 },
          { opacity: 1, transform: "none" },
        ],
        { duration: 520 / sp, delay: delay(el), easing: RESSORT, fill: "backwards" },
      ),
    );
  };
  document.addEventListener("htmx:load", (event) => play(event.target));
})();
