// Flux du bus interne du client (SPEC-21 §4.2) : `fetch` avec le jeton de session (`EventSource`
// n'envoie pas d'en-tête), trames SSE découpées à la main, reconnexion toutes les 2 s.
// Une seule connexion pour toute la page : un flux SSE tient une connexion HTTP/1.1 ouverte et Chromium
// n'en accorde que 6 par hôte, au-delà plus aucun `fetch` ni navigation htmx ne part. Les écouteurs se
// partagent donc ce flux unique (tous les sujets) et filtrent par sujet.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const listeners = new Set();
  let running = false;
  let connected = false;

  const live = (listener) => !listener.abort.signal.aborted && listener.alive();

  function call(fn, ...args) {
    try {
      fn(...args);
    } catch (error) {
      /* un écouteur cassé n'arrête ni le flux ni les autres */
    }
  }

  function dispatch(name, payload) {
    for (const listener of [...listeners]) {
      if (!live(listener)) listeners.delete(listener);
      else if (listener.topics.has(name)) call(listener.onEvent, name, payload);
    }
  }

  async function run() {
    running = true;
    for (;;) {
      try {
        const response = await fetch("/events", { headers: { [meta("token-header")]: meta("session-token") } });
        if (!response.ok) throw new Error(response.status);
        connected = true;
        for (const listener of [...listeners]) if (live(listener)) call(listener.onOpen);
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
            const name = /^event: ?(.*)$/m.exec(frame)?.[1];
            if (!name) continue; // battement (« : ping »)
            let payload = null;
            try {
              payload = JSON.parse(/^data: ?(.*)$/m.exec(frame)?.[1] ?? "null");
            } catch (error) {
              /* charge illisible : l'événement part sans elle */
            }
            dispatch(name, payload);
          }
        }
      } catch (error) {
        /* serveur indisponible : on retente */
      }
      connected = false;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  /**
   * Écoute le ou les sujets `topic` ; `onEvent(nom, charge)` reçoit chaque événement, `onOpen()` chaque
   * (re)connexion (l'état a pu changer pendant une coupure). Renvoie un AbortController : `abort()` retire
   * l'écouteur. `alive()` faux le retire aussi.
   */
  function open(topic, onEvent, { alive = () => true, onOpen = () => {} } = {}) {
    const abort = new AbortController();
    listeners.add({ topics: new Set([].concat(topic)), onEvent, onOpen, alive, abort });
    if (!running) run();
    else if (connected) call(onOpen);
    return abort;
  }

  window.Sse = { open };
})();
