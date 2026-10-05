// Règles de l'éditeur de runes (SPEC-21 tâche 92), sans DOM : une page est
// { primary, sub, keystone, rows: [3 ids], subs: [2 ids, la plus ancienne d'abord], shards: [3 ids] },
// `styles` la liste de `/draft/runes` ({ id, slots: [[{ id }], ...] }, rangée 0 = runes majeures).
// Chaque fonction renvoie une nouvelle page, jamais la même modifiée. Testé sous node (tests/test_client_draft.py).
(function (root) {
  const style = (styles, id) => styles.find((candidate) => candidate.id === id);
  const first = (tree, row) => tree.slots[row][0].id;

  /** Rangée (0 à 3) d'une rune dans un arbre, -1 si elle n'y est pas. */
  function runeRow(tree, runeId) {
    return tree.slots.findIndex((slot) => slot.some((rune) => rune.id === runeId));
  }

  /** Les deux premières runes des deux premières rangées : la sélection par défaut d'un arbre secondaire. */
  function defaultSubs(tree) {
    return [first(tree, 1), first(tree, 2)];
  }

  function setPrimary(styles, page, id) {
    if (id === page.primary) return page;
    const tree = style(styles, id);
    const sub = page.sub === id ? styles.find((other) => other.id !== id).id : page.sub;
    return {
      ...page,
      primary: id,
      keystone: first(tree, 0),
      rows: [1, 2, 3].map((row) => first(tree, row)),
      sub,
      subs: sub === page.sub ? page.subs : defaultSubs(style(styles, sub)),
    };
  }

  function setSub(styles, page, id) {
    if (id === page.sub || id === page.primary) return page;
    return { ...page, sub: id, subs: defaultSubs(style(styles, id)) };
  }

  function setKeystone(styles, page, id) {
    return runeRow(style(styles, page.primary), id) === 0 ? { ...page, keystone: id } : page;
  }

  function setRow(styles, page, row, id) {
    const tree = style(styles, page.primary);
    if (runeRow(tree, id) !== row + 1) return page;
    const rows = [...page.rows];
    rows[row] = id;
    return { ...page, rows };
  }

  /** Une rune de l'arbre secondaire : même rangée = elle remplace l'ancienne ; autre rangée = la plus ancienne part. */
  function setSubRune(styles, page, id) {
    const tree = style(styles, page.sub);
    const row = runeRow(tree, id);
    if (row < 1 || page.subs.includes(id)) return page;
    const same = page.subs.findIndex((other) => runeRow(tree, other) === row);
    const subs = same >= 0 ? page.subs.map((other, i) => (i === same ? id : other)) : [page.subs[1], id];
    return { ...page, subs };
  }

  function setShard(page, row, id) {
    const shards = [...page.shards];
    shards[row] = id;
    return { ...page, shards };
  }

  /** Les runes secondaires dans l'ordre des rangées (pour l'affichage). */
  function subsByRow(styles, page) {
    const tree = style(styles, page.sub);
    return [...page.subs].sort((a, b) => runeRow(tree, a) - runeRow(tree, b));
  }

  const api = { runeRow, setPrimary, setSub, setKeystone, setRow, setSubRune, setShard, subsByRow };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RuneLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
