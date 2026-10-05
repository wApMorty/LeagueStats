// Grimoire des champions (SPEC-21 tâche 89) : overlay de pick et de ban manuel, ouvert par `Draft.openGrid()`.
// Le serveur trie et annote les tuiles ; ce module filtre (recherche sans accents, rôle, pool), pilote
// la sélection et la barre basse, et agit par les mêmes fonctions que les cartes de la rangée.
(() => {
  const plain = (text) =>
    text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  let grid = null; // l'overlay ouvert, ou null

  function close() {
    if (!grid) return;
    grid.element.remove();
    removeEventListener("keydown", grid.onKey);
    grid = null;
  }

  function visibleTiles() {
    return [...grid.element.querySelectorAll(".g-tile")].filter((tile) => !tile.hidden);
  }

  function applyFilters(quick) {
    const { element, query, role, poolOnly } = grid;
    let shown = 0;
    element.querySelectorAll(".g-tile").forEach((tile) => {
      const visible =
        (role === "all" || tile.dataset.roles.split(" ").includes(role)) &&
        (!poolOnly || tile.dataset.pool === "1") &&
        (!query || tile.dataset.search.includes(query));
      tile.hidden = !visible;
      if (visible) shown++;
    });
    element.querySelector("#g-count").textContent = `${shown} champion${shown > 1 ? "s" : ""}`;
    element.querySelector("#g-none").hidden = shown > 0;
    element.querySelectorAll("[data-role-chip]").forEach((chip) => {
      chip.classList.toggle("is-on", chip.dataset.roleChip === role);
    });
    const toggle = element.querySelector("[data-pool-toggle]");
    toggle.classList.toggle("is-on", poolOnly);
    toggle.setAttribute("aria-pressed", String(poolOnly));
    if (!Motion.opts().reduced) {
      visibleTiles()
        .slice(0, 48)
        .forEach((tile, i) =>
          tile.animate(
            [{ opacity: 0, transform: "scale(.55) translateY(12px) rotate(-8deg)" }, { opacity: 1, transform: "none" }],
            { duration: 420, delay: (quick ? 0 : 220) + i * (quick ? 6 : 14), easing: Motion.E.ressort, fill: "backwards" },
          ),
        );
    }
  }

  function select(tile) {
    if (!tile || tile.dataset.gone) return;
    const { element } = grid;
    element.querySelectorAll(".g-tile.is-sel").forEach((other) => other.classList.remove("is-sel"));
    tile.classList.add("is-sel");
    grid.selected = tile;
    const image = tile.querySelector("img")?.src ?? "";
    element.querySelector("#g-sel-img").src = image;
    element.querySelector("#g-sel-name").textContent = tile.dataset.name;
    element.querySelector("#g-sel-info").textContent = tile.dataset.info;
    const act = element.querySelector("#g-act");
    act.disabled = false;
    act.textContent = `${grid.ban ? "Bannir" : "Verrouiller"} ${tile.dataset.name}`;
    const id = +tile.dataset.id;
    if (grid.ban) Draft.aimBan(id, tile.dataset.name);
    else Draft.hoverPick(id, tile.dataset.name, image);
    if (!Motion.opts().reduced) Motion.bloom(tile.querySelector(".g-disc"), Motion.opts());
  }

  async function act() {
    if (!grid?.selected) return;
    const done = grid.ban ? await Draft.confirmBan() : await Draft.confirmLock();
    if (done) close();
  }

  async function open() {
    if (grid) return;
    const state = Draft.state;
    if (!state) return;
    const response = await fetch("/draft/champions");
    if (!response.ok) return;
    const host = document.getElementById("d-overlays");
    host.insertAdjacentHTML("beforeend", await response.text());
    const element = host.lastElementChild;
    const ban = element.dataset.mode === "ban";
    grid = {
      element,
      ban,
      query: "",
      role: element.dataset.role || "all",
      poolOnly: false,
      selected: null,
      onKey: (event) => event.key === "Escape" && close(),
    };
    addEventListener("keydown", grid.onKey);
    element.addEventListener("click", (event) => {
      if (event.target.closest("[data-grid-close]")) return close();
      const chip = event.target.closest("[data-role-chip]");
      if (chip) {
        grid.role = chip.dataset.roleChip;
        return applyFilters(true);
      }
      if (event.target.closest("[data-pool-toggle]")) {
        grid.poolOnly = !grid.poolOnly;
        return applyFilters(true);
      }
      if (event.target.closest("#g-act")) return act();
      select(event.target.closest(".g-tile"));
    });
    element.addEventListener("dblclick", (event) => {
      const tile = event.target.closest(".g-tile");
      if (!tile || tile.dataset.gone) return;
      select(tile);
      act();
    });
    element.addEventListener("keydown", (event) => {
      const tile = event.target.closest(".g-tile");
      if (tile && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        select(tile);
      }
    });
    element.querySelector("#g-q").addEventListener("input", (event) => {
      grid.query = plain(event.target.value.trim());
      applyFilters(true);
    });
    // L'aperçu de départ : ma cible actuelle, sinon rien.
    const current = ban ? Draft.banSelected || state.ban_hover_id : Draft.selected || state.hover_id;
    const start = current && element.querySelector(`.g-tile[data-id="${current}"]`);
    if (start && !start.dataset.gone) {
      start.classList.add("is-sel");
      grid.selected = start;
      element.querySelector("#g-sel-img").src = start.querySelector("img")?.src ?? "";
      element.querySelector("#g-sel-name").textContent = start.dataset.name;
      element.querySelector("#g-sel-info").textContent = start.dataset.info;
      const button = element.querySelector("#g-act");
      button.disabled = false;
      button.textContent = `${ban ? "Bannir" : "Verrouiller"} ${start.dataset.name}`;
    }
    applyFilters(false);
    if (!Motion.opts().reduced) {
      element.animate(
        [{ clipPath: "circle(0% at 78% 72%)" }, { clipPath: "circle(150% at 78% 72%)" }],
        { duration: 720, easing: Motion.E.standard },
      );
    }
    Draft.animate(element);
    element.querySelector("#g-q").focus();
  }

  // Le passage des bans aux picks (ou le verrouillage) change ce que la liste permet : on referme.
  Draft.onSync((state) => {
    if (grid && (grid.ban !== (state?.kind === "ban") || state?.locked_id)) close();
  });

  window.DraftGrid = { open, close };
})();
