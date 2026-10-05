// Banc `/_motion` (SPEC-21 tâche 84, critère 11) : p95 du temps d'image par scène, calque de particules
// et braises compris. Chaque scène tourne `data-scene-ms` ms ; l'image qui suit le départ est écartée.
(() => {
  const table = document.getElementById("bench-results");
  const budget = +table.dataset.budget;
  const duration = +table.dataset.sceneMs;
  const on = { sp: 1, reduced: false }; // le banc mesure l'animation pleine, quel que soit le réglage

  const spawn = (n) => {
    const x = innerWidth / 2;
    const y = innerHeight / 2;
    Motion.burst(x, y, { n, speed: 9, life: duration * 1.5, ring: false, size: 2.4 });
  };
  const SCENES = {
    braises: () => Motion.embers(2),
    particules: () => spawn(1600),
    trace: () => {
      const path = document.querySelector("[data-bench-trace]");
      path.dataset.trace = String(duration);
      Motion.intro(path.parentElement, on);
    },
    sceau: () => Motion.seal(document.getElementById("bench-seal"), { sp: 1 }),
  };

  const quantile = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];

  const measure = (key) =>
    new Promise((resolve) => {
      const deltas = [];
      let last = null;
      SCENES[key]();
      const start = performance.now();
      const step = (now) => {
        if (last !== null) deltas.push(now - last);
        last = now;
        if (now - start < duration) return requestAnimationFrame(step);
        Motion.embers(document.documentElement.dataset.motion === "reduit" ? 0 : 0.35);
        deltas.shift(); // la première image paie le démarrage de la scène
        resolve(deltas);
      };
      requestAnimationFrame(step);
    });

  const report = (key, deltas) => {
    const sorted = [...deltas].sort((a, b) => a - b);
    const cells = [
      document.querySelector(`[data-scene="${key}"]`).textContent,
      sorted.length,
      ...[0.5, 0.95, 0.99].map((q) => quantile(sorted, q).toFixed(1)),
      sorted[sorted.length - 1].toFixed(1),
      sorted.filter((d) => d > budget).length,
    ];
    const row = table.tBodies[0].insertRow();
    cells.forEach((value) => (row.insertCell().textContent = value));
    row.dataset.scene = key;
  };

  let busy = false;
  const runAll = async (keys) => {
    if (busy) return;
    busy = true;
    for (const key of keys) report(key, await measure(key));
    busy = false;
  };
  document.querySelectorAll("[data-scene]").forEach((button) => {
    button.onclick = () => runAll([button.dataset.scene]);
  });
  document.getElementById("bench-all").onclick = () => runAll(Object.keys(SCENES));
})();
