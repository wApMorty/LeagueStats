// Écran Lobby (SPEC-21 tâche 80) : le corps de la page est relu (`/lobby/etat`) à chaque événement du
// WebSocket LCU relayé par le bus (sujet `lcu`) et toutes les 10 s en secours ; les actions (ouvrir un
// lobby, choisir ses postes, quitter) sont des POST avec le jeton de session, refusés lisiblement par le
// serveur hors de la phase qui convient. Un rechargement n'a aucune animation et laisse une liste ouverte.
(() => {
  const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content;
  const POLL_MS = 10000;
  let busy = false;
  let again = false;

  const body = () => document.getElementById("lobby-body");

  function notice(text) {
    const el = document.getElementById("lobby-notice");
    if (!el) return;
    el.textContent = text || "";
    el.hidden = !text;
  }

  const post = (path) =>
    fetch(path, { method: "POST", headers: { [meta("token-header")]: meta("session-token") } })
      .then(async (response) => ({ ok: response.ok, body: await response.json().catch(() => ({})) }))
      .catch(() => ({ ok: false, body: { detail: "Serveur indisponible" } }));

  async function refresh() {
    if (!body()) return; // une autre page est affichée
    if (busy) {
      again = true;
      return;
    }
    if (document.activeElement?.tagName === "SELECT" && body().contains(document.activeElement)) return;
    busy = true;
    try {
      const response = await fetch("/lobby/etat");
      if (response.ok && body()) body().innerHTML = await response.text();
    } catch (error) {
      /* serveur indisponible : le prochain événement relance */
    } finally {
      busy = false;
      if (again) {
        again = false;
        refresh();
      }
    }
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-lobby-action]");
    if (!button || button.disabled) return;
    button.disabled = true;
    notice("");
    const { ok, body: reply } = await post(button.dataset.lobbyAction);
    if (!ok) notice(reply.detail || "Action refusée");
    button.disabled = false;
    refresh();
  });

  document.addEventListener("change", async (event) => {
    if (!event.target.matches("#pos-first, #pos-second")) return;
    const first = document.getElementById("pos-first").value;
    const second = document.getElementById("pos-second").value;
    notice("");
    const { ok, body: reply } = await post(`/lobby/postes?first=${first}&second=${second}`);
    if (!ok) notice(reply.detail || "Postes refusés");
    event.target.blur(); // sinon le rechargement attendrait que la liste soit refermée
    refresh();
  });

  window.addEventListener("load", () => {
    Sse.open("lcu", (name, payload) => {
      if (/lobby|matchmaking|gameflow/.test(payload?.uri ?? "")) refresh();
    });
    setInterval(refresh, POLL_MS);
  });

  window.Lobby = { refresh };
})();
