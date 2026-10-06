// Règles de visée d'un ban (SPEC-24 tâche 97), sans DOM. `state` est l'état de la rangée de bans :
// { kind, my_ban_id, ban_hover_id, bans: [ids conseillés, le meilleur d'abord] }.
// Une cible n'existe que si elle a été cliquée ou déjà envoyée au client LoL (survol de ban) : le
// conseil, lui, n'est qu'une suggestion affichée, jamais une présélection silencieuse.
// Testé sous node (tests/test_client_draft.py).
(function (root) {
  /** Cible courante : mon ban posé, sinon la cible cliquée, sinon le survol déjà dans le client. */
  function target(state, clicked) {
    if (!state || state.kind !== "ban") return null;
    return state.my_ban_id || clicked || state.ban_hover_id || null;
  }

  /** Le conseil à mettre en avant tant qu'aucune cible n'est choisie. */
  function suggestion(state, clicked) {
    if (!state || state.kind !== "ban" || target(state, clicked)) return null;
    return (state.bans && state.bans[0]) || null;
  }

  /** Un clic sur `id` part dans le client LoL (survol de ban) sauf si c'est déjà la cible ou si mon ban est posé. */
  function shouldSendHover(state, clicked, id) {
    if (!state || state.kind !== "ban" || state.my_ban_id) return false;
    return target(state, clicked) !== id;
  }

  const api = { target, suggestion, shouldSendHover };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BanLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
