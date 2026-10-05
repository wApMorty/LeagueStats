// File d'attente dans la barre de titre (SPEC-21 tâche 81) : « Lancer la file » quand le lobby le permet,
// puis la recherche en cours (temps écoulé, estimation du client LoL) avec « Annuler ». L'état vient du
// serveur (`/file/state`), relu à chaque événement du WebSocket LCU relayé par le bus (sujet `lcu`) et toutes
// les 4 s en secours ; le temps s'écoule côté page entre deux lectures. Quand la partie est trouvée,
// l'overlay de `found.js` prend le relais (la phase quitte « Matchmaking »). Si l'auto-accept du Live Coach
// est actif, l'info-bulle le dit : la partie trouvée sera acceptée sans clic.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const POLL_MS = 4000;
  let busy = false;
  let since = null; // instant (performance.now) où la recherche a commencé
  let estimated = 0;
  let ticker = null;

  const el = (id) => document.getElementById(id);
  const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

  const post = (path) =>
    fetch(path, { method: "POST", headers: { [meta("token-header")]: meta("session-token") } })
      .then(async (response) => ({ ok: response.ok, body: await response.json().catch(() => ({})) }))
      .catch(() => ({ ok: false, body: { detail: "Serveur indisponible" } }));

  function tick() {
    if (since === null) return;
    const elapsed = (performance.now() - since) / 1000;
    el("tb-file-text").textContent = `En file ${clock(elapsed)}` + (estimated ? ` · estimée ${clock(estimated)}` : "");
  }

  function apply(state) {
    const start = el("tb-file-start");
    const search = el("tb-file-search");
    if (!start || !search) return;
    start.hidden = !state.can_start;
    search.hidden = !state.searching;
    start.title = state.queue ? `Lancer la recherche : ${state.queue}` : "Lancer la recherche de partie du lobby";
    search.title = state.auto_accept
      ? "Auto-accept du Live Coach actif : la partie trouvée sera acceptée sans clic"
      : "Recherche de partie en cours";
    if (state.searching) {
      estimated = state.estimated || 0;
      since = performance.now() - (state.elapsed || 0) * 1000;
      if (!ticker) ticker = setInterval(tick, 1000);
      tick();
    } else {
      since = null;
      clearInterval(ticker);
      ticker = null;
    }
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch("/file/state");
      if (response.ok) apply(await response.json());
    } catch (error) {
      /* serveur indisponible : le prochain événement relance */
    } finally {
      busy = false;
    }
  }

  async function act(path, button) {
    button.disabled = true;
    const { ok, body } = await post(path);
    button.disabled = false;
    if (!ok) {
      button.title = body.detail || "Action refusée";
      button.classList.add("is-refused");
      setTimeout(() => button.classList.remove("is-refused"), 3000);
    }
    refresh();
  }

  window.addEventListener("load", () => {
    el("tb-file-start")?.addEventListener("click", (event) => act("/file/lancer", event.currentTarget));
    el("tb-file-cancel")?.addEventListener("click", (event) => act("/file/annuler", event.currentTarget));
    Sse.open("lcu", (name, payload) => {
      if (/lobby|matchmaking|gameflow/.test(payload?.uri ?? "")) refresh();
    }, { onOpen: refresh });
    setInterval(refresh, POLL_MS);
    refresh();
  });

  window.FileQueue = { refresh };
})();
