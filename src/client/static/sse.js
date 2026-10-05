// Flux du bus interne du client (SPEC-21 §4.2) : `fetch` avec le jeton de session (`EventSource`
// n'envoie pas d'en-tête), trames SSE découpées à la main, reconnexion toutes les 2 s.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;

  /**
   * Écoute le sujet `topic` ; `onEvent(nom, charge)` reçoit chaque événement, `onOpen()` chaque
   * (re)connexion (l'état a pu changer pendant une coupure). Renvoie un AbortController : `abort()` ferme
   * le flux. `alive()` faux arrête les reconnexions.
   */
  function open(topic, onEvent, { alive = () => true, onOpen = () => {} } = {}) {
    const abort = new AbortController();
    (async () => {
      while (alive() && !abort.signal.aborted) {
        try {
          const response = await fetch(`/events?topic=${encodeURIComponent(topic)}`, {
            headers: { [meta("token-header")]: meta("session-token") },
            signal: abort.signal,
          });
          if (!response.ok) throw new Error(response.status);
          onOpen();
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
              onEvent(name, payload);
            }
          }
        } catch (error) {
          if (abort.signal.aborted) return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    })();
    return abort;
  }

  window.Sse = { open };
})();
