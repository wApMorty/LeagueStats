// Partie trouvée (SPEC-21 tâche 93) : l'overlay de la coque pendant la file trouvée, et la pastille
// « Champ select en cours » de la barre de titre. L'état vient du serveur (`/found/state`), relu à chaque
// événement du WebSocket LCU relayé par le bus (sujet `lcu`) et toutes les 4 s en secours.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const POLL_MS = 4000;
  const LEAVE_MESSAGE = "Un joueur n'a pas accepté · retour en file";
  const RUNES = "ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛇ ᛈ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛞ ᛟ ";
  const RING = 2199.1; // circonférence de l'anneau de compte à rebours (r = 350)

  // Overlay : { el, until, total, timer, timeouts, holdMax, enterWait } puis, selon l'étape, `accepted`
  // (séquence lancée, une seule fois), `settled` (séquence finie : « held »), `entering` (effondrement vers
  // la draft) et `leaving` (fondu de sortie). Table de décision : `apply`.
  let overlay = null;
  let dismissed = false; // garde-fou échu pendant ce ready-check : on ne rouvre pas l'overlay
  let busy = false;

  const post = (path) =>
    fetch(path, { method: "POST", headers: { [meta("token-header")]: meta("session-token") } })
      .then(async (response) => ({ ok: response.ok, body: await response.json().catch(() => ({})) }))
      .catch(() => ({ ok: false, body: { detail: "Serveur indisponible" } }));

  /** Ouvre /draft ; faux si on y est déjà (rien ne se charge). */
  function goDraft() {
    if (location.pathname === "/draft") return false;
    history.pushState({}, "", "/draft");
    htmx.ajax("GET", "/draft", { target: "#view", select: "#view", swap: "outerHTML" });
    return true;
  }

  // ---------- pastille de la barre de titre ----------

  function pill(inChampSelect) {
    const element = document.getElementById("tb-center");
    if (element) element.hidden = !inChampSelect;
  }

  // ---------- overlay ----------

  function markup(auto) {
    return `
<div class="f-pillar" data-pillar></div>
<div class="f-halo" data-glow="2400"></div>
<div class="f-core" data-core>
  <svg class="f-layer" data-spin="60" viewBox="-360 -360 720 720" aria-hidden="true">
    <circle data-trace="1100" r="350" class="f-ring-a"/>
    <path id="qfRing" d="M0,-332 A332,332 0 1,1 0,332 A332,332 0 1,1 0,-332" fill="none"/>
    <text data-fade data-delay="400" data-ring="2086" class="f-ring-text"><textPath href="#qfRing">${RUNES.repeat(4)}</textPath></text>
    <circle data-trace="1100" data-delay="150" r="314" class="f-ring-b"/>
  </svg>
  <svg class="f-layer" data-spin="-90" viewBox="-360 -360 720 720" aria-hidden="true">
    <path data-glow="1800" d="M0,-290 L170.5,234.6 L-275.8,-89.6 L275.8,-89.6 L-170.5,234.6 Z" class="f-star-glow"/>
    <path data-trace="1500" data-delay="300" d="M0,-290 L170.5,234.6 L-275.8,-89.6 L275.8,-89.6 L-170.5,234.6 Z" class="f-star"/>
    <circle data-trace="1200" data-delay="500" r="290" class="f-circle"/>
    <circle data-trace="1000" data-delay="700" r="112" class="f-circle-in"/>
    <path data-trace="1500" data-delay="450" d="M0,290 L-170.5,-234.6 L275.8,89.6 L-275.8,89.6 L170.5,-234.6 Z" class="f-star-inv"/>
  </svg>
  <svg class="f-layer" viewBox="-360 -360 720 720" aria-hidden="true">
    <circle r="350" class="f-track"/>
    <circle r="350" class="f-count" id="f-count"/>
  </svg>
  <div class="f-shock" data-shock></div><div class="f-shock f-shock-b" data-shock></div>
  <div class="f-text">
    <div class="f-kicker" data-rise data-delay="500">Classée solo/duo</div>
    <div class="f-title" id="f-title" data-pop data-spell data-delay="1300">Partie trouvée</div>
    <div class="f-sub" id="f-sub" data-rise data-delay="800"></div>
  </div>
</div>
<div class="f-actions" data-rise data-delay="900">
  <div class="f-buttons" id="f-buttons">
    <button type="button" class="f-accept" id="f-accept">Accepter</button>
    <button type="button" class="f-decline" id="f-decline">Refuser</button>
  </div>
  <span class="f-auto"${auto ? "" : " hidden"}>Auto-accept du Live Coach actif · acceptation automatique</span>
</div>`;
  }

  function show(state) {
    const el = document.createElement("div");
    el.className = "f-overlay";
    el.setAttribute("role", "alertdialog");
    el.setAttribute("aria-label", "Partie trouvée");
    el.innerHTML = markup(state.auto_accept);
    document.body.appendChild(el);
    overlay = { el, accepted: false, timeouts: [], until: performance.now() + state.remaining * 1000, total: state.total };
    el.querySelector("#f-accept").onclick = accept;
    el.querySelector("#f-decline").onclick = decline;
    overlay.timer = setInterval(tick, 250);
    tick();
    Motion.intro(el, Motion.opts());
    Motion.ambient(el, Motion.opts());
    if (Motion.opts().reduced) return;
    // Convergence de 90 runes, pilier de lumière, puis impact menthe / magenta et explosion.
    const [cx, cy] = Motion.center(el.querySelector("[data-core]"));
    const C = Motion.C;
    Motion.converge(cx, cy, { n: 90, radius: 1100, life: 1500, colors: [C.mint, C.gold] });
    el.querySelector("[data-pillar]").animate([{ transform: "scaleY(0)", opacity: 0 }, { transform: "scaleY(1)", opacity: 1 }], { duration: 900, delay: 1000, easing: Motion.E.entree, fill: "backwards" });
    later(1400, () => {
      Motion.impact(cx, cy, { color: C.mint, comp: C.magenta });
      later(60, () => {
        Motion.burst(cx, cy, { n: 200, speed: 13, glyphs: 22, ringR: 560, ringW: 9, colors: [C.mint, C.gold, C.magenta, C.white] });
        Motion.flash(C.magenta, 0.45, 600);
        Motion.shake(document.querySelector(".view"), 9, 460);
      });
    });
  }

  function later(ms, fn) {
    if (!overlay) return;
    overlay.timeouts.push(setTimeout(fn, ms));
  }

  function tick() {
    if (!overlay || overlay.accepted) return;
    const left = Math.max(0, overlay.until - performance.now()) / 1000;
    overlay.el.querySelector("#f-count").style.strokeDashoffset = (RING * (1 - Math.min(1, left / overlay.total))).toFixed(1);
    overlay.el.querySelector("#f-sub").textContent = `${Math.ceil(left)} s pour répondre`;
  }

  function close() {
    if (!overlay) return;
    clearInterval(overlay.timer);
    overlay.timeouts.forEach(clearTimeout);
    overlay.el.remove();
    overlay = null;
  }

  /** Acceptation (la mienne, ou celle du Live Coach) : impact, explosion, anneaux ×9, puis l'overlay est tenu. */
  function acceptedSequence() {
    if (!overlay || overlay.accepted) return;
    overlay.accepted = true;
    overlay.acceptedAt = performance.now();
    const el = overlay.el;
    el.querySelector("#f-title").textContent = "Acceptée";
    el.querySelector("#f-sub").textContent = "En attente des autres joueurs";
    el.querySelector("#f-buttons").hidden = true;
    el.querySelector("#f-count").style.visibility = "hidden";
    const reduced = Motion.opts().reduced;
    if (!reduced) {
      const C = Motion.C;
      Motion.seal(el, { ...Motion.opts(), colors: [C.mint, C.gold, C.white, C.copper] });
      const [cx, cy] = Motion.center(el.querySelector("[data-core]"));
      Motion.impact(cx, cy, { color: C.mint, comp: C.magenta, target: document.querySelector(".view"), frameMs: 60 });
      later(90, () => {
        Motion.burst(cx, cy, { n: 340, speed: 22, glyphs: 46, ringR: 1200, ringW: 12, ringLife: 1050, life: 1600, colors: [C.mint, C.white, C.gold, C.magenta] });
        Motion.flash(C.white, 0.8, 720);
        Motion.shake(document.querySelector(".view"), 16, 560);
      });
      el.querySelectorAll("[data-spin]").forEach((svg) => svg.getAnimations().forEach((animation) => (animation.playbackRate = 9)));
    }
    later(reduced ? 0 : 1200, settle);
  }

  /** Fin de la séquence : les anneaux reprennent leur vitesse, l'overlay attend la draft. */
  function settle() {
    overlay.settled = true;
    overlay.el.querySelectorAll("[data-spin]").forEach((svg) => svg.getAnimations().forEach((animation) => (animation.playbackRate = 1)));
    if (overlay.enterAfter) enter();
  }

  /** Le champ select s'ouvre : /draft se charge sous l'overlay, qui s'effondre ensuite et se retire. */
  function enter() {
    if (overlay.entering) return;
    if (!overlay.settled) return void (overlay.enterAfter = true);
    overlay.entering = true;
    clearInterval(overlay.timer);
    const el = overlay.el;
    if (Motion.opts().reduced) {
      goDraft();
      return close();
    }
    let started = false;
    const collapse = () => {
      if (started) return;
      started = true;
      document.removeEventListener("htmx:load", onLoad);
      el.animate(
        [{ opacity: 1, transform: "scale(1)", filter: "brightness(1)" }, { opacity: 0, transform: "scale(.2) rotate(160deg)", filter: "brightness(3)" }],
        { duration: 560, easing: "cubic-bezier(.6,0,.8,.2)", fill: "forwards" },
      ).onfinish = close;
    };
    const onLoad = (event) => event.target.id === "view" && collapse();
    if (!goDraft()) return collapse();
    document.addEventListener("htmx:load", onLoad);
    later(overlay.enterWait * 1000, collapse);
  }

  async function accept() {
    const { ok, body } = await post("/found/accept");
    if (ok) acceptedSequence();
    else if (overlay) overlay.el.querySelector("#f-sub").textContent = body.detail || "Réponse refusée";
  }

  async function decline() {
    const { ok, body } = await post("/found/decline");
    if (!ok && overlay) return void (overlay.el.querySelector("#f-sub").textContent = body.detail || "Réponse refusée");
    leave();
  }

  /** La file n'est plus trouvée (refus, esquive, expiration) : l'overlay s'efface, avec un message si on en donne un. */
  function leave(message) {
    if (!overlay || overlay.leaving) return;
    overlay.leaving = true;
    const el = overlay.el;
    clearInterval(overlay.timer);
    overlay.timeouts.forEach(clearTimeout);
    if (message) el.querySelector("#f-sub").textContent = message;
    if (Motion.opts().reduced) return close();
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 400, fill: "forwards" }).onfinish = close;
  }

  // ---------- état ----------

  /** Table de décision de l'overlay (SPEC-26 §4.1), évaluée à chaque état lu. */
  function apply(state) {
    pill(state.phase === "ChampSelect");
    if (state.phase !== "ReadyCheck") dismissed = false;
    const check = state.ready_check;
    const found = state.phase === "ReadyCheck" && check?.state === "InProgress" && check.response !== "Declined";
    if (!overlay) {
      if (found && !dismissed) {
        show(state);
        if (check.response === "Accepted") acceptedSequence(); // auto-accept, ou page ouverte après l'acceptation
      }
      return;
    }
    overlay.holdMax = state.hold_max;
    overlay.enterWait = state.enter_wait;
    if (overlay.entering || overlay.leaving) return;
    if (state.phase === "ChampSelect") {
      acceptedSequence(); // le Live Coach a accepté avant nous : sans effet si déjà jouée
      enter();
    } else if (overlay.accepted) {
      // Tenu : après l'acceptation, seul compte que la phase reste `ReadyCheck` (le détail du ready-check ne compte plus).
      if (state.phase !== "ReadyCheck") leave(LEAVE_MESSAGE);
      else if (performance.now() - overlay.acceptedAt > overlay.holdMax * 1000) {
        dismissed = true;
        leave(LEAVE_MESSAGE);
      }
    } else if (found && check.response === "Accepted") acceptedSequence();
    else if (!found) leave();
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch("/found/state");
      if (response.ok) apply(await response.json());
    } catch (error) {
      /* serveur indisponible : le prochain événement relance */
    } finally {
      busy = false;
    }
  }

  // Bascule vers « En partie » (SPEC-26) : au passage de la famille de phase `draft` à `game`, depuis n'importe
  // quelle page. Le premier événement vu n'a pas de précédent : jamais d'arrachage d'une page ouverte en pleine partie.
  let lastKind = null;
  function watchPhase(name, payload) {
    const kind = payload?.kind;
    if (!kind) return;
    const switching = lastKind === "draft" && kind === "game" && location.pathname !== "/en-partie";
    lastKind = kind;
    if (!switching) return;
    if (window.Transition) Transition.go("/en-partie");
    else {
      history.pushState({}, "", "/en-partie");
      htmx.ajax("GET", "/en-partie", { target: "#view", select: "#view", swap: "outerHTML" });
    }
  }

  window.addEventListener("load", () => {
    Sse.open("phase", watchPhase);
    Sse.open("lcu", (name, payload) => {
      if (/gameflow|ready-check|champ-select/.test(payload?.uri ?? "")) refresh();
    }, { onOpen: refresh });
    setInterval(refresh, POLL_MS);
    document.addEventListener("click", (event) => {
      if (event.target.closest("#tb-center")) goDraft();
    });
    refresh();
  });

  window.Found = { refresh };
})();
