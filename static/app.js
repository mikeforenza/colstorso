/* ColsTorso SPA core: state, API client, shell, router, shared widgets. Vanilla JS, no build step. */
const S = { user: null, meta: null, store: null, route: '', cache: {} };
const $ = sel => document.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v, d = 0) => v == null ? '—' : (v < 0 ? '-' : '') + '$' + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
const kfmt = v => v == null ? '—' : Math.abs(v) >= 1000 ? (v < 0 ? '-' : '') + '$' + (Math.abs(v) / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1) + 'k' : money(v);
const num = (v, d = 1) => v == null ? '—' : (+v).toLocaleString('en-US', { maximumFractionDigits: d });
const icon = (n, cls = '') => `<svg class="i ${cls}" aria-hidden="true"><use href="/design/icons/ct-icons.svg#i-${n}"/></svg>`;
const can = cap => S.meta && S.meta.perms.includes(cap);
const role = () => S.user && S.user.role;
const isStore = () => ['store_manager', 'associate'].includes(role());
const qs = o => { const p = Object.entries(o).filter(([, v]) => v != null && v !== ''); return p.length ? '?' + p.map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&') : ''; };

async function api(path, opts = {}) {
  const h = { 'X-User': S.user ? S.user.id : '' };
  let body = opts.body;
  if (body && !(body instanceof FormData)) { h['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
  const r = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers: h, body });
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) {
    const msg = (data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : ('Error ' + r.status);
    if (r.status === 401) { logout(); }
    toast(msg, true); throw new Error(msg);
  }
  return data;
}
const post = (p, b = {}) => api(p, { body: b, method: 'POST' });

function toast(msg, err) {
  const el = document.createElement('div'); el.className = 'toast' + (err ? ' err' : ''); el.innerHTML = `${icon(err ? 'triangle-alert' : 'check')}<span>${esc(msg)}</span>`;
  $('#toasts').appendChild(el); setTimeout(() => el.remove(), err ? 6000 : 3500);
}
function modal(title, html, buttons = []) {
  return new Promise(res => {
    const root = $('#modal-root');
    root.innerHTML = `<div class="modal-back"><div class="modal" role="dialog" aria-modal="true"><div class="hrow between"><h3 class="h3">${esc(title)}</h3>
      <button class="iconbtn" data-x>${icon('x')}</button></div><div class="stack">${html}</div>
      <div class="hrow" style="justify-content:flex-end">${buttons.map((b, i) => `<button class="btn ${b.primary ? 'btn-primary' : 'btn-secondary'}" data-b="${i}">${esc(b.label)}</button>`).join('')}</div></div></div>`;
    const close = v => { root.innerHTML = ''; res(v); };
    root.querySelector('[data-x]').onclick = () => close(null);
    root.querySelectorAll('[data-b]').forEach(el => el.onclick = async () => {
      const b = buttons[+el.dataset.b];
      if (b.action) { try { const v = await b.action(root.querySelector('.modal')); if (v === false) return; close(v ?? true); } catch (e) { /* toast shown */ } }
      else close(b.value ?? null);
    });
    const first = root.querySelector('input,select,textarea'); if (first) first.focus();
  });
}
const val = (root, sel) => { const el = root.querySelector(sel); return el ? el.value : null; };
const checked = (root, sel) => [...root.querySelectorAll(sel + ':checked')].map(e => e.value);

function md(s) { // minimal, safe markdown: paragraphs, **bold**, lists, images, links
  const lines = esc(s || '').split('\n'); let out = '', list = null;
  const inline = t => t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, '<img alt="$1" src="$2">').replace(/\[([^\]]+)\]\((https?:[^)\s]+|\/[^)\s]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\*([^*]+)\*/g, '<i>$1</i>');
  for (const l of lines) {
    const m = l.match(/^\s*(\d+\.|-|\*)\s+(.*)/);
    if (m) { const t = /\d/.test(m[1]) ? 'ol' : 'ul'; if (list !== t) { if (list) out += `</${list}>`; out += `<${t}>`; list = t; } out += `<li>${inline(m[2])}</li>`; continue; }
    if (list) { out += `</${list}>`; list = null; }
    if (l.trim()) out += `<p>${inline(l)}</p>`;
  }
  if (list) out += `</${list}>`;
  return `<div class="md">${out}</div>`;
}
const chipP = p => `<span class="chip p-${(p || 'should').toLowerCase()}">${p === 'Must' ? icon('flame') : p === 'Should' ? icon('arrow-up') : icon('minus')}${esc(p || 'Should')}</span>`;
const chipKind = k => `<span class="chip kind">${icon(k === 'alert' ? 'triangle-alert' : k === 'theme' ? 'sparkles' : 'chart-column')}${esc(k === 'alert' ? 'Alert' : k === 'theme' ? 'AI theme' : 'Opportunity')}</span>`;
const UI = { incoming: 'Suggested', prelaunch: 'Accepted', proposed: 'Accepted', live: 'In progress', done: 'Done', rejected: 'Not for us', snoozed: 'Snoozed', open: 'Open' };
const statusChip = s => `<span class="chip ${({ live: 's-info', incoming: 's-warning', rejected: 's-danger', proposed: 's-warning', prelaunch: 's-neutral', done: 's-success', snoozed: 's-neutral', open: 's-info' })[s] || 's-neutral'}">${esc(UI[s] || s)}</span>`;
const rangeTxt = imp => imp && imp.weeks_measured ? `likely ${kfmt(imp.low)} to ${kfmt(imp.high)}` : '';
const impactTxt = imp => !imp || !imp.weeks_measured ? `<span class="imp-neu">Measuring from next week</span>` : imp.status === 'grey' ? `<span class="imp-neu">${icon('minus', 'i-sm')} No clear change yet (${kfmt(imp.cumulative)}, ${rangeTxt(imp)})</span>` :
  `<span class="${imp.status === 'green' ? 'imp-pos' : 'imp-neg'}">${icon(imp.status === 'green' ? 'trending-up' : 'trending-down', 'i-sm')} ${imp.cumulative >= 0 ? '+' : ''}${kfmt(imp.cumulative)} so far <span class="muted">(${rangeTxt(imp)})</span></span>`;
const verdict = imp => !imp || !imp.weeks_measured ? '<span class="chip s-neutral">Too early</span>' : imp.status === 'green' ? `<span class="chip s-success">${icon('trending-up')}Worked</span>` : imp.status === 'red' ? `<span class="chip s-danger">${icon('trending-down')}Got worse</span>` : `<span class="chip s-neutral">${icon('minus')}No clear change</span>`;
function conf(z) { const n = Math.abs(z || 0) > 2.5 ? 3 : Math.abs(z || 0) > 1.5 ? 2 : 1; return `<span class="conf">${[1, 2, 3].map(i => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</span> ${['Low', 'Medium', 'High'][n - 1]}`; }
const storeOpts = (sel, all = true) => (all ? `<option value="">All my stores</option>` : '') + S.meta.stores.map(s => `<option value="${s.id}" ${+sel === s.id ? 'selected' : ''}>${esc(s.code)} · ${esc(s.name)}</option>`).join('');
const catName = id => (S.meta.categories.find(c => c.id === +id) || {}).name || '';

/* ---------- auth ---------- */
async function login(uid) {
  S.user = await post('/api/login', { user_id: uid });
  localStorage.setItem('ct_user', uid); S.store = null;
  await loadMeta(); location.hash = '#/home'; route();
}
function logout() { localStorage.removeItem('ct_user'); S.user = null; S.meta = null; location.hash = '#/login'; route(); }
async function loadMeta() { S.meta = await api('/api/meta'); S.user = S.meta.user; if (isStore()) S.store = S.user.store_id; }

/* ---------- shell ---------- */
function nav() {
  const r = role(), items = [
    ['home', 'sun', 'Today'], ['missions', 'target', 'Missions'], ['tasks', 'list-checks', 'Tasks'], ['walks', 'circle-check', 'Store walks'],
    ['business', 'layout-dashboard', 'My business'], ['pnl', 'chart-column', 'P&L explorer'],
    can('team') && ['team', 'users', 'Team'], can('visits') && ['visits', 'map-pin', 'Visits'],
    ['bp', 'lightbulb', 'Best practices'], ['comms', 'megaphone', 'Comms'],
    can('impact') && ['impact', 'chart-line', 'Impact'], can('impact') && !isStore() && ['pushback', 'message-square', 'Store feedback'], can('campaigns') && ['campaigns', 'flame', 'Campaigns'],
    (can('dc') || isStore() || r === 'district_manager') && ['dc', 'store', r === 'dc_manager' ? 'DC quality' : 'Load quality'],
    ['ask', 'sparkles', 'Ask ColsTorso'],
    can('data') && ['onboarding', 'badge-check', 'Get started'],
    (can('architect') || can('data') || can('users') || can('tasks_admin') || can('surveys_admin')) && ['architect', 'settings', 'Architect'],
  ].filter(Boolean);
  const cur = S.route.split('/')[0];
  return `<nav class="sidenav" aria-label="Main"><div class="brand"><img src="/design/logo.svg" alt="ColsTorso"></div>
    ${items.map(([k, i, l]) => `<a href="#/${k}" class="${cur === k || (cur === 'mission' && k === 'missions') || (cur === 'kpi' && k === 'business') || (cur === 'task' && k === 'tasks') || (cur === 'walk' && k === 'walks') || (cur === 'visit' && k === 'visits') ? 'active' : ''}">${icon(i)}<span>${l}</span></a>`).join('')}
    <div class="foot"><a href="#/notifications">${icon('bell')}<span>Notifications</span>${S.meta.unread ? `<span class="count">${S.meta.unread}</span>` : ''}</a>
    <a href="#/coaching">${icon('message-square')}<span>Coaching notes</span></a>
    <a href="#/login" onclick="logout();return false">${icon('user')}<span>Switch user</span></a></div></nav>`;
}
function topbar() {
  const u = S.user, init = u.name.split(' ').map(x => x[0]).join('').slice(0, 2);
  const scopeSel = S.meta.stores.length > 1 ? `<select id="storeSel" aria-label="Store filter" onchange="S.store=this.value||null;route()">${storeOpts(S.store)}</select>` : '';
  const st = S.meta.stores.length === 1 ? S.meta.stores[0] : null;
  return `<header class="topbar"><div class="ctx"><b>${st ? esc(st.code + ' · ' + st.name) : esc(u.name)}</b><span>${esc(S.meta.role_label)} · Week ${S.meta.week} (w/c ${esc(S.meta.week_start)}) · today ${esc(S.meta.today)}</span></div>
    ${scopeSel}<button class="iconbtn" title="Help" aria-label="Help" onclick="openHelp()">${icon('circle-help')}</button><button class="iconbtn" title="Toggle dark mode" aria-label="Toggle dark mode" onclick="toggleTheme()">${icon('sun')}</button><button class="iconbtn" title="Ask ColsTorso" onclick="openAsk()">${icon('sparkles')}</button>
    <a class="iconbtn" href="#/notifications" title="Notifications">${icon('bell')}${S.meta.unread ? `<span class="dot">${S.meta.unread}</span>` : ''}</a>
    <button class="avatar" title="${esc(u.name)} – switch user" onclick="logout()">${esc(init)}</button></header>
    ${freshStrip()}`;
}
const ageTxt = h => h < 1 ? 'just now' : h < 48 ? Math.round(h) + 'h ago' : Math.round(h / 24) + ' days ago';
function freshStrip() {
  const f = S.meta.freshness || [];
  return `<div class="fresh" role="status">${f.map(x => `<span class="src ${x.state === 'fresh' ? 'ok' : x.state}">${icon(x.state === 'fresh' ? 'circle-check' : x.state === 'aging' ? 'clock' : 'triangle-alert', 'i-sm')}
    ${esc(x.name)}: ${x.state === 'fresh' ? 'through ' + esc(x.data_through) : x.state === 'aging' ? 'ageing' : 'stale'} · loaded ${ageTxt(x.age_hours)} <span class="muted">(${x.cadence})</span></span>`).join('')}
    ${S.meta.public_demo ? `<span class="muted">${S.meta.tenant_kind === 'demo' ? 'Demo tenant · synthetic data' : 'Uploaded workspace on a public demo – don\'t upload confidential data'}</span><button class="btn btn-ghost" style="min-height:32px" onclick="resetDemo()">Reset demo data</button>` : ''}</div>`;
}
async function resetDemo() {
  const ok = await modal('Reset demo data?', '<p>This rebuilds the synthetic dataset (50 stores, 52 weeks) for everyone using this demo. Takes a few seconds.</p>', [{ label: 'Cancel' }, { label: 'Reset', primary: true, action: () => post('/api/admin/reset') }]);
  if (ok) { toast('Demo data reset'); await loadMeta(); location.hash = '#/home'; route(); }
}
function applyTheme() {
  const pref = localStorage.getItem('ct_theme');
  const dark = pref ? pref === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
}
function toggleTheme() { const cur = document.documentElement.getAttribute('data-theme'); localStorage.setItem('ct_theme', cur === 'dark' ? 'light' : 'dark'); applyTheme(); }
applyTheme(); window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (!localStorage.getItem('ct_theme')) applyTheme(); });
function shell(html) {
  $('#app').innerHTML = `<div class="shell">${nav()}<div class="main">${topbar()}<main class="content" id="content">${html}</main></div></div>`;
}
const setContent = html => { const c = $('#content'); if (c) c.innerHTML = html; };
const loading = () => `<div class="stack">${'<div class="skel" style="height:80px"></div>'.repeat(3)}</div>`;

/* ---------- router ---------- */
const Pages = {};
async function route() {
  const h = location.hash.replace(/^#\/?/, '') || 'home';
  S.route = h;
  if (!S.user) { const saved = localStorage.getItem('ct_user'); if (saved && h !== 'login') { try { S.user = { id: saved }; await loadMeta(); } catch (e) { S.user = null; } } }
  if (!S.user || h === 'login') return Pages.login();
  const [name, ...args] = h.split('/');
  const fn = Pages[name] || Pages.notfound;
  shell(loading());
  try { await fn(...args); } catch (e) { console.error(e); if (S.route === h) setContent(`<div class="empty">Couldn't load this page: ${esc(e.message)}</div>`); }
  if (S.route !== h && !S.rerouting) { S.rerouting = true; try { await route(); } finally { S.rerouting = false; } }   // a slower, older page finished last: redraw the current one
}
window.addEventListener('hashchange', route);
window.addEventListener('load', route);
async function refreshMeta() { S.meta = await api('/api/meta'); }

/* ---------- AI drawer ---------- */
function openAsk(prefill) {
  let d = $('#askDrawer');
  if (!d) {
    d = document.createElement('div'); d.id = 'askDrawer'; d.className = 'drawer';
    d.innerHTML = `<div class="hd">${icon('sparkles')}<b class="grow">Ask ColsTorso</b><button class="iconbtn" onclick="this.closest('.drawer').remove()">${icon('x')}</button></div>
      <div class="bd ai" id="askLog" style="border:0;border-radius:0"><div class="msg">Ask about your stores, missions, KPIs, waste, labor or what worked elsewhere. Answers are computed from your live data.</div>
      <div class="prompts">${['What should I focus on this week?', 'Which stores have the worst waste?', 'What worked for Fresh waste?', 'Why is labor over budget?', 'How much impact have missions delivered?'].map(p => `<button onclick="askSend(this.textContent)">${p}</button>`).join('')}</div></div>
      <form class="ft" onsubmit="askSend(this.q.value);this.q.value='';return false"><input name="q" class="grow" placeholder="Ask about your store…" autocomplete="off"><button class="btn btn-primary">${icon('send')}</button></form>`;
    document.body.appendChild(d);
  }
  if (prefill) askSend(prefill);
}
async function openHelp(q) {
  document.querySelectorAll('.drawer').forEach(d => d.remove());
  const d = document.createElement('div'); d.id = 'helpDrawer'; d.className = 'drawer';
  d.innerHTML = `<div class="hd">${icon('circle-help')}<b class="grow">Help & support</b><button class="iconbtn" aria-label="Close" onclick="this.closest('.drawer').remove()">${icon('x')}</button></div>
    <div class="bd stack" style="overflow:auto"><form onsubmit="helpAsk(this.q.value);return false" class="hrow"><input name="q" class="grow" placeholder="How do I…?" value="${esc(q || '')}" autocomplete="off"><button class="btn btn-primary">${icon('send')}</button></form>
    <div id="helpAns"></div><div id="helpList" class="stack">${loading()}</div></div>`;
  document.body.appendChild(d);
  const r = await api('/api/help'); helpRender(r.articles);
  if (q) helpAsk(q);
}
function helpRender(arts) {
  $('#helpList').innerHTML = arts.map(a => `<details class="card card-pad"><summary><b>${esc(a.title)}</b> <span class="muted s">· ${esc(a.section)}</span></summary><p>${esc(a.body)}</p><a href="${esc(a.link)}" onclick="this.closest('.drawer').remove()">Go there ${icon('chevron-right', 'i-sm')}</a></details>`).join('');
}
async function helpAsk(q) {
  if (!q || !q.trim()) return;
  const r = await post('/api/help/ask', { q });
  $('#helpAns').innerHTML = `<div class="ai"><div class="msg">${md(r.answer)}<div class="cite">${(r.sources || []).map(s => `<span>${esc(s)}</span>`).join('')}</div></div></div>`;
  helpRender(r.articles.length ? r.articles : (await api('/api/help')).articles);
}
async function askSend(q, logSel = '#askLog') {
  if (!q || !q.trim()) return;
  const log = $(logSel); log.insertAdjacentHTML('beforeend', `<div class="msg me">${esc(q)}</div>`);
  const r = await post('/api/ai/ask', { q });
  log.insertAdjacentHTML('beforeend', `<div class="msg">${md(r.answer)}${(r.sources || []).length ? `<div class="cite">${r.sources.map(s => `<span>${esc(s)}</span>`).join('')}</div>` : ''}${(r.articles || []).slice(0, 2).map(a => `<a href="${esc(a.link)}" onclick="document.querySelectorAll('.drawer').forEach(d=>d.remove())">${icon('info', 'i-sm')} ${esc(a.title)}</a>`).join(' · ')}${(r.links || []).map(l => `<a href="${esc(l.href)}">${esc(l.label)}</a>`).join(' · ')}</div>`);
  log.scrollTop = log.scrollHeight;
}

/* ---------- login ---------- */
Pages.login = async () => {
  const users = await fetch('/api/users').then(r => r.json());
  const pick = ['hq_admin', 'central_analyst', 'regional_manager', 'district_manager', 'store_manager', 'associate', 'dc_manager'];
  const labels = { hq_admin: 'HQ admin', central_analyst: 'Central analyst', regional_manager: 'Regional manager', district_manager: 'District manager', store_manager: 'Store manager', associate: 'Store associate', dc_manager: 'DC manager' };
  const featured = pick.map(r => users.find(u => u.role === r)).filter(Boolean);
  $('#app').innerHTML = `<div class="login"><img src="/design/logo.svg" alt="ColsTorso" style="height:48px">
    <div><h1 class="h1">Sign in to the demo tenant</h1><p class="lede">Pick a persona. Every role sees its own scope, inbox and permissions. Data is synthetic (50 stores, 52 weeks).</p></div>
    <div class="personas">${featured.map(u => `<button class="card persona" onclick="login(${u.id})"><span class="eyebrow">${labels[u.role]}</span><b>${esc(u.name)}</b><span class="muted">${esc(u.store_code || u.district || '')}</span></button>`).join('')}</div>
    <div class="card card-pad stack"><label class="f">Or any user<select id="anyUser">${users.map(u => `<option value="${u.id}">${esc(u.name)} – ${labels[u.role] || u.role} ${esc(u.store_code || u.district || '')}</option>`).join('')}</select></label>
    <button class="btn btn-primary" onclick="login($('#anyUser').value)">Sign in</button></div></div>`;
};
Pages.notfound = () => setContent(`<div class="empty">Page not found. <a href="#/home">Go to Today</a></div>`);
