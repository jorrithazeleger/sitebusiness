// Sneeuw op een canvas. Respecteert 'minder beweging'.
import { reducedMotion } from './util.js';

export function startSneeuw(canvas) {
  const ctx = canvas.getContext('2d');
  let w = 0, h = 0, dpr = 1;
  let flakes = [];
  let wind = 0, windTarget = 0, gust = 0;
  let intensity = 1;
  let running = true;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const target = Math.min(180, Math.round((w * h) / 8000));
    while (flakes.length < target) flakes.push(make(true));
    flakes.length = target;
  }

  function make(anywhere) {
    const z = Math.random();
    return {
      x: Math.random() * w,
      y: anywhere ? Math.random() * h : -10,
      z,
      r: 0.6 + z * 2.6,
      vy: 0.25 + z * 0.9,
      sway: Math.random() * Math.PI * 2,
      swaySpeed: 0.004 + Math.random() * 0.012,
      a: 0.35 + z * 0.6,
    };
  }

  let last = performance.now();
  function tick(now) {
    if (!running) return;
    const dt = Math.min(3, (now - last) / 16.67);
    last = now;
    if (Math.random() < 0.003) windTarget = (Math.random() - 0.4) * 1.2;
    wind += (windTarget + gust - wind) * 0.01 * dt;
    gust *= 0.97;
    ctx.clearRect(0, 0, w, h);
    const visible = Math.round(flakes.length * Math.min(1, intensity));
    for (let i = 0; i < visible; i++) {
      const f = flakes[i];
      f.sway += f.swaySpeed * dt;
      f.y += f.vy * dt * (1 + gust * 0.15);
      f.x += (Math.sin(f.sway) * 0.4 + wind * (0.4 + f.z)) * dt;
      if (f.y > h + 10 || f.x < -20 || f.x > w + 20) {
        Object.assign(f, make(false));
        if (wind > 0.5) f.x = Math.random() * w * 0.6 - 20;
        if (wind < -0.5) f.x = w * 0.4 + Math.random() * w * 0.6 + 20;
      }
      ctx.globalAlpha = f.a;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(tick);
  }

  if (reducedMotion()) {
    canvas.style.display = 'none';
    return { vlaag() {}, sterkte() {} };
  }
  resize();
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', () => {
    running = !document.hidden;
    if (running) { last = performance.now(); requestAnimationFrame(tick); }
  });
  requestAnimationFrame(tick);

  return {
    vlaag(kracht = 6) { gust = kracht; },
    sterkte(n) { intensity = n; },
  };
}
