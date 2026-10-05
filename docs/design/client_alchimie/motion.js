// Primitives de motion du thème « Alchimie » (SPEC-21 §4.3) : CSS + Web Animations API + un calque canvas
// natif pour les particules (étincelles, braises, runes). Zéro dépendance.
// Attributs lus : data-trace="ms" (tracé SVG, avec plume d'étincelles), data-rise, data-pop, data-fade,
// data-spell (texte qui se transmute depuis des runes), data-delay="ms", data-spin="s", data-glow="ms",
// data-ink="ms", data-count, data-ring, data-tilt (inclinaison 3D au survol), data-seal / data-shock / data-flash / data-quake.
(function () {
  if (window.Motion) return; // chargé par chaque écran : une seule instance
  const E = {
    standard: 'cubic-bezier(.65,0,.35,1)',
    entree: 'cubic-bezier(.22,1,.36,1)',
    ressort: 'cubic-bezier(.2,.8,.2,1)',
    sceau: 'cubic-bezier(.3,0,.2,1)',
    rebond: 'cubic-bezier(.34,1.56,.64,1)',
  };
  const RUNES = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ';
  // Complémentaires : cuivre (55) ↔ violet électrique (≈235–295), menthe (165) ↔ magenta (≈345).
  const C = { mint: 'oklch(0.88 0.12 165)', copper: 'oklch(0.8 0.14 55)', gold: 'oklch(0.92 0.11 85)', rose: 'oklch(0.78 0.15 355)', white: 'oklch(0.99 0.02 110)',
    violet: 'oklch(0.66 0.24 290)', magenta: 'oklch(0.7 0.27 345)', blue: 'oklch(0.72 0.18 245)', ink: 'oklch(0.08 0.02 290)' };
  const PAL = [C.mint, C.copper, C.gold, C.violet];
  const COMP = { [C.copper]: C.violet, [C.gold]: C.blue, [C.mint]: C.magenta };
  const D = el => +(el.dataset.delay || 0);
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = a => a[(Math.random() * a.length) | 0];
  const inOut = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const out3 = t => 1 - Math.pow(1 - t, 3);
  const fmt = (n, d) => n.toFixed(d).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');

  // ---------- calque de particules ----------
  const FX = { cv: null, ctx: null, P: [], tasks: new Set(), on: false, last: 0, embers: 0, acc: 0, dpr: 1, font: '', freeze: 0, under: [] };
  function ensure() {
    if (FX.cv) return;
    document.querySelectorAll('canvas[data-motion-fx]').forEach(c => c.remove());
    const cv = document.createElement('canvas');
    cv.setAttribute('aria-hidden', 'true');
    cv.setAttribute('data-motion-fx', '');
    cv.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:2147483000;';
    document.body.appendChild(cv);
    FX.cv = cv; FX.ctx = cv.getContext('2d');
    const fit = () => { FX.dpr = Math.min(2, window.devicePixelRatio || 1); cv.width = innerWidth * FX.dpr; cv.height = innerHeight * FX.dpr; };
    fit(); addEventListener('resize', fit);
  }
  function add(p) {
    ensure();
    p.age = 0;
    if (FX.P.length > 1600) FX.P.splice(0, FX.P.length - 1600);
    FX.P.push(p);
    run();
  }
  function run() { if (FX.on) return; ensure(); FX.on = true; FX.last = performance.now(); requestAnimationFrame(frame); }
  function task(fn) { FX.tasks.add(fn); run(); }
  function frame(now) {
    let dt = Math.min(50, now - FX.last); FX.last = now;
    if (now < FX.freeze) dt = 0; // arrêt sur image
    const k = dt / 16.67;
    FX.tasks.forEach(t => { if (t(now) === false) FX.tasks.delete(t); });
    if (FX.embers > 0) { FX.acc += FX.embers * k; while (FX.acc >= 1) { FX.acc -= 1; ember(); } }
    const c = FX.ctx, d = FX.dpr;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, FX.cv.width, FX.cv.height); c.setTransform(d, 0, 0, d, 0, 0);
    FX.under.forEach(fn => fn(c)); FX.under.length = 0;
    c.globalCompositeOperation = 'lighter'; c.lineCap = 'round';
    const P = FX.P, born = []; let j = 0;
    for (let i = 0; i < P.length; i++) {
      const p = P[i];
      p.age += dt;
      if (p.age >= p.life) { if (p.end) p.end(born); continue; }
      P[j++] = p;
      const t = p.age / p.life, f = 1 - t;
      if (p.kind === 'spark') {
        const dr = Math.pow(p.drag, k); p.vx *= dr; p.vy = p.vy * dr + p.g * k; p.x += p.vx * k; p.y += p.vy * k;
        c.globalAlpha = f * p.a; c.strokeStyle = p.color; c.lineWidth = p.size * (0.35 + 0.65 * f);
        c.beginPath(); c.moveTo(p.x - p.vx * p.trail, p.y - p.vy * p.trail); c.lineTo(p.x, p.y); c.stroke();
        if (p.size > 1.8) { c.globalAlpha = f * p.a * 0.22; c.lineWidth = p.size * 3.2; c.stroke(); }
      } else if (p.kind === 'ember') {
        p.x += (p.vx + Math.sin(p.age * 0.002 + p.ph) * 0.35) * k; p.y += p.vy * k;
        c.globalAlpha = p.a * Math.min(1, t * 6) * f * (0.7 + 0.3 * Math.sin(p.age * 0.012 + p.ph)); c.fillStyle = p.color;
        c.beginPath(); c.arc(p.x, p.y, p.size, 0, 6.283); c.fill();
        c.globalAlpha *= 0.25; c.beginPath(); c.arc(p.x, p.y, p.size * 3.5, 0, 6.283); c.fill();
      } else if (p.kind === 'ring') {
        const e = out3(t), r = p.r0 + (p.r1 - p.r0) * e;
        c.globalAlpha = f * p.a; c.strokeStyle = p.color; c.lineWidth = p.w * f + 0.5;
        c.beginPath(); c.arc(p.x, p.y, r, 0, 6.283); c.stroke();
      } else if (p.kind === 'glyph' || p.kind === 'orbit') {
        let x = p.x, y = p.y, a = f;
        if (p.kind === 'orbit') {
          const e = inOut(t), r = p.R * (1 - e), ang = p.a0 + p.spin * e;
          x = p.cx + Math.cos(ang) * r; y = p.cy + Math.sin(ang) * r; a = Math.min(1, t * 4) * (0.4 + 0.6 * e);
        } else {
          const dr = Math.pow(p.drag, k); p.vx *= dr; p.vy = p.vy * dr + p.g * k; p.x += p.vx * k; p.y += p.vy * k; x = p.x; y = p.y; p.rot += p.vr * k;
        }
        const font = `${p.size | 0}px "Noto Sans Runic", serif`;
        if (FX.font !== font) { c.font = font; FX.font = font; }
        c.save(); c.translate(x, y); c.rotate(p.rot || 0);
        c.globalAlpha = a * p.a; c.fillStyle = p.color; c.textAlign = 'center'; c.textBaseline = 'middle';
        c.fillText(p.ch, 0, 0); c.restore();
      }
    }
    P.length = j;
    born.forEach(p => { p.age = 0; P.push(p); });
    if (P.length || FX.tasks.size || FX.embers > 0) requestAnimationFrame(frame);
    else { FX.on = false; c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, FX.cv.width, FX.cv.height); }
  }
  function spark(x, y, o = {}) {
    const ang = o.ang ?? rnd(0, 6.283), sp = o.v ?? rnd(1, 6);
    return { kind: 'spark', x, y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, g: o.g ?? 0.05, drag: o.drag ?? 0.94, life: o.life ?? rnd(500, 1100), size: o.size ?? rnd(0.8, 2.6), color: o.color ?? pick(PAL), a: o.a ?? 1, trail: o.trail ?? 2.2 };
  }
  function ember() {
    add({ kind: 'ember', x: rnd(0, innerWidth), y: innerHeight + 10, vx: rnd(-0.25, 0.25), vy: rnd(-0.5, -1.5), life: rnd(4000, 8000), size: rnd(0.6, 1.7), color: pick([C.copper, C.mint, C.gold, C.violet, C.magenta]), a: rnd(0.35, 0.85), ph: rnd(0, 6.28) });
  }

  // Explosion d'étincelles, d'anneaux et de runes à (x, y) écran.
  function burst(x, y, o = {}) {
    if (o.reduced) return;
    const base = o.colors ?? PAL, cols = o.comp === false ? base : [...base, ...base.map(c => COMP[c]).filter(Boolean)], speed = o.speed ?? 7, n = o.n ?? 80;
    for (let i = 0; i < n; i++) add(spark(x, y, { v: rnd(0.25, 1) * speed, life: rnd(0.5, 1) * (o.life ?? 1100), size: rnd(0.8, o.size ?? 2.8), color: pick(cols), g: o.g ?? 0.06, drag: o.drag ?? 0.935 }));
    if (o.ring !== false) {
      const R = o.ringR ?? 180;
      add({ kind: 'ring', x, y, r0: 6, r1: R, w: o.ringW ?? 5, life: o.ringLife ?? 750, color: cols[0], a: 0.9 });
      add({ kind: 'ring', x, y, r0: 4, r1: R * 0.62, w: (o.ringW ?? 5) * 0.6, life: (o.ringLife ?? 750) * 0.8, color: COMP[base[0]] || cols[1] || cols[0], a: 0.85 });
      add({ kind: 'ring', x, y, r0: 2, r1: R * 1.25, w: (o.ringW ?? 5) * 0.35, life: (o.ringLife ?? 750) * 1.2, color: C.white, a: 0.5 });
    }
    for (let i = 0; i < (o.glyphs ?? 0); i++) {
      const ang = rnd(0, 6.283), v = rnd(2, 6) * (speed / 7);
      add({ kind: 'glyph', ch: pick(RUNES), x, y, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v, g: 0.02, drag: 0.95, rot: rnd(-0.5, 0.5), vr: rnd(-0.06, 0.06), size: rnd(14, 30), life: rnd(900, 1600), color: pick(cols), a: 0.95 });
    }
  }
  function center(el) { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, r]; }
  function burstAt(el, o = {}) { if (!el) return; const [x, y] = center(el); burst(x, y, o); }
  // Runes qui convergent en spirale vers (x, y) ; étincelle à l'arrivée.
  function converge(x, y, o = {}) {
    if (o.reduced) return;
    const n = o.n ?? 48, R = o.radius ?? 600, life = o.life ?? 1200, cols = o.colors ?? PAL;
    for (let i = 0; i < n; i++) {
      const color = pick(cols);
      add({ kind: 'orbit', ch: pick(RUNES), cx: x, cy: y, R: R * rnd(0.6, 1.25), a0: rnd(0, 6.283), spin: rnd(1.2, 2.8) * (o.dir ?? 1), size: rnd(14, 28), life: life * rnd(0.7, 1), delay: 0, color, a: 1, rot: 0,
        end: born => { for (let s = 0; s < 3; s++) { const p = spark(x, y, { v: rnd(1, 4), color, life: 500 }); born.push(p); } } });
    }
  }
  function embers(rate) { FX.embers = rate || 0; if (rate) run(); }

  let flashEl = null;
  function flash(color = C.white, peak = 0.5, dur = 380) {
    if (!flashEl) { flashEl = document.createElement('div'); flashEl.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147482999;opacity:0;mix-blend-mode:screen;'; document.body.appendChild(flashEl); }
    flashEl.style.background = `radial-gradient(circle at 50% 50%, ${color} 0%, transparent 70%)`;
    flashEl.animate([{ opacity: 0 }, { opacity: peak, offset: 0.18 }, { opacity: 0 }], { duration: dur, easing: 'ease-out' });
  }
  function shake(el, amp = 6, dur = 420) {
    if (!el) return;
    const f = [];
    for (let i = 0; i <= 8; i++) { const a = amp * (1 - i / 8); f.push({ transform: i === 8 ? 'translate(0,0)' : `translate(${rnd(-a, a).toFixed(1)}px,${rnd(-a, a).toFixed(1)}px)` }); }
    el.animate(f, { duration: dur, easing: 'linear', composite: 'add' });
  }

  // ---------- impact frames ----------
  // Trois images de choc façon anime : négatif (page inversée, traits d'encre), noir + lignes de vitesse blanches,
  // complémentaire saturée + lignes de la couleur primaire ; puis aberration chromatique, coup de zoom et arrêt sur image.
  let impEl = null;
  function lines(c, x, y, n, color, w, r0, len) {
    c.fillStyle = color;
    for (let i = 0; i < n; i++) {
      const a = rnd(0, 6.283), r1 = rnd(r0 * 0.6, r0 * 1.4), r2 = r1 + rnd(len * 0.4, len), hw = rnd(w * 0.3, w) / 2;
      const px = -Math.sin(a), py = Math.cos(a);
      c.beginPath();
      c.moveTo(x + Math.cos(a) * r1, y + Math.sin(a) * r1);
      c.lineTo(x + Math.cos(a) * r2 + px * hw, y + Math.sin(a) * r2 + py * hw);
      c.lineTo(x + Math.cos(a) * r2 - px * hw, y + Math.sin(a) * r2 - py * hw);
      c.closePath(); c.fill();
    }
  }
  function impact(x, y, o = {}) {
    if (o.reduced) return;
    ensure();
    if (!impEl) { impEl = document.createElement('div'); impEl.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147482998;opacity:0;'; document.body.appendChild(impEl); }
    const prim = o.color ?? C.copper, comp = o.comp ?? COMP[prim] ?? C.violet, f = o.frameMs ?? 50;
    const W = Math.hypot(innerWidth, innerHeight);
    // Une seule image : voile complémentaire léger + lignes de vitesse fines, sans négatif ni arrêt global.
    const draw = c => { c.save(); c.globalCompositeOperation = 'source-over'; c.globalAlpha = 0.35; lines(c, x, y, 46, prim, 6, 160, W * 0.7); c.globalAlpha = 0.5; lines(c, x, y, 18, C.white, 3, 180, W * 0.45); c.restore(); };
    const t0 = performance.now();
    FX.freeze = t0 + f + (o.hold ?? 0);
    task(now => {
      if (now - t0 < f) { impEl.style.background = `radial-gradient(circle at ${x}px ${y}px, transparent 0%, ${comp} 75%)`; impEl.style.mixBlendMode = 'soft-light'; impEl.style.opacity = 0.55; FX.under.push(draw); return true; }
      impEl.animate([{ opacity: 0.3 }, { opacity: 0 }], { duration: 220, easing: 'ease-out' });
      impEl.style.opacity = 0;
      return false;
    });
    const tg = o.target;
    if (tg) setTimeout(() => tg.animate([{ filter: `drop-shadow(4px 0 0 ${comp}) drop-shadow(-4px 0 0 ${prim}) saturate(1.25)` }, { filter: 'none' }], { duration: 240, easing: 'ease-out' }), f);
  }

  // ---------- tracés ----------
  function trace(el, dur, delay, sp, pen = true) {
    if (!el.getTotalLength) return;
    const L = el.getTotalLength();
    if (!L) return;
    el.style.strokeDasharray = `${L} ${L}`;
    el.animate([{ strokeDashoffset: L }, { strokeDashoffset: 0 }], { duration: dur / sp, delay: delay / sp, easing: E.standard, fill: 'both' });
    if (!pen || L < 160) return;
    const t0 = performance.now() + delay / sp, d = dur / sp, color = el.dataset.pen || pick([C.copper, C.gold, C.mint]);
    task(now => {
      const t = (now - t0) / d;
      if (t < 0) return true;
      if (t > 1 || !el.isConnected) return false;
      const m = el.getScreenCTM(); if (!m) return false;
      const pt = el.getPointAtLength(L * inOut(t));
      const x = m.a * pt.x + m.c * pt.y + m.e, y = m.b * pt.x + m.d * pt.y + m.f;
      add(spark(x, y, { v: rnd(0.3, 2.2), life: rnd(300, 700), size: rnd(0.8, 2.2), color, g: 0.03 }));
      add({ kind: 'ring', x, y, r0: 1, r1: 5, w: 1.5, life: 120, color: C.white, a: 0.4 });
      return true;
    });
  }

  function fixRings(root) {
    root.querySelectorAll('text[data-ring]').forEach(t => {
      if (t.__ring) return;
      t.__ring = true;
      t.setAttribute('textLength', t.dataset.ring);
      t.setAttribute('lengthAdjust', 'spacing');
    });
  }

  function count(el, sp) {
    const to = +el.dataset.count, dec = +(el.dataset.dec || 0), suf = el.dataset.suffix || '';
    const node = el.firstChild;
    if (!node || node.nodeType !== 3) return;
    const final = node.nodeValue;
    const t0 = performance.now() + D(el) / sp, dur = 1300 / sp;
    const step = now => {
      const p = Math.max(0, Math.min(1, (now - t0) / dur));
      node.nodeValue = p >= 1 ? final : fmt(to * (1 - Math.pow(1 - p, 4)), dec) + suf;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // Texte qui se transmute : chaque lettre passe par des runes avant de se fixer (décor, jamais porteur de sens).
  function spell(el, sp) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const final = node.nodeValue; if (!final.trim()) return;
      const n = final.length, t0 = performance.now() + D(el) / sp, dur = (520 + n * 26) / sp;
      const at = [...final].map((_, i) => (i / n) * 0.65 + Math.random() * 0.35);
      const step = now => {
        const p = (now - t0) / dur;
        if (p >= 1 || !node.isConnected) { node.nodeValue = final; return; }
        node.nodeValue = [...final].map((ch, i) => (ch === ' ' || p >= at[i] ? ch : p < 0 ? '\u2002' : RUNES[(Math.random() * RUNES.length) | 0])).join('');
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  function intro(root, o = {}) {
    if (!root) return;
    const sp = Math.max(0.25, o.sp || 1);
    fixRings(root);
    root.querySelectorAll('[data-trace],[data-rise],[data-pop],[data-fade]').forEach(el => el.getAnimations().forEach(a => a.cancel()));
    if (o.reduced) return;
    root.querySelectorAll('[data-trace]').forEach(el => trace(el, +el.dataset.trace, D(el), sp, o.pen !== false));
    root.querySelectorAll('[data-rise]').forEach(el => el.animate(
      [{ opacity: 0, transform: 'perspective(900px) translateY(34px) rotateX(38deg) scale(.96)' }, { opacity: 1, transform: 'perspective(900px) translateY(0) rotateX(0) scale(1)' }],
      { duration: 900 / sp, delay: D(el) / sp, easing: E.entree, fill: 'backwards' }));
    root.querySelectorAll('[data-pop]').forEach(el => {
      el.animate(
        [{ opacity: 0, transform: 'scale(.2) rotate(-70deg)' }, { opacity: 1, transform: 'scale(1.14) rotate(6deg)', offset: 0.68 }, { opacity: 1, transform: 'scale(1) rotate(0)' }],
        { duration: 760 / sp, delay: D(el) / sp, easing: E.ressort, fill: 'backwards' });
      setTimeout(() => el.isConnected && burstAt(el, { n: 18, speed: 4, life: 700, ringR: 70, ringW: 3, size: 2 }), (D(el) + 500) / sp);
    });
    root.querySelectorAll('[data-fade]').forEach(el => el.animate(
      [{ opacity: 0 }, { opacity: 1 }], { duration: 1000 / sp, delay: D(el) / sp, easing: 'ease-out', fill: 'backwards' }));
    root.querySelectorAll('[data-spell]').forEach(el => spell(el, sp));
    root.querySelectorAll('[data-count]').forEach(el => count(el, sp));
  }

  function tilt(el) {
    if (el.__tilt) return;
    el.__tilt = true;
    el.style.transformStyle = 'preserve-3d';
    el.addEventListener('pointermove', e => {
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(900px) rotateX(${(-y * 10).toFixed(2)}deg) rotateY(${(x * 12).toFixed(2)}deg) translateZ(14px)`;
      el.style.transition = 'transform 80ms linear';
    });
    el.addEventListener('pointerleave', () => { el.style.transition = 'transform 600ms cubic-bezier(.2,.8,.2,1)'; el.style.transform = ''; });
  }

  function ambient(root, o = {}) {
    if (!root) return;
    fixRings(root);
    const sp = Math.max(0.25, o.sp || 1);
    if (o.reduced) return;
    root.querySelectorAll('[data-spin]').forEach(el => {
      if (el.__spun) return;
      el.__spun = true;
      const s = +el.dataset.spin;
      el.animate([{ transform: 'rotate(0deg)' }, { transform: `rotate(${s > 0 ? 360 : -360}deg)` }], { duration: (Math.abs(s) * 1000) / sp, iterations: Infinity });
    });
    root.querySelectorAll('[data-glow]').forEach(el => {
      if (el.__glow) return;
      el.__glow = true;
      el.animate([{ opacity: 0.3 }, { opacity: 1 }, { opacity: 0.3 }], { duration: +el.dataset.glow / sp, iterations: Infinity, easing: 'ease-in-out' });
    });
    root.querySelectorAll('[data-ink]').forEach(el => {
      if (el.__ink) return;
      el.__ink = true;
      trace(el, +el.dataset.ink, D(el), sp);
    });
    root.querySelectorAll('[data-tilt]').forEach(tilt);
  }

  // Sceau apposé : tampon, explosion d'étincelles et de runes, ondes, éclair, secousse.
  function seal(root, o = {}) {
    if (!root) return;
    const sp = o.reduced ? 100 : Math.max(0.25, o.sp || 1);
    const cols = o.colors ?? [C.copper, C.gold, C.mint, C.white];
    root.querySelectorAll('[data-seal]').forEach(el => {
      el.animate(
        [{ transform: 'scale(3.4) rotate(-40deg)', opacity: 0 }, { transform: 'scale(.86) rotate(8deg)', opacity: 1, offset: 0.58 }, { transform: 'scale(1.06) rotate(-3deg)', offset: 0.8 }, { transform: 'scale(1) rotate(0deg)', opacity: 1 }],
        { duration: 680 / sp, easing: E.sceau, fill: 'backwards' });
      if (!o.reduced) setTimeout(() => {
        const [x, y] = center(el);
        impact(x, y, { color: cols[0], target: o.target });
        setTimeout(() => { burst(x, y, { n: 170, speed: 14, glyphs: 24, ringR: 360, ringW: 8, colors: cols, life: 1400 }); flash(COMP[cols[0]] || cols[0], 0.3, 520); }, 60);
      }, 380 / sp);
    });
    root.querySelectorAll('[data-shock]').forEach((el, i) => el.animate(
      [{ transform: 'scale(.7)', opacity: 0.95 }, { transform: 'scale(3.2)', opacity: 0 }],
      { duration: 1100 / sp, delay: (360 + i * 140) / sp, easing: 'cubic-bezier(.15,.7,.2,1)', fill: 'both' }));
    root.querySelectorAll('[data-flash]').forEach(el => el.animate([{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 0 }], { duration: 1600 / sp, delay: 320 / sp }));
    if (!o.reduced) root.querySelectorAll('[data-quake]').forEach(el => setTimeout(() => shake(el, 9, 460), 380 / sp + 60));
  }

  function bloom(el, o = {}) {
    if (!el || o.reduced) return;
    const sp = Math.max(0.25, o.sp || 1);
    el.animate([{ transform: 'scale(.5) rotate(-20deg)', opacity: 0.2 }, { transform: 'scale(1.18) rotate(4deg)', opacity: 1, offset: 0.6 }, { transform: 'scale(1)', opacity: 1 }], { duration: 520 / sp, easing: E.ressort });
    burstAt(el, { n: 26, speed: 5, life: 700, ringR: 70, ringW: 3, glyphs: 3, size: 2.2, colors: o.colors });
  }

  window.Motion = { E, C, COMP, impact, trace, intro, ambient, seal, bloom, fixRings, burst, burstAt, converge, embers, flash, shake, spell, center };
})();
