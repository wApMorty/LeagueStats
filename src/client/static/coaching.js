// Écrans du coaching (SPEC-21 tâches 51 à 95) : animations qui n'ont pas de primitive dans motion.js.
// `data-bar="y|x"` : une barre qui pousse depuis son pied (ressort) ; `data-row` : une ligne qui entre
// par la gauche ; `data-stack` : un événement qui tombe sur la pile. `data-delay` en ms. En mode
// Réduit, rien ne joue : les éléments restent à leur place finale. Le sceau de la revue de partie
// (`.game-seal`) est apposé à l'arrivée sur la page, une seule fois : mint et or pour une victoire, rose
// et cuivre pour une défaite ; en Réduit il est posé tout de suite, sans particules ni secousse.
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

  const stage = (root) => {
    const seal = root.querySelector?.(".game-seal [data-seal]");
    if (!seal || seal.__staged) return;
    seal.__staged = true;
    const options = Motion.opts();
    const C = Motion.C;
    const colors = seal.classList.contains("loss") ? [C.rose, C.copper, C.white] : [C.mint, C.gold, C.white];
    const page = seal.closest(".page");
    setTimeout(() => {
      Motion.seal(seal.parentElement, { ...options, target: page, colors });
      if (!options.reduced) setTimeout(() => Motion.shake(page, 9, 460), 440 / options.sp);
    }, 150 / options.sp);
  };

  document.addEventListener("htmx:load", (event) => {
    play(event.target);
    stage(event.target);
  });

  // Une partie vient d'être capturée (sujet `game_captured`, SPEC-21 §4.5) : la fenêtre bascule sur la revue.
  // Un lien caché dans #view passe par la navigation htmx de la coque, donc par la transition de page et
  // l'historique. Jamais en pleine draft : un champ select en cours ne doit pas être arraché à l'écran ;
  // la revue reste à une entrée de navigation (« Post-game »).
  window.Sse?.open("game_captured", (name) => {
    const view = document.getElementById("view");
    if (name !== "game_captured" || !view || document.getElementById("draft")) return;
    const link = Object.assign(document.createElement("a"), { href: "/postgame", hidden: true });
    view.appendChild(link);
    htmx.process(link);
    link.click();
    link.remove();
  });
})();
