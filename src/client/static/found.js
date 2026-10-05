// Partie trouvée (SPEC-21 tâche 93) : l'overlay de la coque pendant la file trouvée, et la pastille
// « Champ select en cours » de la barre de titre. L'état vient du serveur (`/found/state`), relu à chaque
// événement du WebSocket LCU relayé par le bus (sujet `lcu`) et toutes les 4 s en secours.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const POLL_MS = 4000;
  const EXPECT_DRAFT_MS = 20000; // après « Accepter », le champ select suit dans ce délai
  const RUNES = "ᚠ ᚢ ᚦ ᚨ ᚱ ᚲ ᚷ ᚹ ᚺ ᚾ ᛁ ᛃ ᛇ ᛈ ᛉ ᛊ ᛏ ᛒ ᛖ ᛗ ᛚ ᛜ ᛞ ᛟ ";
  const RING = 2199.1; // circonférence de l'anneau de compte à rebours (r = 350)

  let overlay = null; // { el, until, total, accepted, timer, timeouts }
  let expectDraft = 0;
  let busy = false;

  const post = (path) =>
    fetch(path, { method: "POST", headers: { [meta("token-header")]: meta("session-token") } })
      .then(async (response) => ({ ok: response.ok, body: await response.json().catch(() => ({})) }))
      .catch(() => ({ ok: false, body: { detail: "Serveur indisponible" } }));

  function goDraft() {
    if (location.pathname === "/draft") return;
    history.pushState({}, "", "/draft");
    htmx.ajax("GET", "/draft", { target: "#view", select: "#view", swap: "outerHTML" });
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
  <span class="f-auto"${auto ? "" : " hidden"}>Auto-accept du Live Coach actif · acceptation automatique à 4 s</span>
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

  /** Acceptation (la mienne, ou celle du Live Coach) : impact, explosion, anneaux ×9, effondrement vers la draft. */
  function acceptedSequence() {
    if (!overlay || overlay.accepted) return;
    overlay.accepted = true;
    expectDraft = performance.now() + EXPECT_DRAFT_MS;
    const el = overlay.el;
    el.querySelector("#f-title").textContent = "Acceptée";
    el.querySelector("#f-sub").textContent = "Le cercle se referme · ouverture du champ select";
    el.querySelector("#f-buttons").hidden = true;
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
    later(reduced ? 0 : 1200, () => {
      const done = () => {
        close();
        if (expectDraft) refresh(); // le champ select est peut-être déjà là
      };
      if (reduced) return done();
      el.animate(
        [{ opacity: 1, transform: "scale(1)", filter: "brightness(1)" }, { opacity: 0, transform: "scale(.2) rotate(160deg)", filter: "brightness(3)" }],
        { duration: 560, easing: "cubic-bezier(.6,0,.8,.2)", fill: "forwards" },
      ).onfinish = done;
    });
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

  /** La file n'est plus trouvée (refus, esquive, expiration) : l'overlay s'efface. */
  function leave() {
    if (!overlay || overlay.accepted) return;
    const el = overlay.el;
    clearInterval(overlay.timer);
    if (Motion.opts().reduced) return close();
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 400, fill: "forwards" }).onfinish = close;
  }

  // ---------- état ----------

  function apply(state) {
    pill(state.phase === "ChampSelect");
    const found = state.phase === "ReadyCheck" && state.ready_check?.state === "InProgress";
    if (found && !overlay) show(state);
    else if (found && overlay && state.ready_check.response === "Accepted") acceptedSequence();
    else if (!found && overlay) {
      if (state.phase === "ChampSelect") acceptedSequence(); // le Live Coach a accepté avant nous
      else leave();
    }
    if (state.phase === "ChampSelect" && expectDraft > performance.now() && !overlay) {
      expectDraft = 0;
      goDraft();
    }
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

  window.addEventListener("load", () => {
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
