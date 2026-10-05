// Écran de draft (SPEC-21 tâches 73 à 92) : flux SSE du bus, synchronisation des zones par clé, mise à
// l'échelle, chrono et balance. Les autres modules de l'écran (grimoire, runes) s'accrochent à `window.Draft`.
//
// Le serveur rend l'écran en fragments (`/draft/stage`) ; chaque enfant d'un conteneur `data-sync` porte
// `data-key` et `data-sig`. Un nœud dont l'empreinte n'a pas bougé n'est pas touché (ses animations
// continuent) ; un nœud nouveau ou modifié rejoue ses animations `data-*` de motion.js.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const authHeaders = () => ({ [meta("token-header")]: meta("session-token") });
  const fr = (value, digits = 1) => value.toFixed(digits).replace(".", ",");
  const RING = 175.93; // circonférence du chrono (r = 28)

  const listeners = new Set();
  let ctx = null;

  // ---------- synchronisation par clé ----------

  /** Anime un nœud tout juste inséré (motion.js ne parcourt que les descendants de sa racine). */
  function animate(node) {
    const proxy = {
      querySelectorAll: (selector) => [
        ...(node.matches(selector) ? [node] : []),
        ...node.querySelectorAll(selector),
      ],
    };
    Motion.intro(proxy, Motion.opts());
    Motion.ambient(proxy, Motion.opts());
  }

  function sync(oldParent, newParent, fresh) {
    const olds = new Map();
    for (const child of oldParent.children) if (child.dataset.key) olds.set(child.dataset.key, child);
    let cursor = oldParent.firstElementChild;
    for (const next of [...newParent.children]) {
      const old = next.dataset.key ? olds.get(next.dataset.key) : undefined;
      if (!old) {
        oldParent.insertBefore(next, cursor);
        fresh.push(next);
        continue;
      }
      olds.delete(next.dataset.key);
      if (old === cursor) cursor = old.nextElementSibling;
      else oldParent.insertBefore(old, cursor);
      if (next.hasAttribute("data-sync")) sync(old, next, fresh);
      else if (old.dataset.sig !== next.dataset.sig) {
        old.replaceWith(next);
        fresh.push(next);
      }
    }
    olds.forEach((old) => old.remove());
  }

  function applyHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    const fresh = [];
    const previousKind = ctx.state?.kind;
    const wasLocked = ctx.state?.locked_id;
    sync(ctx.sync, template.content, fresh);
    readState();
    const reveal = previousKind === "ban" && ctx.state && ctx.state.kind !== "ban";
    if (reveal) staggerReveal(fresh);
    fresh.forEach(animate);
    if (reveal) revealBans(fresh);
    revealSkins(fresh);
    paintRow();
    if (ctx.state?.locked_id && !wasLocked) requestAnimationFrame(sealMoment);
    listeners.forEach((listener) => listener(ctx.state, fresh));
  }

  // ---------- rafraîchissement ----------

  async function refresh() {
    if (ctx.busy) return void (ctx.dirty = true);
    ctx.busy = true;
    try {
      do {
        ctx.dirty = false;
        const response = await fetch(ctx.root.dataset.stageUrl);
        if (response.ok && ctx.alive()) applyHtml(await response.text());
      } while (ctx.dirty && ctx.alive());
    } catch (error) {
      /* serveur indisponible : le prochain événement relance */
    } finally {
      ctx.busy = false;
    }
  }

  async function stream() {
    while (ctx.alive()) {
      try {
        const response = await fetch("/events?topic=draft", {
          headers: authHeaders(),
          signal: ctx.abort.signal,
        });
        if (!response.ok) throw new Error(response.status);
        refresh(); // l'état a pu changer pendant une coupure
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          let end;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            if (/^event: ?draft$/m.test(frame)) refresh();
          }
        }
      } catch (error) {
        if (ctx.abort.signal.aborted) return;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  // ---------- état : chrono, balance, sélection ----------

  function readState() {
    const data = ctx.sync.querySelector(".d-data");
    ctx.state = data ? JSON.parse(data.dataset.state) : null;
    if (!ctx.state) return;
    ctx.received = performance.now();
    const state = ctx.state;
    // Un survol que je viens de lancer prime quelques secondes sur ce que le client annonçait avant.
    const holding = ctx.hoverUntil > performance.now();
    if (state.locked_id) ctx.sel = state.locked_id;
    if (!state.locked_id) ctx.skin = null;
    else if (state.hover_id && !(holding && ctx.sel)) ctx.sel = state.hover_id;
    else if (!ctx.sel) ctx.sel = state.recs[0] ?? null;
    renderBalance();
    tick();
  }

  function tick() {
    const state = ctx.state;
    const ring = document.getElementById("d-tick-ring");
    const label = document.getElementById("d-tick-n");
    if (!ring || !label) return;
    if (!state || state.time_left_ms == null) {
      label.textContent = "–";
      ring.style.strokeDashoffset = RING;
      return;
    }
    const total = state.time_total_ms || 30000;
    const left = Math.max(0, state.time_left_ms - (performance.now() - ctx.received));
    label.textContent = Math.ceil(left / 1000);
    ring.style.strokeDashoffset = (RING * (1 - Math.min(1, left / total))).toFixed(2);
  }

  /** Probabilité à montrer : celle du champion sélectionné, sinon la fin de draft attendue. */
  function balanceTarget() {
    const state = ctx.state;
    const picked = ctx.sel != null ? state.win[String(ctx.sel)] : undefined;
    return picked ?? state.shown ?? state.base;
  }

  function paintBalance(probability) {
    const percent = document.getElementById("d-bal-pct");
    if (!percent) return;
    if (probability == null) {
      percent.textContent = "–";
      document.getElementById("d-bal-foe").textContent = "–";
      return;
    }
    percent.textContent = `${fr(probability * 100)} %`;
    document.getElementById("d-bal-foe").textContent = `${fr(100 - probability * 100)} %`;
    document.getElementById("d-bal-fill").style.transform = `scaleY(${probability.toFixed(4)})`;
    document.getElementById("d-bal-cursor").style.bottom = `${(probability * 100).toFixed(2)}%`;
  }

  function renderBalance() {
    const state = ctx.state;
    const note = document.getElementById("d-bal-note");
    if (!note) return;
    const name = state.names[String(ctx.sel)];
    note.textContent = state.locked_id
      ? "fin de draft estimée"
      : name && String(ctx.sel) in state.win
        ? `si ${name} est verrouillé`
        : "position actuelle";
    const target = balanceTarget();
    cancelAnimationFrame(ctx.raf);
    if (target == null || ctx.shown == null || Motion.opts().reduced) {
      ctx.shown = target;
      return paintBalance(target);
    }
    const from = ctx.shown;
    const start = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - start) / 800);
      ctx.shown = from + (target - from) * (1 - Math.pow(1 - p, 3));
      paintBalance(ctx.shown);
      if (p < 1) ctx.raf = requestAnimationFrame(step);
    };
    ctx.raf = requestAnimationFrame(step);
  }

  // ---------- phase de bans (tâche 87) ----------

  const POP = [
    { opacity: 0, transform: "scale(.2) rotate(-60deg)" },
    { opacity: 1, transform: "scale(1.15)", offset: 0.7 },
    { opacity: 1, transform: "none" },
  ];

  /** Sélection et libellés de la rangée : cartes de ban et de pick, boutons « Bannir X » et « Verrouiller X ». */
  function paintRow() {
    const state = ctx.state;
    if (!state) return;
    paintPicks(state);
    paintSkins(state);
    if (state.kind !== "ban") ctx.banSel = null;
    else if (state.my_ban_id) ctx.banSel = state.my_ban_id;
    else if (!ctx.banSel) ctx.banSel = state.ban_hover_id || state.bans[0] || null;
    ctx.stage.querySelectorAll(".d-cards-ban .d-card").forEach((card) => {
      const id = +card.dataset.champ;
      const selected = id === ctx.banSel;
      card.classList.toggle("is-sel", selected);
      card.querySelector("[data-state]").textContent =
        id === state.my_ban_id ? "Banni" : selected ? "Visé" : "Viser";
    });
    const button = ctx.stage.querySelector('[data-act="ban"]');
    if (button) {
      const name = state.names[String(ctx.banSel)] || ctx.banName;
      button.textContent = name ? `Bannir ${name}` : "Bannir";
      button.disabled = !ctx.banSel || !name;
    }
  }

  // ---------- sélection de skin (tâche 90) ----------

  /** Le skin marqué : mon dernier clic tant que le client ne l'a pas confirmé, sinon celui du client. */
  function paintSkins(state) {
    const cards = [...ctx.stage.querySelectorAll(".d-skin")];
    if (!cards.length) return;
    if (ctx.skin && state.skin_id === ctx.skin) ctx.skin = null; // confirmé
    const chosen = ctx.skin && ctx.skinUntil > performance.now() ? ctx.skin : state.skin_id;
    cards.forEach((card) => card.classList.toggle("is-sel", +card.dataset.skin === chosen));
    const selected = cards.find((card) => +card.dataset.skin === chosen);
    const title = document.getElementById("d-skin-title");
    if (selected && title) title.textContent = `Skin · ${selected.dataset.name}`;
  }

  /** Les cartes de skin arrivent en tournant, l'une après l'autre. */
  function revealSkins(fresh) {
    if (Motion.opts().reduced) return;
    fresh
      .flatMap((node) => [...node.querySelectorAll(".d-skin")])
      .forEach((card, i) =>
        card.animate(
          [{ opacity: 0, transform: "translateY(40px) rotateY(70deg)" }, { opacity: 1, transform: "none" }],
          { duration: 560, delay: 200 + i * 45, easing: Motion.E.entree, fill: "backwards" },
        ),
      );
  }

  /** Choisit un skin possédé : aperçu et splash tout de suite, écriture dans le champ select. */
  function pickSkin(card) {
    if (card.dataset.owned !== "1" || !ctx.state?.locked_id) return;
    const id = +card.dataset.skin;
    ctx.skin = id;
    ctx.skinUntil = performance.now() + 3000;
    paintSkins(ctx.state);
    const image = card.querySelector("img")?.src.replace("/loading/", "/splash/");
    const splash = ctx.stage.querySelector(".d-splash");
    if (splash && image) {
      let img = splash.querySelector("img");
      if (!img) splash.appendChild((img = document.createElement("img")));
      img.src = image;
      splash.classList.add("on");
      if (!Motion.opts().reduced)
        img.animate(
          [{ opacity: 0, transform: "scale(1.12)", filter: "brightness(2.2) saturate(1.6)" }, { opacity: 1, transform: "scale(1)", filter: "none" }],
          { duration: 900, easing: Motion.E.entree },
        );
    }
    if (!Motion.opts().reduced) {
      const [x, y] = Motion.center(card);
      const C = Motion.C;
      Motion.burst(x, y, { n: 50, speed: 7, glyphs: 6, ringR: 120, colors: [C.gold, C.copper, C.violet] });
    }
    post("/draft/skin", { skin_id: id });
  }

  function paintPicks(state) {
    ctx.stage.querySelectorAll(".d-cards-pick .d-card").forEach((card) => {
      const selected = +card.dataset.champ === ctx.sel;
      card.classList.toggle("is-sel", selected);
      card.querySelector("[data-state]").textContent = selected ? (state.locked_id ? "Scellé" : "Survolé") : "Survoler";
    });
    const button = ctx.stage.querySelector('[data-act="lock"]');
    if (button) {
      const name = state.names[String(ctx.sel)] || ctx.pickName;
      button.textContent = name ? `Verrouiller ${name}` : "Verrouiller";
      button.disabled = !state.my_turn || !ctx.sel || !name;
      button.title = state.my_turn ? "" : "Ce n'est pas encore ton tour";
    }
  }

  /** Survole un pick (carte ou grimoire) : aperçu tout de suite, survol dans le client à mon tour. */
  function hoverPick(id, name, image) {
    const state = ctx.state;
    if (!state || state.locked_id || state.kind === "ban" || ctx.sel === id) return;
    ctx.pickName = name;
    ctx.hoverUntil = performance.now() + 3000;
    select(id);
    paintRow();
    const portrait = ctx.stage.querySelector("img[data-me]");
    if (portrait && image) {
      portrait.src = image;
      portrait.style.opacity = 0.6;
    }
    if (!Motion.opts().reduced && portrait) {
      Motion.bloom(portrait, Motion.opts());
      const [x, y] = Motion.center(portrait);
      const C = Motion.C;
      Motion.converge(x, y, { n: 26, radius: 340, life: 650, colors: [C.copper, C.gold, C.violet] });
    }
    if (state.my_turn) post("/draft/action/hover", { champion_id: id });
  }

  async function confirmLock() {
    if (!ctx.sel || !ctx.state?.my_turn) return false;
    const done = await post("/draft/action/lock", { champion_id: ctx.sel }); // le sceau suit quand le client confirme
    return !!done;
  }

  /** Verrouillage confirmé : sceau apposé, impact, 170 étincelles, secousse. */
  function sealMoment() {
    const C = Motion.C;
    Motion.seal(ctx.root, { ...Motion.opts(), target: ctx.stage, colors: [C.copper, C.gold, C.mint, C.white] });
  }

  /** Vise un ban (carte ou grimoire) : l'aperçu part dans le client par un survol de ban. */
  function aimBan(id, name) {
    if (!ctx.state || ctx.state.kind !== "ban" || ctx.state.my_ban_id || ctx.banSel === id) return;
    ctx.banSel = id;
    ctx.banName = name;
    paintRow();
    if (!Motion.opts().reduced) Motion.bloom(ctx.stage.querySelector("[data-ban-me]"), Motion.opts());
    post("/draft/action/hover_ban", { champion_id: id });
  }

  /** Tampon sur mon ban : retour d'échelle, explosion magenta, secousse de l'écran. */
  function banStamp() {
    const el = ctx.stage.querySelector("[data-ban-me]");
    if (!el || Motion.opts().reduced) return;
    el.animate(
      [
        { transform: "scale(2.4) rotate(-30deg)", opacity: 0 },
        { transform: "scale(.9) rotate(6deg)", opacity: 1, offset: 0.6 },
        { transform: "none", opacity: 1 },
      ],
      { duration: 560, easing: Motion.E.sceau },
    );
    setTimeout(() => {
      const [x, y] = Motion.center(el);
      const C = Motion.C;
      Motion.burst(x, y, { n: 130, speed: 11, glyphs: 14, ringR: 220, ringW: 6, colors: [C.magenta, C.rose, C.white] });
      Motion.shake(ctx.stage, 6, 360);
    }, 300);
  }

  async function confirmBan() {
    if (!ctx.banSel) return false;
    const done = await post("/draft/action/ban", { champion_id: ctx.banSel });
    if (done) banStamp();
    return !!done;
  }

  /** Les picks adverses arrivent après les bans : 700 ms puis 150 ms d'écart (README, « Ban »). */
  function staggerReveal(fresh) {
    if (Motion.opts().reduced) return;
    let index = 0;
    fresh
      .flatMap((node) => [...(node.matches(".d-member-enemy") ? [node] : []), ...node.querySelectorAll(".d-member-enemy")])
      .forEach((node) => (node.dataset.delay = String(700 + index++ * 150)));
  }

  /** Les bans adverses se révèlent en cascade de 120 ms, chacun avec sa gerbe. */
  function revealBans(fresh) {
    if (Motion.opts().reduced) return;
    const C = Motion.C;
    fresh
      .flatMap((node) => [...node.querySelectorAll(".d-ban-foe.d-ban-done")])
      .forEach((el, i) => {
        el.animate(POP, { duration: 520, delay: i * 120, easing: Motion.E.ressort, fill: "backwards" });
        setTimeout(() => Motion.burstAt(el, { n: 22, speed: 5, ringR: 46, ringW: 3, colors: [C.rose, C.violet] }), i * 120 + 260);
      });
  }

  // ---------- mise à l'échelle ----------

  function fit() {
    const { root, stage } = ctx;
    const [width, height] = [+root.dataset.stageW, +root.dataset.stageH];
    const k = Math.min(1, root.clientWidth / width, root.clientHeight / height);
    const x = (root.clientWidth - width * k) / 2;
    const y = (root.clientHeight - height * k) / 2;
    stage.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
    ctx.scale = k;
  }

  // ---------- actions ----------

  function toast(message) {
    const host = document.getElementById("d-overlays");
    if (!host) return;
    const element = document.createElement("div");
    element.className = "d-toast";
    element.setAttribute("role", "status");
    element.textContent = message;
    host.appendChild(element);
    Motion.opts().reduced || element.animate([{ opacity: 0, transform: "translate(-50%, 12px)" }, { opacity: 1, transform: "translate(-50%, 0)" }], { duration: 260, easing: Motion.E.entree });
    setTimeout(() => element.remove(), 3500);
  }

  /** POST avec le jeton de session ; un refus (409) s'affiche tel quel. Renvoie la réponse JSON ou null. */
  async function post(path, params) {
    try {
      const response = await fetch(`${path}?${new URLSearchParams(params)}`, {
        method: "POST",
        headers: authHeaders(),
      });
      const body = response.status === 204 ? {} : await response.json().catch(() => ({}));
      if (!response.ok) return void toast(body.detail || "Action refusée");
      return body;
    } catch (error) {
      toast("Serveur indisponible");
    }
  }

  function select(id) {
    if (ctx.state?.locked_id || ctx.sel === id) return;
    ctx.sel = id;
    renderBalance();
    listeners.forEach((listener) => listener(ctx.state, []));
  }

  // ---------- cycle de vie ----------

  function boot(root) {
    if (ctx && ctx.root === root) return;
    ctx?.abort.abort();
    const stage = root.querySelector("#draft-stage");
    ctx = {
      root,
      stage,
      sync: root.querySelector("#d-sync"),
      abort: new AbortController(),
      alive: () => root.isConnected,
      state: null,
      sel: null,
      shown: null,
      scale: 1,
      busy: false,
      dirty: false,
    };
    fit();
    readState();
    paintRow();
    stage.addEventListener("click", (event) => {
      const name = (card) => card.querySelector(".d-card-name").textContent;
      const ban = event.target.closest(".d-cards-ban .d-card");
      if (ban) return aimBan(+ban.dataset.champ, name(ban));
      const skin = event.target.closest(".d-skin");
      if (skin) return pickSkin(skin);
      const pick = event.target.closest(".d-cards-pick .d-card");
      if (pick) return hoverPick(+pick.dataset.champ, name(pick), pick.querySelector("img")?.src);
      if (event.target.closest('[data-act="ban"]')) confirmBan();
      else if (event.target.closest('[data-act="lock"]')) confirmLock();
      else if (event.target.closest("[data-open-grid]")) window.DraftGrid?.open();
      else if (event.target.closest(".d-me") && !ctx.state?.locked_id) window.DraftGrid?.open();
      else if (event.target.closest("[data-ban-me]") && ctx.state?.kind === "ban" && !ctx.state.my_ban_id)
        window.DraftGrid?.open();
    });
    addEventListener("resize", () => ctx.alive() && fit());
    const timer = setInterval(() => {
      if (ctx.alive()) return tick();
      clearInterval(timer);
      ctx.abort.abort(); // l'écran a été quitté : le flux SSE se ferme
    }, 250);
    stream();
  }

  document.addEventListener("htmx:load", (event) => {
    const root = event.target.id === "draft" ? event.target : event.target.querySelector?.("#draft");
    if (root) boot(root);
  });

  window.Draft = {
    get state() {
      return ctx?.state;
    },
    get selected() {
      return ctx?.sel;
    },
    get scale() {
      return ctx?.scale ?? 1;
    },
    select,
    aimBan,
    hoverPick,
    confirmBan,
    confirmLock,
    openGrid: () => window.DraftGrid?.open(),
    post,
    toast,
    refresh,
    onSync: (listener) => listeners.add(listener),
    sync,
    animate,
    fr,
  };
})();
