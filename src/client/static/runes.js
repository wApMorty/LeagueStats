// Colonne loadout de la draft (SPEC-21 tâche 91) : page de runes, sorts d'invocateur et objets du champion
// sélectionné ou verrouillé. Le serveur donne la page prévue (`/draft/loadout`, OneTricks ou déjà écrite
// dans le client) et les arbres de Data Dragon (`/draft/runes`) ; ce module tient la copie de travail
// (`lo`), la page modifiée à la main (qui prime sur l'import du lock-in) et « Envoyer au client ».
(() => {
  const SPELL_KEYS = ["D", "F"];
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const perk = (icon) => `/assets/perk/${icon}`;

  let tree = null; // arbres, fragments, sorts (une fois par session)
  let treeRequest = null;
  let lo = null; // copie de travail : { championId, status, base, page, spells, modified, pushed, picker }

  const host = () => document.querySelector(".d-loadout");

  /** Petit constructeur DOM : aucun HTML en chaîne, donc rien à échapper. */
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (value !== false && value != null) node.setAttribute(key, value === true ? "" : value);
    }
    node.append(...children.flat().filter((child) => child != null && child !== false));
    return node;
  }

  const styleOf = (id) => tree?.styles.find((style) => style.id === id);
  const runeOf = (style, id) => style?.slots.flat().find((rune) => rune.id === id);
  const shardOf = (id) => tree?.shards.flatMap((row) => row.options).find((option) => option.id === id);
  const spellOf = (id) => tree?.spells.find((spell) => spell.id === id);
  const tint = (color, alpha) => color.replace(")", ` / ${alpha})`);
  const initials = (name) =>
    name.split(/[\s:'’-]+/).filter((word) => word.length > 2).slice(0, 2).map((word) => word[0].toUpperCase()).join("");

  function ensureTree() {
    treeRequest ??= fetch("/draft/runes")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => (tree = data?.styles?.length ? data : null))
      .catch(() => null);
    return treeRequest;
  }

  // ---------- chargement ----------

  async function load(championId) {
    lo = { championId, status: "loading", modified: false, pushed: false, picker: null };
    render();
    const [plan] = await Promise.all([
      fetch(`/draft/loadout?champion_id=${championId}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ensureTree(),
    ]);
    if (!lo || lo.championId !== championId) return; // le champion a changé entre-temps
    if (!plan?.available || !tree) {
      lo.status = "unavailable";
      lo.reason = plan?.reason || "Page indisponible";
    } else {
      lo.status = "ready";
      lo.base = plan;
      lo.page = clone(plan.page);
      lo.spells = [...plan.spells];
    }
    render();
  }

  /** Suit le champion montré : sélectionné avant le lock, verrouillé ensuite ; la page écrite par le Live Coach la remplace. */
  function follow(state) {
    if (!host() || !state) return;
    const champion = state.locked_id || Draft.selected || 0;
    if (!champion) {
      if (lo) lo = null;
      return render();
    }
    if (!lo || lo.championId !== champion) {
      if (lo?.modified) Draft.post("/draft/loadout/manual", { on: 0 }); // la main ne vaut que pour ce champion
      return void load(champion);
    }
    if (lo.status === "ready" && !lo.modified && state.locked_id && lo.base.source !== "client" && state.loadout) {
      load(champion); // le Live Coach vient d'écrire la page dans le client
    } else if (!host().firstElementChild) render();
  }

  // ---------- modifications ----------

  function markModified() {
    const first = !lo.modified;
    lo.modified = true;
    lo.pushed = false;
    if (first) Draft.post("/draft/loadout/manual", { on: 1 });
    render();
  }

  function pickSpell(slot, id) {
    const other = 1 - slot;
    if (lo.spells[other] === id) lo.spells[other] = lo.spells[slot];
    lo.spells[slot] = id;
    lo.picker = null;
    markModified();
    bloom(`[data-spell-slot="${slot}"]`);
  }

  function swapSpells() {
    lo.spells = [lo.spells[1], lo.spells[0]];
    markModified();
    bloom('[data-spell-slot="0"]');
  }

  /** Appelé par l'éditeur de runes (tâche 92) quand la page est appliquée. */
  function applyPage(page) {
    lo.page = clone(page);
    markModified();
    if (Motion.opts().reduced) return;
    const key = host().querySelector("[data-keystone]");
    if (!key) return;
    Motion.bloom(key, Motion.opts());
    const [x, y] = Motion.center(key);
    Motion.burst(x, y, { n: 60, speed: 8, glyphs: 8, ringR: 140, colors: [styleOf(lo.page.primary)?.color ?? Motion.C.mint] });
    Motion.flash(Motion.C.magenta, 0.2, 380);
  }

  function restore() {
    lo.page = clone(lo.base.page);
    lo.spells = [...lo.base.spells];
    lo.modified = false;
    lo.pushed = false;
    lo.picker = null;
    Draft.post("/draft/loadout/manual", { on: 0 });
    render();
  }

  async function push() {
    const { page, spells } = lo;
    const done = await Draft.post("/draft/loadout/send", {
      primary: page.primary,
      sub: page.sub,
      perks: [page.keystone, ...page.rows, ...page.subs].join(","),
      shards: page.shards.join(","),
      spell1: spells[0],
      spell2: spells[1],
    });
    if (!done) return;
    lo.pushed = true;
    render();
  }

  function bloom(selector) {
    const node = host().querySelector(selector);
    if (node && !Motion.opts().reduced) Motion.bloom(node, Motion.opts());
  }

  // ---------- rendu ----------

  function runeDisc(rune, size, color, glow) {
    return el(
      "div",
      { class: "lo-rune", style: `--s:${size}px;--c:${color};${glow ? `box-shadow:0 0 20px ${color}` : ""}` },
      rune ? initials(rune.name) : "",
      rune ? el("img", { src: perk(rune.icon), alt: "" }) : null,
    );
  }

  function pageCard() {
    const page = lo.page;
    const primary = styleOf(page.primary);
    const secondary = styleOf(page.sub);
    const color = primary.color;
    const keystone = runeOf(primary, page.keystone);
    const rows = page.rows.map((id) => runeOf(primary, id));
    const subs = page.subs.map((id) => runeOf(secondary, id));
    const shards = page.shards.map(shardOf);
    return el(
      "div",
      {
        class: "lo-page",
        style: `--tc:${color};background:linear-gradient(155deg, ${tint(color, 0.16)} 0%, oklch(0.205 0.02 170) 45%, ${tint(secondary.color, 0.12)} 100%);border-color:${color}`,
        role: "button",
        tabindex: "0",
        "data-open-editor": true,
      },
      el("div", { class: "lo-tree" }, el("img", { src: perk(primary.icon), alt: "" }), primary.name, el("span", { class: "lo-edit" }, "Modifier ›")),
      el(
        "div",
        { class: "lo-key" },
        el("div", { "data-keystone": true }, runeDisc(keystone, 72, color, true)),
        el("div", { class: "lo-key-name" }, keystone?.name ?? "—"),
      ),
      el("div", { class: "lo-rows" }, rows.map((rune) => el("div", { class: "lo-row" }, runeDisc(rune, 44, color), el("div", { class: "lo-rune-name" }, rune?.name ?? "—")))),
      el("div", { class: "lo-tree lo-tree-sub", style: `color:${secondary.color}` }, el("img", { src: perk(secondary.icon), alt: "" }), secondary.name),
      el("div", { class: "lo-subs" }, subs.map((rune) => el("div", { class: "lo-sub" }, runeDisc(rune, 36, secondary.color), el("span", {}, rune?.name ?? "—")))),
      el(
        "div",
        { class: "lo-shards" },
        shards.map((shard) => el("div", { class: "lo-shard" }, shard ? el("img", { src: perk(shard.icon), alt: "" }) : null)),
        el("span", {}, shards.map((shard) => shard?.name ?? "—").join(" · ")),
      ),
    );
  }

  function spellsBlock() {
    const slots = lo.spells.map((id, slot) => {
      const spell = spellOf(id);
      return el(
        "div",
        { class: `lo-spell${lo.picker === slot ? " is-open" : ""}`, "data-spell-slot": slot, role: "button", tabindex: "0", onclick: () => ((lo.picker = lo.picker === slot ? null : slot), render()) },
        spell ? el("img", { src: `/assets/spell/${spell.key}.png`, alt: "" }) : null,
        el("div", { class: "lo-spell-id" }, el("span", { class: "lo-spell-name" }, spell?.name ?? String(id)), el("span", { class: "lo-spell-key" }, `Touche ${SPELL_KEYS[slot]}`)),
      );
    });
    const picker =
      lo.picker === null
        ? null
        : el(
            "div",
            { class: "lo-picker", "data-picker": true },
            el("div", { class: "lo-picker-title" }, `Choisir le sort ${SPELL_KEYS[lo.picker]}`),
            el(
              "div",
              { class: "lo-picker-grid" },
              tree.spells.map((spell) =>
                el(
                  "div",
                  { class: `lo-choice${lo.spells[lo.picker] === spell.id ? " is-mine" : ""}`, onclick: () => pickSpell(lo.picker, spell.id), role: "button", tabindex: "0" },
                  el("img", { src: `/assets/spell/${spell.key}.png`, alt: "" }),
                  el("span", {}, spell.name),
                ),
              ),
            ),
          );
    return el(
      "div",
      { class: "lo-spells" },
      el("div", { class: "lo-label" }, el("span", {}, "Sorts d'invocateur"), el("a", { class: "lo-swap", role: "button", tabindex: "0", onclick: swapSpells }, "Échanger D ⇄ F")),
      el("div", { class: "lo-spell-grid" }, slots),
      picker,
    );
  }

  function itemsBlock() {
    return el(
      "div",
      { class: "lo-items" },
      el("div", { class: "lo-label" }, "Objets · lecture seule"),
      lo.base.items.map((block) =>
        el("div", { class: "lo-item-row" }, el("span", {}, block.title), block.ids.slice(0, 6).map((id) => el("img", { src: `/assets/item/${id}.png`, alt: "" }))),
      ),
    );
  }

  function footer() {
    const name = Draft.state?.names?.[String(lo.championId)] ?? "";
    const note = lo.pushed
      ? "Page et sorts écrits dans le client LoL."
      : lo.modified
        ? "Tes modifications partiront dans le client à l'envoi ; l'import OneTricks au verrouillage ne les écrasera pas."
        : lo.base.source === "client"
          ? "Page écrite dans le client au verrouillage (SPEC-15)."
          : `Import OneTricks automatique au verrouillage${name ? ` de ${name}` : ""} (SPEC-15).`;
    return el(
      "div",
      { class: "lo-foot" },
      el("div", { class: "lo-note" }, note),
      el(
        "div",
        { class: "lo-buttons" },
        el("button", { type: "button", class: "lo-push", onclick: push }, lo.pushed ? "Envoyé au client ✓" : "Envoyer au client"),
        lo.modified ? el("button", { type: "button", class: "lo-restore", onclick: restore }, "Rétablir OneTricks") : null,
      ),
    );
  }

  function render() {
    const root = host();
    if (!root) return;
    const state = Draft.state;
    const role = root.dataset.role || "";
    const head = el(
      "div",
      { class: "lo-head" },
      el("div", { class: "d-kicker" }, `Loadout${state?.names?.[String(lo?.championId)] ? ` · ${state.names[String(lo.championId)]}` : ""}${role ? ` ${role}` : ""}`),
      el(
        "div",
        { class: "lo-title-row" },
        el("span", { class: "lo-title" }, "Runes & sorts"),
        lo?.status === "ready" ? (lo.modified ? el("span", { class: "lo-pill" }, "Modifiée à la main") : el("span", { class: "lo-meta" }, lo.base.source === "client" ? "Page du client" : `OneTricks · ${lo.base.games} parties`)) : null,
      ),
    );
    let body;
    if (!lo) body = el("div", { class: "lo-empty" }, "Survole ou verrouille un champion : sa page de runes apparaît ici.");
    else if (lo.status === "loading") body = el("div", { class: "lo-empty" }, "Lecture du grimoire de runes…");
    else if (lo.status === "unavailable") body = el("div", { class: "lo-empty" }, lo.reason);
    else body = el("div", { class: "lo-body" }, pageCard(), spellsBlock(), itemsBlock(), footer());
    root.replaceChildren(head, body);
    if (lo?.status === "ready" && !Motion.opts().reduced && root.dataset.painted !== String(lo.championId)) {
      root.dataset.painted = String(lo.championId);
      root.querySelectorAll(".lo-body > *").forEach((node, i) =>
        node.animate([{ opacity: 0, transform: "translateY(18px)" }, { opacity: 1, transform: "none" }], { duration: 600, delay: 200 + i * 100, easing: Motion.E.entree, fill: "backwards" }),
      );
    }
  }

  document.addEventListener("click", (event) => {
    if (!lo || lo.status !== "ready") return;
    if (event.target.closest("[data-open-editor]")) window.RuneEditor?.open(lo, tree, applyPage);
    else if (lo.picker !== null && !event.target.closest(".lo-spells")) {
      lo.picker = null;
      render();
    }
  });

  Draft.onSync((state) => follow(state));

  window.Loadout = { get model() { return lo; }, get tree() { return tree; }, applyPage, ensureTree };
})();
