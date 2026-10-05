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
    sync(ctx.sync, template.content, fresh);
    fresh.forEach(animate);
    readState();
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
    if (state.locked_id) ctx.sel = state.locked_id;
    else if (state.hover_id) ctx.sel = state.hover_id;
    else if (!ctx.sel || !(String(ctx.sel) in state.win)) ctx.sel = state.recs[0] ?? null;
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
    post,
    toast,
    refresh,
    onSync: (listener) => listeners.add(listener),
    sync,
    animate,
    fr,
  };
})();
