// Transition de page « signature » (SPEC-21 tâche 94, README du handoff, « Moments signature » 1) : à chaque
// navigation htmx, le contenu s'assombrit pendant qu'un cercle runique se trace et que 44 runes convergent,
// le cercle implose, puis une onde de choc ouvre la nouvelle page par un `clip-path` circulaire. Elle
// remplace le fondu de View Transitions.
//
// htmx retient le remplacement pendant `swap:<ms>` (attribut `hx-swap` de #view, posé ici selon le réglage
// Motion) : c'est la durée de la première moitié. En mode Réduit : aucun délai, changement instantané.
// L'overlay ne capte jamais les clics ; un nouveau clic relance la transition au lieu d'être perdu.
(() => {
  const config = JSON.parse(document.querySelector('meta[name="page-transition"]')?.content ?? "{}");
  const RING = "ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛇ ᛈ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛞ ᛟ ".repeat(2);

  let veil = null;
  let pending = null; // { fromDraft, timers } pendant une navigation
  const view = () => document.getElementById("view");

  function syncSwap() {
    view()?.setAttribute("hx-swap", Motion.opts().reduced ? "outerHTML" : `outerHTML swap:${config.swap}ms`);
  }

  function ensureVeil() {
    if (veil?.isConnected) return veil;
    veil = document.createElement("div");
    veil.className = "tr-veil";
    veil.setAttribute("aria-hidden", "true");
    veil.innerHTML = `
<div class="tr-glow" data-vglow></div>
<svg class="tr-sig" data-vsig viewBox="-260 -260 520 520">
  <circle data-vtrace r="240" class="tr-a"/>
  <path id="veilRing" d="M0,-222 A222,222 0 1,1 0,222 A222,222 0 1,1 0,-222" fill="none"/>
  <text data-ring="1394" class="tr-text"><textPath href="#veilRing">${RING}</textPath></text>
  <circle data-vtrace r="204" class="tr-b"/>
  <path data-vtrace d="M0,-204 L119.9,165 L-194,-63 L194,-63 L-119.9,165 Z" class="tr-star"/>
  <path data-vtrace d="M0,204 L-119.9,-165 L194,63 L-194,63 L119.9,-165 Z" class="tr-star-inv"/>
  <circle data-vtrace r="74" class="tr-c"/>
</svg>`;
    document.body.appendChild(veil);
    return veil;
  }

  function clear() {
    if (!pending) return;
    pending.timers.forEach(clearTimeout);
    pending = null;
    if (veil) {
      veil.getAnimations({ subtree: true }).forEach((animation) => animation.cancel());
      veil.style.opacity = 0;
    }
    document.querySelector(".page")?.getAnimations().forEach((animation) => animation.cancel());
  }

  /** Première moitié : le contenu s'assombrit, le cercle se trace, les runes convergent, il implose. */
  function start() {
    clear();
    pending = { fromDraft: !!document.getElementById("draft"), timers: [] };
    const layer = ensureVeil();
    layer.style.opacity = 1;
    const sig = layer.querySelector("[data-vsig]");
    const glow = layer.querySelector("[data-vglow]");
    layer.getAnimations({ subtree: true }).forEach((animation) => animation.cancel());
    layer.querySelectorAll("[data-vtrace]").forEach((node, i) => Motion.trace(node, 520, i * 70, 1));
    Motion.fixRings(layer);
    const [cx, cy] = Motion.center(sig);
    Motion.converge(cx, cy, { n: config.runes, radius: 760, life: 760 });
    glow.animate([{ opacity: 0, transform: "scale(.4)" }, { opacity: 1, transform: "scale(1)" }], { duration: 620, easing: Motion.E.entree, fill: "forwards" });
    sig.animate(
      [{ transform: "rotate(-140deg) scale(.7)" }, { transform: "rotate(0deg) scale(1)", offset: 0.78 }, { transform: "rotate(120deg) scale(.06)" }],
      { duration: config.swap, easing: "cubic-bezier(.5,0,.75,0)", fill: "forwards" },
    );
    document.querySelector(".page")?.animate(
      [{ opacity: 1, transform: "scale(1)", filter: "brightness(1)" }, { opacity: 0, transform: "scale(.92)", filter: "brightness(.4)" }],
      { duration: config.darken, easing: Motion.E.standard, fill: "forwards" },
    );
    // Garde-fou : une navigation qui n'aboutit pas (réseau, serveur) ne laisse pas le voile en place.
    pending.timers.push(setTimeout(clear, config.swap + config.open + 4000));
  }

  /** Seconde moitié, la nouvelle page est en place : explosion, éclair, secousse, ouverture circulaire. */
  function arrive() {
    const { fromDraft } = pending;
    const layer = ensureVeil();
    const sig = layer.querySelector("[data-vsig]");
    const [cx, cy] = Motion.center(sig);
    const C = Motion.C;
    Motion.burst(cx, cy, { n: 240, speed: 17, glyphs: 30, ringR: 950, ringW: 10, ringLife: 950, life: 1400, colors: [C.copper, C.gold, C.violet, C.white] });
    Motion.flash(C.copper, 0.5, 560);
    Motion.shake(view(), 8, 460);
    layer.querySelector("[data-vglow]").animate([{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(4)" }], { duration: 700, easing: Motion.E.entree, fill: "forwards" });
    document.querySelector(".page")?.animate(
      [
        { clipPath: "circle(0% at 50% 50%)", filter: "brightness(2.2)" },
        { clipPath: "circle(40% at 50% 50%)", filter: "brightness(1.3)", offset: 0.45 },
        { clipPath: "circle(75% at 50% 50%)", filter: "brightness(1)" },
      ],
      { duration: config.open, easing: Motion.E.entree },
    );
    const nav = document.querySelector(".nav");
    if (fromDraft && nav) {
      // À la sortie de la draft (sans navigation), la navigation revient en glissant.
      nav.animate([{ transform: `translateX(-${config.nav_width}px)` }, { transform: "none" }], { duration: config.slide, easing: Motion.E.entree });
    }
    pending.timers.forEach(clearTimeout);
    pending.timers = [
      setTimeout(() => {
        layer.style.opacity = 0;
        pending = null;
      }, config.open),
    ];
  }

  document.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.requestConfig?.boosted && !Motion.opts().reduced) start();
  });
  document.addEventListener("htmx:load", (event) => {
    if (event.target.id !== "view") return;
    syncSwap();
    if (pending) arrive();
  });
  for (const name of ["htmx:sendError", "htmx:timeout", "htmx:sendAbort"]) document.addEventListener(name, clear);

  // Les réglages de Motion changent le délai de remplacement tout de suite.
  document.addEventListener("click", (event) => event.target.closest(".seg [data-mode]") && setTimeout(syncSwap));
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", syncSwap);
  addEventListener("DOMContentLoaded", syncSwap);
  syncSwap();
})();
