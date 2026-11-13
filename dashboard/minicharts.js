/* minicharts.js - dependency-free SVG charts (bar / stacked bar / line / band / reference line / hbar / scatter)
   Theme-aware through CSS variables; hover tooltips; redraws on resize. ~250 lines, no external requests. */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const h = (tag, attrs, parent, text) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };
  const tip = (() => {
    let t = null;
    return () => t || (t = Object.assign(document.body.appendChild(document.createElement('div')), { className: 'mc-tip' }));
  })();
  const showTip = (ev, html) => {
    const t = tip(); t.innerHTML = html; t.style.display = 'block';
    const w = t.offsetWidth, x = ev.clientX + 14 + w > innerWidth ? ev.clientX - w - 14 : ev.clientX + 14;
    t.style.left = x + 'px'; t.style.top = Math.max(8, ev.clientY - 10) + 'px';
  };
  const hideTip = () => { tip().style.display = 'none'; };

  function niceTicks(min, max, n = 5) {
    if (min === max) { max = min + 1; }
    const span = max - min, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0))), norm = step0 / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const lo = Math.floor(min / step + 1e-9) * step, hi = Math.ceil(max / step - 1e-9) * step, t = [];
    for (let v = lo; v <= hi + step / 2; v += step) t.push(+v.toFixed(10));
    return t;
  }
  const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

  function legend(svg, items, x0, y) {
    let x = x0;
    items.forEach(it => {
      if (it.dash) h('line', { x1: x, x2: x + 14, y1: y, y2: y, stroke: it.color, 'stroke-width': 2, 'stroke-dasharray': '4 3' }, svg);
      else h('rect', { x, y: y - 5, width: 10, height: 10, rx: 2, fill: it.color }, svg);
      const tx = x + (it.dash ? 19 : 15);
      h('text', { x: tx, y: y + 4, class: 'lg' }, svg, it.name);
      x = tx + it.name.length * 6.1 + 16;
    });
  }

  /* ------------------------------------------------------------------ category chart */
  function draw(el, s) {
    const W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return;
    const svg = h('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const n = s.labels.length, ser = s.series;
    const legendItems = ser.filter(x => x.legend !== false && x.type !== 'ref' || (x.type === 'ref' && x.legend));
    const hasY2 = ser.some(x => x.axis === 'right');
    const m = { l: 56, r: hasY2 ? 56 : 14, t: legendItems.length > 1 ? 28 : 10, b: 26 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;

    function domain(axis) {
      const mine = ser.filter(x => (x.axis || 'left') === axis);
      if (!mine.length) return null;
      const hasBar = mine.some(x => x.type === 'bar');
      let lo = Infinity, hi = -Infinity;
      const stacks = {};
      mine.forEach(x => {
        if (x.type === 'bar' && x.stack) {
          x.data.forEach((v, i) => { const k = x.stack + i; stacks[k] = stacks[k] || { p: 0, n: 0 }; v >= 0 ? stacks[k].p += v : stacks[k].n += v; });
        } else if (x.type === 'ref') { lo = Math.min(lo, x.value); hi = Math.max(hi, x.value); }
        else {
          (x.type === 'band' ? x.low.concat(x.high) : x.data).forEach(v => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
        }
      });
      Object.values(stacks).forEach(k => { hi = Math.max(hi, k.p); lo = Math.min(lo, k.n); });
      const zero = s[axis === 'right' ? 'zero2' : 'zero'] ?? hasBar;
      if (zero) { lo = Math.min(0, lo); hi = Math.max(0, hi); }
      else { const pad = (hi - lo) * 0.12 || 1; lo -= pad; hi += pad; }
      const ymin = s[axis === 'right' ? 'y2Min' : 'yMin'], ymax = s[axis === 'right' ? 'y2Max' : 'yMax'];
      if (ymin != null) lo = ymin; if (ymax != null) hi = ymax;
      const t = niceTicks(lo, hi, 5);
      return { ticks: t, d0: t[0], d1: t[t.length - 1] };
    }
    const DL = domain('left') || { ticks: [0, 1], d0: 0, d1: 1 }, DR = hasY2 ? domain('right') : null;
    const yL = v => m.t + ih - (v - DL.d0) / (DL.d1 - DL.d0) * ih;
    const yR = v => m.t + ih - (v - DR.d0) / (DR.d1 - DR.d0) * ih;
    const yOf = x => (x.axis === 'right' ? yR : yL);
    const bw = iw / n, xC = i => m.l + bw * (i + 0.5);
    const fL = s.yFmt || (v => v.toLocaleString()), fR = s.y2Fmt || fL;

    // grid + y axes
    DL.ticks.forEach(t => {
      h('line', { x1: m.l, x2: m.l + iw, y1: yL(t), y2: yL(t), class: t === 0 && DL.d0 < 0 ? 'axis0' : 'grid' }, svg);
      h('text', { x: m.l - 8, y: yL(t) + 4, 'text-anchor': 'end' }, svg, fL(t));
    });
    if (DR) DR.ticks.forEach(t => h('text', { x: m.l + iw + 8, y: yR(t) + 4 }, svg, fR(t)));
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / (s.xLabelWidth || 52)))));
    s.labels.forEach((l, i) => { if (i % every === 0 || i === n - 1 && (n - 1) % every === 0) h('text', { x: xC(i), y: H - 8, 'text-anchor': 'middle' }, svg, l); });

    // bands
    ser.filter(x => x.type === 'band').forEach(x => {
      const idx = x.low.map((v, i) => (v != null && x.high[i] != null) ? i : -1).filter(i => i >= 0);
      if (!idx.length) return;
      const up = idx.map(i => `${xC(i)},${yOf(x)(x.high[i])}`), dn = idx.slice().reverse().map(i => `${xC(i)},${yOf(x)(x.low[i])}`);
      h('polygon', { points: up.concat(dn).join(' '), fill: x.color, opacity: x.opacity || 0.16 }, svg);
    });

    // bars (grouped slots / stacks)
    const bars = ser.filter(x => x.type === 'bar');
    const slots = []; bars.forEach(x => { const k = x.stack || ('_' + x.name); if (!slots.includes(k)) slots.push(k); });
    const groupW = Math.min(bw * 0.72, s.maxBar ? s.maxBar * slots.length : 1e9), sw = groupW / slots.length;
    const acc = {};
    bars.forEach(x => {
      const si = slots.indexOf(x.stack || ('_' + x.name));
      x.data.forEach((v, i) => {
        if (v == null) return;
        const y0 = yOf(x)(0), cx = xC(i) - groupW / 2 + si * sw;
        let top, bot;
        if (x.stack) { const k = x.stack + i; acc[k] = acc[k] || { p: 0, n: 0 }; if (v >= 0) { bot = acc[k].p; acc[k].p += v; top = acc[k].p; } else { top = acc[k].n; acc[k].n += v; bot = acc[k].n; } }
        else { bot = 0; top = v; }
        const ya = yOf(x)(Math.max(top, bot)), yb = yOf(x)(Math.min(top, bot));
        const col = (x.colors && x.colors[i]) || x.color;
        h('rect', { x: cx + (x.stack ? 0 : 0.5), y: ya, width: Math.max(1, sw - (slots.length > 1 ? 1 : 0.5)), height: Math.max(0.5, yb - ya), fill: col, rx: x.stack ? 0 : 3 }, svg);
      });
    });

    // lines
    ser.filter(x => x.type === 'line').forEach(x => {
      let d = '', pen = false;
      x.data.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${xC(i).toFixed(1)},${yOf(x)(v).toFixed(1)}`; pen = true; });
      h('path', { d, fill: 'none', stroke: x.color, 'stroke-width': x.width || 2.4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': x.dash || '' }, svg);
      if (x.points) x.data.forEach((v, i) => v != null && h('circle', { cx: xC(i), cy: yOf(x)(v), r: 2.6, fill: x.color }, svg));
    });

    // reference lines
    ser.filter(x => x.type === 'ref').forEach(x => {
      const y = yOf(x)(x.value);
      h('line', { x1: m.l, x2: m.l + iw, y1: y, y2: y, stroke: x.color, 'stroke-width': 1.6, 'stroke-dasharray': '6 4' }, svg);
      if (x.label) h('text', { x: m.l + iw - 4, y: y - 5, 'text-anchor': 'end', class: 'reflbl' }, svg, x.label);
    });

    if (legendItems.length > 1) legend(svg, legendItems.map(x => ({ name: x.name, color: x.color, dash: x.type === 'ref' || (x.type === 'line' && x.dash) })), m.l, 12);

    // hover
    const guide = h('line', { y1: m.t, y2: m.t + ih, class: 'guide', opacity: 0 }, svg);
    const hit = h('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent' }, svg);
    hit.addEventListener('mousemove', ev => {
      const r = svg.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.floor((ev.clientX - r.left - m.l) / bw)));
      guide.setAttribute('x1', xC(i)); guide.setAttribute('x2', xC(i)); guide.setAttribute('opacity', 1);
      const rows = ser.filter(x => x.type !== 'ref' && x.tip !== false).map(x => {
        const v = x.type === 'band' ? null : x.data[i];
        if (x.type === 'band') { return x.low[i] == null ? '' : `<div><i style="background:${x.color}"></i>${esc(x.name)}: ${(x.fmt || fL)(x.low[i])} - ${(x.fmt || fL)(x.high[i])}</div>`; }
        if (v == null) return '';
        const real = x.rawSign ? Math.abs(v) : v;
        return `<div><i style="background:${(x.colors && x.colors[i]) || x.color}"></i>${esc(x.name)}: <b>${(x.fmt || (x.axis === 'right' ? fR : fL))(real)}</b></div>`;
      }).join('');
      showTip(ev, `<div class="tt">${esc(s.labels[i])}</div>${rows}`);
    });
    hit.addEventListener('mouseleave', () => { guide.setAttribute('opacity', 0); hideTip(); });
  }

  /* ------------------------------------------------------------------ horizontal bar */
  function hbar(el, s) {
    const W = el.clientWidth, H = el.clientHeight; if (!W || !H) return;
    const svg = h('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const lw = Math.min(170, Math.max(...s.labels.map(l => l.length)) * 6.4 + 12), m = { l: lw, r: 56, t: 6, b: s.xTitle ? 34 : 22 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b, n = s.labels.length, bh = ih / n;
    const ticks = niceTicks(0, Math.max(...s.values) * 1.02, 4), d1 = ticks[ticks.length - 1], xS = v => m.l + v / d1 * iw;
    const f = s.fmt || (v => v.toLocaleString());
    ticks.forEach(t => { h('line', { x1: xS(t), x2: xS(t), y1: m.t, y2: m.t + ih, class: 'grid' }, svg); h('text', { x: xS(t), y: H - (s.xTitle ? 20 : 6), 'text-anchor': 'middle' }, svg, (s.tickFmt || f)(t)); });
    if (s.xTitle) h('text', { x: m.l + iw / 2, y: H - 4, 'text-anchor': 'middle' }, svg, s.xTitle);
    s.labels.forEach((l, i) => {
      const y = m.t + i * bh + bh * 0.16, hh = bh * 0.68, v = s.values[i];
      h('text', { x: m.l - 8, y: y + hh / 2 + 4, 'text-anchor': 'end', class: 'cat' }, svg, l);
      const r = h('rect', { x: m.l, y, width: Math.max(1, xS(v) - m.l), height: hh, fill: (s.colors && s.colors[i]) || s.color, rx: 3 }, svg);
      h('text', { x: xS(v) + 6, y: y + hh / 2 + 4, class: 'val' }, svg, f(v));
      r.addEventListener('mousemove', ev => showTip(ev, `<div class="tt">${esc(l)}</div><div>${esc(s.name || 'Value')}: <b>${f(v)}</b></div>${s.extra ? s.extra[i] : ''}`));
      r.addEventListener('mouseleave', hideTip);
    });
  }

  /* ------------------------------------------------------------------ scatter (calibration) */
  function scatter(el, s) {
    const W = el.clientWidth, H = el.clientHeight; if (!W || !H) return;
    const svg = h('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const m = { l: 54, r: 16, t: 12, b: 42 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    const mx = Math.max(...s.points.map(p => Math.max(p.x, p.y))) * 1.1, ticks = niceTicks(0, mx, 5), d1 = ticks[ticks.length - 1];
    const xS = v => m.l + v / d1 * iw, yS = v => m.t + ih - v / d1 * ih, f = s.fmt || (v => v);
    ticks.forEach(t => {
      h('line', { x1: m.l, x2: m.l + iw, y1: yS(t), y2: yS(t), class: 'grid' }, svg); h('text', { x: m.l - 8, y: yS(t) + 4, 'text-anchor': 'end' }, svg, f(t));
      h('text', { x: xS(t), y: m.t + ih + 16, 'text-anchor': 'middle' }, svg, f(t));
    });
    h('text', { x: m.l + iw / 2, y: H - 6, 'text-anchor': 'middle' }, svg, s.xTitle);
    h('text', { x: 12, y: m.t + ih / 2, 'text-anchor': 'middle', transform: `rotate(-90 12 ${m.t + ih / 2})` }, svg, s.yTitle);
    h('line', { x1: xS(0), y1: yS(0), x2: xS(d1), y2: yS(d1), stroke: 'var(--mute)', 'stroke-dasharray': '5 4', 'stroke-width': 1.4 }, svg);
    s.points.forEach((p, i) => {
      const c = h('circle', { cx: xS(p.x), cy: yS(p.y), r: 6, fill: s.color, opacity: 0.9, stroke: 'var(--card)', 'stroke-width': 1.5 }, svg);
      c.addEventListener('mousemove', ev => showTip(ev, `<div class="tt">Risk decile ${i + 1}</div><div>Predicted: <b>${f(p.x)}</b></div><div>Observed: <b>${f(p.y)}</b></div>`));
      c.addEventListener('mouseleave', hideTip);
    });
    legend(svg, [{ name: 'Risk deciles', color: s.color }, { name: 'Perfect calibration', color: 'var(--mute)', dash: true }], m.l, 8 + 4);
  }

  function mount(fn) {
    return (idOrEl, spec) => {
      const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
      const render = () => { el.innerHTML = ''; fn(el, spec); };
      el._w = el.clientWidth; render();
      if (el._ro) el._ro.disconnect();
      el._ro = new ResizeObserver(() => { if (el.clientWidth !== el._w) { el._w = el.clientWidth; render(); } });
      el._ro.observe(el);
    };
  }
  window.MC = { chart: mount(draw), hbar: mount(hbar), scatter: mount(scatter) };
})();
