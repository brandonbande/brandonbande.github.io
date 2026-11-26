// Motion layer. Native APIs only; everything is optional.
// Content is visible by default: this module opts in to hidden-then-revealed states by
// adding .js-motion, so if it fails to load nothing stays hidden.
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const root = document.documentElement;

// ---- One-shot section reveals ------------------------------------------------------------
if (!reduced && 'IntersectionObserver' in window) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add('is-revealed');
      io.unobserve(e.target);
      e.target.querySelectorAll('[data-count]').forEach(countUp);
    }
  }, { threshold: 0.15, rootMargin: '0px 0px -5% 0px' });
  document.querySelectorAll('[data-reveal]').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.top < innerHeight && r.bottom > 0) el.classList.add('is-revealed'); // already on screen: no flash
    else io.observe(el);
  });
  root.classList.add('js-motion');
  // Stats sit inside panels, not reveal blocks: count them when they scroll in.
  const statIO = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { countUp(e.target); statIO.unobserve(e.target); }
  }, { threshold: 0.6 });
  document.querySelectorAll('[data-count]').forEach((el) => statIO.observe(el));
}

// ---- Count-up: runs once, always ends on the exact HTML text ------------------------------
function countUp(el) {
  if (el.dataset.counted) return;
  el.dataset.counted = '1';
  const final = el.textContent;
  const m = final.match(/^([^\d]*)([\d,]+)(.*)$/);
  if (!m) return;
  const target = Number(m[2].replace(/,/g, ''));
  const t0 = performance.now();
  const dur = 900;
  const step = (now) => {
    const k = Math.min(1, (now - t0) / dur);
    const v = Math.round(target * (1 - Math.pow(1 - k, 3)));
    el.textContent = k < 1 ? `${m[1]}${v.toLocaleString('en')}${m[3]}` : final;
    if (k < 1) requestAnimationFrame(step);
  };
  el.setAttribute('aria-label', final);
  requestAnimationFrame(step);
}

// ---- Identity emphasis: all three stay visible; emphasis moves every 2.4 s --------------------
const ids = [...document.querySelectorAll('[data-identities] li')];
if (ids.length && !reduced) {
  let i = 0;
  ids[0].classList.add('is-emphasised');
  setInterval(() => {
    if (document.hidden) return;
    ids[i].classList.remove('is-emphasised');
    i = (i + 1) % ids.length;
    ids[i].classList.add('is-emphasised');
  }, 2400);
}

// ---- Hero network: decorative canvas, ≤ 60/24 nodes, ≤ 30 fps, pauses off-screen ----------------
const canvas = document.querySelector('[data-network]');
if (canvas && canvas.getContext) {
  const ctx = canvas.getContext('2d');
  const styles = getComputedStyle(root);
  const lime = styles.getPropertyValue('--c-lime').trim() || 'currentColor';
  const paper = styles.getPropertyValue('--c-paper').trim() || 'currentColor';
  let nodes = [];
  let w = 0;
  let h = 0;
  let running = false;
  let last = 0;

  const resize = () => {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = w < 768 ? 24 : 60;
    nodes = Array.from({ length: n }, (_, k) => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.12, vy: (Math.random() - 0.5) * 0.12, hub: k % 9 === 0,
    }));
  };

  const draw = () => {
    ctx.clearRect(0, 0, w, h);
    const reach = Math.min(170, w / 5);
    for (let a = 0; a < nodes.length; a++) {
      for (let b = a + 1; b < nodes.length; b++) {
        const dx = nodes[a].x - nodes[b].x;
        const dy = nodes[a].y - nodes[b].y;
        const d = Math.hypot(dx, dy);
        if (d < reach) {
          ctx.globalAlpha = 0.14 * (1 - d / reach);
          ctx.strokeStyle = paper;
          ctx.beginPath(); ctx.moveTo(nodes[a].x, nodes[a].y); ctx.lineTo(nodes[b].x, nodes[b].y); ctx.stroke();
        }
      }
    }
    for (const p of nodes) {
      ctx.globalAlpha = p.hub ? 0.5 : 0.2;
      ctx.fillStyle = p.hub ? lime : paper;
      ctx.fillRect(p.x - 1.5, p.y - 1.5, 3, 3);
    }
    ctx.globalAlpha = 1;
  };

  const tick = (now) => {
    if (!running) return;
    requestAnimationFrame(tick);
    if (now - last < 33) return; // ≤ 30 fps
    last = now;
    for (const p of nodes) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
    }
    draw();
  };

  const start = () => { if (!running && !reduced && !document.hidden) { running = true; requestAnimationFrame(tick); } };
  const stop = () => { running = false; };

  resize();
  draw(); // reduced motion: one static frame
  window.addEventListener('resize', () => { resize(); draw(); });
  if (!reduced) {
    new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop())).observe(canvas);
    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
  }
}
