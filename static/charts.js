/* Tiny dependency-free SVG charts drawing with design tokens. */
const Charts = (() => {
  const W = 640, H = 220, P = { l: 52, r: 12, t: 12, b: 26 };
  const fmt = v => v == null ? '' : Math.abs(v) >= 1000 ? (v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1) + 'k' : (Math.abs(v) < 10 ? (+v).toFixed(1) : Math.round(v));
  function scale(vals, h) {
    const f = vals.filter(v => v != null && isFinite(v));
    let lo = Math.min(...f), hi = Math.max(...f);
    if (!f.length) { lo = 0; hi = 1; }
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    return { lo, hi, y: v => P.t + (h - P.t - P.b) * (1 - (v - lo) / (hi - lo)) };
  }
  // opts: {labels:[...], series:[{name, values, color, dash, width}], band:[[lo,hi],...], band2, zero:true, height}
  function line(opts) {
    const h = opts.height || H, n = opts.labels.length;
    const all = [].concat(...opts.series.map(s => s.values), ...(opts.band || []).flat(), ...(opts.band2 || []).flat(), opts.zero ? [0] : []);
    const s = scale(all, h);
    const x = i => P.l + (W - P.l - P.r) * (n === 1 ? 0.5 : i / (n - 1));
    let g = '';
    for (let k = 0; k <= 4; k++) {
      const v = s.lo + (s.hi - s.lo) * k / 4, y = s.y(v);
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="var(--ct-color-border-subtle)"/><text x="${P.l - 6}" y="${y + 4}" text-anchor="end">${fmt(v)}</text>`;
    }
    const area = (band, fill) => {
      if (!band || !band.length) return '';
      const top = band.map((b, i) => b ? `${x(i)},${s.y(b[1])}` : null).filter(Boolean);
      const bot = band.map((b, i) => b ? `${x(i)},${s.y(b[0])}` : null).filter(Boolean).reverse();
      return `<polygon points="${top.concat(bot).join(' ')}" fill="${fill}" />`;
    };
    g += area(opts.band2, 'var(--ct-color-surface-sunken)') + area(opts.band, 'var(--ct-color-impact-band)');
    if (opts.zero && s.lo < 0 && s.hi > 0) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${s.y(0)}" y2="${s.y(0)}" stroke="var(--ct-color-border-strong)"/>`;
    opts.series.forEach(se => {
      let d = '', pen = false;
      se.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + x(i) + ',' + s.y(v); pen = true; });
      g += `<path d="${d}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2.5}" ${se.dash ? 'stroke-dasharray="6 5"' : ''} stroke-linejoin="round"/>`;
      se.values.forEach((v, i) => { if (v != null && !se.dash) g += `<circle cx="${x(i)}" cy="${s.y(v)}" r="3" fill="${se.color}"><title>${opts.labels[i]}: ${fmt(v)}</title></circle>`; });
    });
    const step = Math.ceil(n / 12);
    opts.labels.forEach((l, i) => { if (i % step === 0 || i === n - 1) g += `<text x="${x(i)}" y="${h - 6}" text-anchor="middle">${l}</text>`; });
    if (opts.marker != null) { const mx = x(opts.marker); g += `<line x1="${mx}" x2="${mx}" y1="${P.t}" y2="${h - P.b}" stroke="var(--ct-color-brand-accent)" stroke-dasharray="3 3"/><text x="${mx + 4}" y="${P.t + 10}">launch</text>`; }
    return `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">${g}</svg>`;
  }
  function bars(opts) { // {labels, values, height}
    const h = opts.height || 200, n = opts.labels.length || 1;
    const s = scale([...opts.values, 0], h);
    const bw = (W - P.l - P.r) / n * 0.7;
    let g = '';
    for (let k = 0; k <= 4; k++) { const v = s.lo + (s.hi - s.lo) * k / 4, y = s.y(v); g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="var(--ct-color-border-subtle)"/><text x="${P.l - 6}" y="${y + 4}" text-anchor="end">${fmt(v)}</text>`; }
    opts.values.forEach((v, i) => {
      const cx = P.l + (W - P.l - P.r) * (i + 0.5) / n, y0 = s.y(0), y1 = s.y(v);
      g += `<rect x="${cx - bw / 2}" y="${Math.min(y0, y1)}" width="${bw}" height="${Math.max(1, Math.abs(y1 - y0))}" rx="3" fill="${v >= 0 ? 'var(--ct-color-status-success-solid)' : 'var(--ct-color-status-danger-solid)'}"><title>${opts.labels[i]}: ${fmt(v)}</title></rect>`;
      if (n <= 16 || i % Math.ceil(n / 16) === 0) g += `<text x="${cx}" y="${h - 6}" text-anchor="middle">${opts.labels[i]}</text>`;
    });
    return `<svg class="chart" viewBox="0 0 ${W} ${h}">${g}</svg>`;
  }
  function spark(values, color) {
    const w = 120, h = 32, f = values.filter(v => v != null);
    if (f.length < 2) return '';
    let lo = Math.min(...f), hi = Math.max(...f); if (lo === hi) { lo -= 1; hi += 1; }
    const pts = values.map((v, i) => v == null ? null : `${(i / (values.length - 1)) * w},${h - 3 - (h - 6) * (v - lo) / (hi - lo)}`).filter(Boolean).join(' ');
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${color || 'var(--ct-color-brand-primary)'}" stroke-width="2"/></svg>`;
  }
  function hbar(rows) { // [{label, value, color}]
    const mx = Math.max(...rows.map(r => Math.abs(r.value)), 1e-9);
    return `<div class="stack">${rows.map(r => `<div class="hrow"><span style="width:120px" class="sec">${r.label}</span><div class="grow bar" style="height:14px"><span style="width:${Math.abs(r.value) / mx * 100}%;background:${r.color}"></span></div><b class="num" style="width:70px;text-align:right">${r.text}</b></div>`).join('')}</div>`;
  }
  return { line, bars, spark, hbar, fmt };
})();
