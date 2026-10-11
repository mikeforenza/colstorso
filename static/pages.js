/* ColsTorso pages: Today, Missions, Mission detail */
function missionCard(m, i, n) {
  const p = (m.priority || 'Should').toLowerCase();
  const why = m.kind === 'alert' || m.kind === 'theme' ? esc(m.comment || m.title) :
    `${m.campaign_id ? 'Part of an HQ campaign. ' : ''}${m.cat_name ? `<b>${esc(m.cat_name)}</b>: ` : ''}${esc(m.kpi_label)} is behind similar stores by <b>${kfmt(m.baseline_gap)}/wk</b>.${m.comment ? ' ' + esc(m.comment) : ''}`;
  const pay = m.kind === 'opportunity' && (m.target_weekly || m.baseline_gap) > 0 ? '+' + kfmt(Math.max(m.target_weekly || m.baseline_gap || 0, 0)) + '/wk' : '—';
  return `<article class="card mission ${p}" id="mc${m.id}"><div class="meta">${chipP(m.priority)}${chipKind(m.kind)}${m.campaign_id ? `<span class="chip kind">${icon('megaphone')}HQ campaign</span>` : ''}
    ${S.meta.stores.length > 1 ? `<span class="chip kind">${esc(m.store_code)}</span>` : ''}<span class="rank">${i != null ? `${i + 1} of ${n}` : statusChip(m.status)}</span></div>
    <h3><a href="#/mission/${m.id}">${esc(m.title)}</a></h3>
    <div class="why"><span class="lbl">Why you're seeing this</span><span>${why}</span></div>
    <div class="facts"><div class="fact"><span class="k">If fixed</span><span class="v big imp-pos">${m.kind === 'opportunity' ? icon('trending-up', 'i-sm') : ''}${pay}</span></div>
    <div class="fact"><span class="k">Effort</span><span class="v">~${m.effort_min} min</span></div>
    <div class="fact"><span class="k">Confidence</span><span class="v">${m.z != null ? conf(m.z) : m.kind === 'alert' ? conf(3) : '—'}</span></div></div>
    ${['incoming', 'snoozed'].includes(m.status) ? `<div class="btn-row"><button class="btn btn-primary" onclick="quick(${m.id},'accept')">${icon('check')} Accept</button>
      <button class="btn btn-secondary" onclick="quick(${m.id},'snooze')">${icon('alarm-clock')} Snooze</button>
      <button class="iconbtn" aria-label="More" onclick="cardMore(${m.id})">${icon('ellipsis')}</button></div>` : ''}</article>`;
}
async function quick(id, action, reason) {
  const r = await post(`/api/missions/${id}/quick`, { action, reason });
  const msg = { accept: r.status === 'live' ? 'Accepted with the suggested plan – measuring vs similar stores from next week' : 'Accepted – sent for approval', snooze: 'Snoozed for a week', not_for_us: 'Marked "not for my store" – HQ will see why' }[action];
  toast(msg); route();
}
async function cardMore(id) {
  const v = await modal('More options', `<a class="btn btn-secondary btn-block" href="#/mission/${id}" onclick="$('#modal-root').innerHTML=''">${icon('target')} Open & edit the plan</a>
    <button class="btn btn-secondary btn-block" onclick="$('#modal-root').innerHTML='';explain(${id})">${icon('sparkles')} Why this mission?</button>
    <label class="f">Not for my store – why? (HQ sees this)<select id="nfr"><option>Not relevant to my store</option><option>Already fixed</option><option>Stock not delivered</option><option>Fixture or display missing</option><option>Not enough staff hours</option><option>Data looks wrong</option></select></label>`,
    [{ label: 'Close' }, { label: 'Not for my store', primary: true, action: m => val(m, '#nfr') }]);
  if (v) quick(id, 'not_for_us', v);
}
async function explain(id) {
  const r = await api('/api/ai/explain/' + id);
  modal('Why this mission?', md(r.text) + (r.llm ? '' : '<p class="muted">Explanation generated from the live data by the built-in rules engine.</p>'), [{ label: 'Close', primary: true }]);
}
async function rejectMission(id, after) {
  const ok = await modal('Snooze or reject', `<label class="f">Why not now? (feeds AI themes and the engine)<select id="rr"><option>Already fixing this</option><option>Short staffed this week</option>
    <option>Delivery or DC problem</option><option>Equipment broken, waiting on repair</option><option>Data looks wrong</option><option value="other">Other…</option></select></label>
    <input id="rro" placeholder="Other reason"><label class="f">Bring it back in<select id="rs"><option value="1">1 week</option><option value="2">2 weeks</option><option value="4" selected>4 weeks</option><option value="8">8 weeks</option></select></label>`,
    [{ label: 'Cancel' }, { label: 'Reject', primary: true, action: async m => { const r = val(m, '#rr') === 'other' ? val(m, '#rro') : val(m, '#rr'); await post(`/api/missions/${id}/reject`, { reason: r, snooze_weeks: +val(m, '#rs') }); } }]);
  if (ok) { toast('Mission rejected – it will not come back for the snooze period'); after ? after() : route(); }
}

Pages.home = async () => {
  const [h, b] = await Promise.all([api('/api/home' + qs({ store: S.store })), api('/api/business' + qs({ store: S.store }))]);
  const inbox = h.inbox, top = inbox.slice(0, S.meta.settings.inbox_size || 3), rest = inbox.slice(top.length);
  const t = b.tiles, pick = k => t.find(x => x.kpi === k), last = x => x.trend[x.trend.length - 1].value;
  const mini = ['total_sales', 'waste', 'labor', 'csat'].map(pick).map(x => `<a class="kpi" href="#/kpi/${x.kpi}" style="text-decoration:none;color:inherit"><span class="k">${esc(x.label)}</span>
     <span class="v num" style="font-size:var(--ct-font-size-150)">${x.unit === '$' ? kfmt(last(x)) : num(last(x)) + (x.unit === '%' ? '%' : '')}</span>
     <span class="d muted">${x.rank ? `#${x.rank} of ${x.of}` : `${x.below_avg} of ${x.stores} below avg`}</span></a>`).join('');
  const tasks = ['Must', 'Should', 'Could'].map(k => (h.tasks[k] || []).slice(0, 4).map(t => `<a class="row" href="#/task/${t.id}" style="text-decoration:none;color:inherit">${chipP(k)}<div class="grow"><div class="t">${esc(t.title)}</div><div class="s">${esc(t.store_code)} · due ${esc(t.due)}</div></div>${icon('chevron-right')}</a>`).join('')).join('');
  setContent(`<div class="split"><div class="stack-lg">
    <div class="hello"><h1 class="h1">${esc(h.briefing.split('.')[0])}</h1><p class="lede">${esc(h.briefing.split('.').slice(1).join('.'))}</p></div>
    ${h.announcements.map(a => `<div class="notice hrow">${icon('megaphone')}<div class="grow"><b>${esc(a.title)}</b> – ${esc(a.body)}</div><button class="btn btn-secondary" onclick="post('/api/comms/${a.id}/read').then(route)">${a.require_ack ? 'Acknowledge' : 'Dismiss'}</button></div>`).join('')}
    <section class="stack"><div class="section-h"><h2 class="h3">Your missions this week</h2><a href="#/missions">Mission control</a></div>
      ${top.length ? top.map((m, i) => missionCard(m, i, top.length)).join('') : '<div class="card empty">No new missions. Nice – check your live missions below.</div>'}
      ${rest.length ? `<a class="card backlog row" href="#/missions">${icon('circle-help')}<div class="grow"><b>${rest.length} more ideas can wait</b><div class="s">Lower value or lower confidence. Not urgent.</div></div>${icon('chevron-right')}</a>` : ''}</section>
    <section class="card"><div class="section-h card-pad" style="margin:0;padding-bottom:0"><h2 class="h3">Working on it</h2><a href="#/missions">See all</a></div>
      <div class="list">${h.live.length ? h.live.slice(0, 6).map(m => `<a class="row" href="#/mission/${m.id}" style="text-decoration:none;color:inherit"><span class="dotst ${m.impact.status}"></span><div class="grow"><div class="t">${esc(m.title)}</div>
      <div class="s">${esc(m.store_code)} · weeks ${m.start_week}–${m.end_week} · vs control stores</div></div><b>${impactTxt(m.impact)}</b></a>`).join('') : '<div class="empty">Nothing live yet. Accept a mission to start measuring.</div>'}</div></section>
    <section class="card"><div class="section-h card-pad" style="margin:0;padding-bottom:0"><h2 class="h3">Tasks</h2><a href="#/tasks">All tasks</a></div><div class="list">${tasks || '<div class="empty">No open tasks.</div>'}</div></section>
  </div><aside class="stack-lg"><div class="card card-pad stack"><h3 class="h4">${S.meta.stores.length === 1 ? esc(S.meta.stores[0].name) : 'Your stores'} this week</h3><div class="grid2">${mini}</div></div>
    <div class="ai"><div class="hd">${icon('sparkles')} Ask ColsTorso</div><div id="homeAsk" class="stack"></div>
    <div class="prompts"><button onclick="askSend(this.textContent,'#homeAsk')">What should I focus on this week?</button><button onclick="askSend(this.textContent,'#homeAsk')">Why is labor over budget?</button></div>
    <form class="hrow" onsubmit="askSend(this.q.value,'#homeAsk');this.q.value='';return false"><input name="q" class="grow" placeholder="Ask about your store…"><button class="btn btn-primary">${icon('send')}</button></form></div>
    <div class="card"><div class="card-pad" style="padding-bottom:0"><h3 class="h4">Notifications</h3></div><div class="list">${h.notifications.slice(0, 6).map(n => `<a class="row" href="${esc(n.link || '#/home')}" style="text-decoration:none;color:inherit">${icon('bell', 'i-sm')}<div class="grow s">${esc(n.text)}</div></a>`).join('') || '<div class="empty">Nothing new.</div>'}</div></div>
  </aside></div>`);
};

Pages.missions = async () => {
  const all = await api('/api/missions' + qs({ store: S.store }));
  const col = (title, list, empty) => `<div class="col"><h4>${title}<span class="pill-num">${list.length}</span></h4>${list.slice(0, 40).map(m => `<a class="card tile" href="#/mission/${m.id}">
    <div class="hrow">${chipP(m.priority)}${statusChip(m.status)}${m.status === 'proposed' ? '<span class="chip s-warning">Awaiting approval</span>' : ''}</div><span class="t">${esc(m.title)}</span>
    <span class="s">${esc(m.store_code)} · ${esc(m.kpi_label)}${m.impact ? ' · ' + impactTxt(m.impact) : m.kind === 'opportunity' ? ' · ' + kfmt(m.baseline_gap) + '/wk' : ''}</span></a>`).join('') || `<div class="empty">${empty}</div>`}</div>`;
  const by = s => all.filter(m => s.includes(m.status));
  setContent(`<div class="pagehead"><div><h1 class="h1">Missions</h1><p class="lede">Suggested → Accepted → In progress (measured against similar stores) → Done. "Not for us" goes back to HQ with your reason.</p></div>
    <div class="hrow"><button class="btn btn-secondary" onclick="writeMission()">${icon('plus')} Write a mission</button></div></div>
    <div class="cols4">${col('Suggested', by(['incoming', 'snoozed']), 'Nothing suggested')}${col('Accepted', by(['prelaunch', 'proposed']), 'Nothing waiting to start')}${col('In progress', by(['live']), 'Nothing in progress')}${col('Done · Not for us', by(['done', 'rejected']), 'Empty')}</div>`);
};
async function writeMission(preset = {}) {
  const kpis = Object.entries(S.meta.kpis).filter(([k]) => !['equipment', 'dc_quality'].includes(k));
  const sub = S.meta.categories.filter(c => c.parent_id);
  const ok = await modal(isStore() ? 'Write your own mission' : 'Send a mission', `<label class="f">Store<select id="ws">${storeOpts(preset.store_id || S.store, false)}</select></label>
    <label class="f">Title<input id="wt" value="${esc(preset.title || '')}" placeholder="e.g. Fix the Dog Food bay after the reset"></label>
    <div class="grid2"><label class="f">KPI<select id="wk">${kpis.map(([k, v]) => `<option value="${k}" ${preset.kpi === k ? 'selected' : ''}>${esc(v.label)}</option>`).join('')}</select></label>
    <label class="f">Category (for sales/waste)<select id="wc"><option value="">—</option>${S.meta.categories.map(c => `<option value="${c.id}" ${+preset.cat_id === c.id ? 'selected' : ''}>${c.parent_id ? '— ' : ''}${esc(c.name)}</option>`).join('')}</select></label></div>
    ${!isStore() ? `<label class="f">Send to<select id="wo"><option value="store_manager">Store manager</option><option value="district_manager">District manager</option></select></label>` : ''}
    <label class="f">Comment / context<textarea id="wm">${esc(preset.comment || '')}</textarea></label><p class="muted">The real gap vs peers is computed now and used as the baseline.</p>`,
    [{ label: 'Cancel' }, { label: isStore() ? 'Create draft' : 'Send', primary: true, action: async m => { if (!val(m, '#wt')) { toast('Add a title', true); return false; }
      return post('/api/missions/send', { store_id: val(m, '#ws'), title: val(m, '#wt'), kpi: val(m, '#wk'), cat_id: val(m, '#wc') || null, owner_role: val(m, '#wo') || 'store_manager', comment: val(m, '#wm') }); } }]);
  if (ok) { toast(isStore() ? 'Draft created' : 'Mission sent to the manager\'s inbox'); location.hash = '#/mission/' + ok.id; }
}

const MS = {};
Pages.mission = async (id, win = '1') => {
  const m = await api(`/api/missions/${id}?window=${win}`); MS.m = m; MS.tasks = MS.tasks && MS.tasks.id === m.id ? MS.tasks : { id: m.id, list: [] };
  const sr = m.series, labels = sr.map(x => 'W' + x.week);
  const isGap = !!m.current, unit = (S.meta.kpis[m.kpi] || {}).unit;
  const better = (S.meta.kpis[m.kpi] || {}).better;
  const chart = sr.length ? Charts.line({ labels, series: [{ name: 'Your store', values: sr.map(x => x.actual), color: 'var(--ct-color-impact-store-line)' },
      ...(isGap ? [{ name: 'Peer expected', values: sr.map(x => x.expected), color: 'var(--ct-color-impact-control-line)', dash: true }] : []),
      ...(m.kpi === 'sales' ? [{ name: 'Last year', values: sr.map(x => x.ly), color: 'var(--ct-color-chart-3)', dash: true, width: 1.5 }] : [])],
    band: m.kpi === 'sales' ? null : sr.map(x => x.quart ? [x.quart[1], x.quart[3]] : null),
    marker: m.start_week ? sr.findIndex(x => x.week === m.start_week) : null }) : '<div class="empty">No time series for this mission type.</div>';
  const why = isGap ? `<div class="hrow"><span class="sec" style="width:120px">Your store</span><b class="num">${unit === '$' ? money(m.current.actual) : num(m.current.actual, 2)}</b></div>
     <div class="hrow"><span class="sec" style="width:120px">Peer expected</span><b class="num">${unit === '$' ? money(m.current.expected) : num(m.current.expected, 2)}</b></div>
     <div class="hrow"><span class="sec" style="width:120px">Gap / week</span><b class="num ${m.current.gap > 0 ? 'imp-neg' : 'imp-pos'}">${money(m.current.gap)}</b><span class="muted">· ${num(m.current.z, 1)}σ · ${conf(m.current.z)}</span></div>
     <p class="muted">${icon('info', 'i-sm')} Compared with <a href="#" onclick="showPeers();return false">${m.peers.length} similar stores</a> (${esc(m.scaler || '')}). ${better === 'lower' ? 'Lower is better.' : 'Higher is better.'}</p>` : `<p>${esc(m.comment || '')}</p>`;
  const heat = m.heatmap.rows.length ? `<table class="tbl heat"><thead><tr><th>${m.kpi === 'sales' ? 'Sibling categories' : 'Store KPIs'}</th>${m.heatmap.weeks.map(w => `<th class="r">W${w}</th>`).join('')}</tr></thead><tbody>
    ${m.heatmap.rows.map(r => { const mx = Math.max(1, ...m.heatmap.rows.flatMap(x => x.cells.map(Math.abs)));
      return `<tr><td>${esc(r.label)}</td>${r.cells.map((v, i) => `<td class="c" title="actual ${r.actual[i]}" style="background:color-mix(in srgb, ${v > 0 ? 'var(--ct-color-status-danger-solid)' : 'var(--ct-color-status-success-solid)'} ${Math.min(60, Math.abs(v) / mx * 60)}%, transparent)">${Charts.fmt(v)}</td>`).join('')}</tr>`; }).join('')}</tbody></table>` : '';
  const editable = ['incoming', 'prelaunch', 'rejected', 'snoozed'].includes(m.status);
  const bp = m.best_practices[0];
  const plan = editable ? `<div class="card card-pad stack" id="plan"><h3 class="h3">Your action plan</h3>
    <div class="stack"><b>1 · What's likely causing it?</b>${m.causes.map(c => `<label class="hrow"><input type="checkbox" name="rc" value="${esc(c)}" ${m.root_causes.includes(c) ? 'checked' : ''}> ${esc(c)}</label>`).join('')}</div>
    <label class="f">2 · Action type<select id="pa">${Object.keys(S.meta.actions).map(a => `<option ${m.action_type === a ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select></label>
    <label class="f">What exactly will you do?<textarea id="pd" placeholder="${esc(Object.values(S.meta.actions)[0])}">${esc(m.action || '')}</textarea></label>
    <div class="grid2"><label class="f">Target ($/week)<input id="pt" type="number" value="${Math.round(Math.max(m.target_weekly || m.baseline_gap || 0, 0))}"></label>
    <label class="f">Measure for<select id="pw">${[2, 4, 6, 8].map(w => `<option value="${w}" ${(m.duration || S.meta.settings.mission_duration) == w ? 'selected' : ''}>${w} weeks</option>`).join('')}</select></label></div>
    <div class="stack"><b>3 · Tasks we'll create</b><div id="ptl">${m.tasks.map(t => `<div class="row" style="padding:6px 0">${icon('check', 'i-sm')}<span class="grow">${esc(t.title)}</span><span class="muted">${esc(t.assignee || '')} ${esc(t.due || '')}</span></div>`).join('')}</div>
      <div class="hrow"><input id="ntt" class="grow" placeholder="New task"><select id="nta"><option value="">Me</option>${m.store_users.map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select><input id="ntd" type="date"><button class="btn btn-secondary" onclick="addPlanTask()">${icon('plus')}</button></div></div>
    <p class="muted">${icon('shield-check', 'i-sm')} We'll measure the result against ${m.peers.length || 'similar'} stores not running this mission. ${isStore() && S.meta.settings.require_approval !== false ? 'Your district manager will review the plan.' : ''}</p>
    <div id="prefill"></div><div class="hrow" style="justify-content:flex-end">${m.status !== 'prelaunch' ? `<button class="btn btn-secondary" onclick="quick(${m.id},'snooze')">${icon('alarm-clock')} Snooze</button><button class="btn btn-secondary" onclick="cardMore(${m.id})">Not for my store…</button>` : ''}<button class="btn btn-secondary" onclick="savePlan('draft')">Save draft</button><button class="btn btn-primary btn-lg" onclick="savePlan('accept')">${icon('check')} Accept & start</button></div></div>` : '';
  const iw = m.impact_weeks, I = m.impact || {};
  const ichart = iw.length ? Charts.line({ labels: ['Start', ...iw.map(x => 'W' + x.week)], zero: true,
      series: [{ values: [0, ...iw.map((x, i) => iw.slice(0, i + 1).reduce((a, r) => a + r.improvement, 0))], color: 'var(--ct-color-impact-store-line)' },
               { values: [0, ...iw.map((x, i) => iw.slice(0, i + 1).reduce((a, r) => a + r.control_improvement, 0))], color: 'var(--ct-color-impact-control-line)', dash: true }],
      band: (() => { const half = (I.high - I.low) / 2 || 0, n = I.weeks_measured || 1; return [[0, 0], ...iw.map((x, i) => { const v = iw.slice(0, i + 1).reduce((a, r) => a + r.improvement, 0), h = half * Math.min(i + 1, n) / n; return [v - h, v + h]; })]; })() }) : '';
  const live = ['live', 'done'].includes(m.status) ? `<div class="card card-pad stack"><div class="hrow">${verdict(I)}<span class="chip kind">${m.status === 'done' ? 'Completed' : 'In progress'} · weeks ${m.start_week}–${m.end_week}</span></div>
    <div class="grid3"><div class="card kpi"><span class="k">Extra per week from this</span><span class="v ${I.weekly >= 0 ? 'imp-pos' : 'imp-neg'}" style="font-size:var(--ct-font-size-150)">${I.weeks_measured ? (I.weekly >= 0 ? '+' : '') + kfmt(I.weekly) + '/wk' : '—'}</span><span class="s muted">${I.weeks_measured ? `likely range ${kfmt(I.weekly_low)} to ${kfmt(I.weekly_high)}` : 'first result after next data load'}</span></div>
      <div class="card kpi"><span class="k">Over ${I.weeks_measured || 0} week(s)</span><span class="v" style="font-size:var(--ct-font-size-150)">${I.weeks_measured ? (I.cumulative >= 0 ? '+' : '') + kfmt(I.cumulative) : '—'}</span><span class="s muted">after removing what similar stores did anyway</span></div>
      <div class="card kpi"><span class="k">How sure are we</span><span class="v" style="font-size:var(--ct-font-size-150)">${esc(I.confidence || '—')}</span><span class="s muted">90% range from ${I.n_controls} comparison stores</span></div></div>
    ${ichart ? ichart + `<div class="legend"><span><i style="background:var(--ct-color-impact-store-line)"></i>Your store (gap closed, cumulative $)</span><span><i style="background:var(--ct-color-impact-control-line)"></i>${I.n_controls} comparison stores</span><span><i style="background:var(--ct-color-impact-band);height:10px"></i>Likely range</span></div>` : '<p class="muted">First measurement arrives with next week\'s data.</p>'}
    <div class="why"><span><b>In plain words:</b> we fixed the comparison group of ${I.n_controls} similar stores ${m.accepted_at ? 'when you accepted (' + esc(m.accepted_at.slice(0, 10)) + ')' : 'at launch'}. Each week we count how much your gap closed, minus how much theirs moved on its own (seasonality, weather, promotions). The likely range shows how much stores move with no mission at all.</span></div>
    <div class="stack"><b>Action</b><p>${esc(m.action_type || '')}: ${esc(m.action || '')}</p></div>
    <div class="stack"><b>Tasks</b>${m.tasks.map(t => `<div class="row" style="padding:4px 0"><button class="check" aria-checked="${!!t.done}" onclick="post('/api/mission_tasks/${t.id}/toggle').then(route)"><span>${t.done ? icon('check', 'i-sm') : ''}</span></button><span class="grow">${esc(t.title)}</span><span class="muted">${esc(t.assignee || '')} ${esc(t.due || '')}</span></div>`).join('') || '<span class="muted">No tasks.</span>'}
    <div class="hrow"><input id="ntt" class="grow" placeholder="Add a task"><select id="nta"><option value="">Me</option>${m.store_users.map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select><input id="ntd" type="date"><button class="btn btn-secondary" onclick="addLiveTask(${m.id})">${icon('plus')}</button></div></div>
    <div class="hrow"><button class="btn btn-primary" onclick="shareBP(${m.id})">${icon('lightbulb')} Share as best practice</button><button class="btn btn-secondary" onclick="post('/api/missions/${m.id}/kudos').then(()=>{toast('Thanks sent to the team');route()})">${icon('thumbs-up')} Thank the team (${m.kudos})</button>
    <button class="btn btn-ghost" onclick="post('/api/missions/${m.id}/followup').then(r=>{toast('Follow-up created');location.hash='#/mission/'+r.id})">Start a follow-up</button></div></div>` : '';
  const approve = m.can_approve ? `<div class="card card-pad stack" style="border-color:var(--ct-color-status-warning-border)"><h3 class="h3">Review this plan</h3><p><b>${esc(m.action_type || '')}</b>: ${esc(m.action || '')}</p>
    <p class="muted">Root causes: ${esc(m.root_causes.join(', ') || '—')} · Target ${money(m.target_weekly)}/wk</p><textarea id="apc" placeholder="Comment for the store manager"></textarea>
    <div class="hrow"><button class="btn btn-secondary" onclick="approveM('changes')">Request changes</button><button class="btn btn-primary" onclick="approveM('approve')">${icon('check')} Approve & launch</button></div></div>` :
    m.status === 'proposed' ? `<div class="notice">Submitted – waiting for your district manager to approve. ${esc(m.action || '')}</div>` : '';
  setContent(`<div class="stack-lg"><div><a href="#/missions" class="muted">${icon('chevron-right')} Mission control</a>
    <div class="hrow" style="margin-top:8px">${chipP(m.priority)}${chipKind(m.kind)}${statusChip(m.label)}<span class="chip kind">${icon('store')}${esc(m.store_code)} ${esc(m.store_name)}</span></div>
    <h1 class="h1" style="margin-top:8px">${esc(m.title)}</h1></div>
    <div class="grid4"><div class="card kpi"><span class="k">Expected payoff</span><span class="v imp-pos" style="font-size:var(--ct-font-size-150)">${m.kind === 'opportunity' ? '+' + kfmt(Math.max(m.target_weekly || m.baseline_gap, 0)) + '/wk' : '—'}</span></div>
    <div class="card kpi"><span class="k">Confidence</span><span class="v" style="font-size:var(--ct-font-size-125)">${m.current ? conf(m.current.z) : '—'}</span></div>
    <div class="card kpi"><span class="k">Measured over</span><span class="v" style="font-size:var(--ct-font-size-150)">${m.duration || S.meta.settings.mission_duration} weeks</span></div>
    <div class="card kpi"><span class="k">Owner</span><span class="v" style="font-size:var(--ct-font-size-125)">${esc(m.owner_name || '—')}</span></div></div>
    ${approve}
    <div class="split-even"><div class="stack-lg"><div class="card card-pad stack"><h3 class="h3">Why you're seeing this</h3>${why}${chart}
      <div class="legend"><span><i style="background:var(--ct-color-impact-store-line)"></i>Your store</span>${isGap ? '<span><i style="background:var(--ct-color-impact-control-line)"></i>Peer expected</span>' : ''}${m.kpi !== 'sales' && isGap ? '<span><i style="background:var(--ct-color-impact-band);height:10px"></i>Peer middle 50%</span>' : ''}${m.kpi === 'sales' ? '<span><i style="background:var(--ct-color-chart-3)"></i>Last year</span>' : ''}</div></div>
      ${heat ? `<div class="card card-pad stack"><div class="hrow between"><h3 class="h3">Insights explorer</h3><div class="seg"><button aria-pressed="${win === '1'}" onclick="location.hash='#/mission/${m.id}/1'">1 week</button><button aria-pressed="${win === '4'}" onclick="location.hash='#/mission/${m.id}/4'">4-week avg</button></div></div>
        <p class="muted">Gap vs peers in $/week (red = behind peers). Look for substitution between siblings before acting.</p><div style="overflow:auto">${heat}</div></div>` : ''}
      <div class="ai"><div class="hd">${icon('sparkles')} Explain this mission</div><div id="mx" class="muted">Loading explanation…</div></div></div>
    <div class="stack-lg">${bp && editable ? `<div class="card card-pad stack" style="background:var(--ct-color-surface-accent-subtle)"><b>${icon('lightbulb')} What worked: ${esc(bp.title)}</b><p>"${esc(bp.body)}"</p><span class="imp-pos">+${money(bp.impact_value)} measured vs control</span><button class="btn btn-secondary" onclick="useBP()">${icon('plus')} Use this plan</button></div>` : ''}
      ${plan}${live}
      <div class="card card-pad stack"><h3 class="h3">Comments</h3>${m.comments.map(c => `<div><b>${esc(c.author)}</b> <span class="muted">${esc(c.ts.slice(0, 16))}</span><p>${esc(c.text)}</p></div>`).join('') || '<span class="muted">No comments yet.</span>'}
        <form class="hrow" onsubmit="post('/api/missions/${m.id}/comment',{text:this.t.value}).then(route);return false"><input name="t" class="grow" placeholder="Write a comment"><button class="btn btn-secondary">${icon('send')}</button></form></div>
      <div class="card card-pad stack"><h3 class="h4">Activity</h3>${m.activity.map(a => `<div class="s muted">${esc(a.ts.slice(0, 16))} · ${esc(a.who || 'System')} ${esc(a.action)} ${esc(a.detail || '')}</div>`).join('') || '<span class="muted">—</span>'}</div></div></div></div>`);
  api('/api/ai/explain/' + m.id).then(r => { const el = $('#mx'); if (el) el.innerHTML = md(r.text) + `<div class="cite">${(r.sources || []).map(x => `<span>${esc(x)}</span>`).join('')}</div>`; });
  if (editable && !m.action) api(`/api/missions/${m.id}/plan`).then(p => {
    if (!$('#pa')) return;
    document.querySelectorAll('input[name=rc]').forEach(cb => cb.checked = p.root_causes.includes(cb.value));
    $('#pa').value = p.action_type; $('#pd').value = p.action; $('#pt').value = p.target_weekly;
    MS.tasks.list = p.tasks.slice();
    $('#ptl').insertAdjacentHTML('beforeend', p.tasks.map(t => `<div class="row" style="padding:6px 0">${icon('plus', 'i-sm')}<span class="grow">${esc(t.title)}</span><span class="muted">You · ${esc(t.due)}</span></div>`).join(''));
    $('#prefill').innerHTML = `<p class="notice">${icon('sparkles', 'i-sm')} We've filled this in from ${esc(p.source)}. Change anything you like.</p>`;
  });
}
function showPeers() { modal('Peer group', `<p>${esc(MS.m.scaler || '')}</p><table class="tbl"><tbody>${MS.m.peers.map(p => `<tr><td>${esc(p.code)}</td><td>${esc(p.name)}</td></tr>`).join('')}</tbody></table>`, [{ label: 'Close', primary: true }]); }
function useBP() { const b = MS.m.best_practices[0]; $('#pa').value = b.action_type; $('#pd').value = b.body; toast('Plan pre-filled from best practice'); }
function planBody() {
  return { root_causes: checked(document, 'input[name=rc]'), action_type: $('#pa').value, action: $('#pd').value, target_weekly: +$('#pt').value, duration: +$('#pw').value, tasks: MS.tasks.list };
}
function addPlanTask() {
  const t = $('#ntt').value.trim(); if (!t) return toast('Type a task first', true);
  const a = $('#nta'); MS.tasks.list.push({ title: t, assignee_id: a.value ? +a.value : S.user.id, due: $('#ntd').value || null });
  $('#ptl').insertAdjacentHTML('beforeend', `<div class="row" style="padding:6px 0">${icon('plus', 'i-sm')}<span class="grow">${esc(t)}</span><span class="muted">${esc(a.selectedOptions[0].text)} ${esc($('#ntd').value)} (on save)</span></div>`); $('#ntt').value = '';
}
async function addLiveTask(id) { const t = $('#ntt').value.trim(); if (!t) return toast('Type a task first', true); await post(`/api/missions/${id}/tasks`, { title: t, assignee_id: $('#nta').value || S.user.id, due: $('#ntd').value || null }); route(); }
async function savePlan(kind) {
  const b = planBody();
  if (kind === 'accept') { const r = await post(`/api/missions/${MS.m.id}/accept`, b); toast(r.status === 'live' ? 'Mission launched – measuring from next week' : 'Plan sent to your district manager'); }
  else { await post(`/api/missions/${MS.m.id}/draft`, b); toast('Draft saved'); }
  MS.tasks.list = []; route();
}
async function approveM(d) { await post(`/api/missions/${MS.m.id}/approve`, { decision: d, comment: $('#apc').value }); toast(d === 'approve' ? 'Approved – mission is live' : 'Sent back for changes'); route(); }
async function shareBP(id) {
  const ok = await modal('Share as best practice', `<label class="f">Title<input id="bt" value="${esc((MS.m.action_type || '') + ': ' + MS.m.title)}"></label><label class="f">What did you do?<textarea id="bb">${esc(MS.m.action || '')}</textarea></label>`,
    [{ label: 'Cancel' }, { label: 'Share', primary: true, action: m => post(`/api/missions/${id}/share`, { title: val(m, '#bt'), body: val(m, '#bb') }) }]);
  if (ok) toast('Shared to the best-practice library');
}

/* ---------- Tasks ---------- */
Pages.tasks = async (tab = 'mine') => {
  const tabs = [['mine', 'My work'], ['done', 'Completed'], (can('tasks_admin') || ['district_manager', 'regional_manager', 'store_manager'].includes(role())) && ['send', 'Send a task'], ['analytics', 'Analytics']].filter(Boolean);
  let body = '';
  if (tab === 'mine' || tab === 'done') {
    const list = await api('/api/tasks' + qs({ status: tab === 'done' ? 'done' : 'open', store: S.store }));
    const grp = tab === 'done' ? { Done: list } : { Must: [], Should: [], Could: [] };
    if (tab !== 'done') list.forEach(t => grp[t.bucket].push(t));
    body = Object.entries(grp).map(([k, l]) => `<section class="card"><div class="card-pad hrow between" style="padding-bottom:0"><h3 class="h4">${k === 'Done' ? 'Completed' : chipP(k)}</h3><span class="pill-num">${l.length}</span></div><div class="list">
      ${l.slice(0, 80).map(t => `<a class="row" href="#/task/${t.id}" style="text-decoration:none;color:inherit"><div class="grow"><div class="t">${esc(t.title)}</div><div class="s">${esc(t.store_code)} · ${esc(t.assignee || t.assignee_role)} · due ${esc(t.due)} · ${esc(t.source)}${t.escalated ? ' · <b class="imp-neg">escalated</b>' : ''}</div></div>${statusChip(t.status)}</a>`).join('') || '<div class="empty">Nothing here.</div>'}</div></section>`).join('');
  } else if (tab === 'send') {
    const tpls = await api('/api/task_templates');
    body = `<div class="card card-pad stack" id="sendTask"><h3 class="h3">Send a task to stores</h3>
      <label class="f">Template<select id="stt"><option value="">— Ad hoc task —</option>${tpls.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('')}</select></label>
      <label class="f">Title (ad hoc or override)<input id="stl"></label><label class="f">Instructions (markdown, ad hoc)<textarea id="stb"></textarea></label>
      <div class="grid3"><label class="f">Formats${['Superstore', 'Standard', 'Express'].map(f => `<label class="hrow"><input type="checkbox" name="sf" value="${f}">${f}</label>`).join('')}</label>
      <label class="f">Tags${S.meta.all_tags.map(t => `<label class="hrow"><input type="checkbox" name="sg" value="${esc(t)}">${esc(t)}</label>`).join('')}</label>
      <label class="f">Stores (blank = all in scope)<select id="sts" multiple size="8">${storeOpts(null, false)}</select></label></div>
      <div class="grid3"><label class="f">Due in (days)<input id="std" type="number" value="3"></label><label class="f">Est. minutes (ad hoc)<input id="ste" type="number" value="15"></label>
      <label class="hrow" style="align-self:end"><input type="checkbox" id="sti"> Ignore store capacity (urgent)</label></div>
      <button class="btn btn-primary" onclick="sendTask()">${icon('send')} Send task</button><div id="stres"></div></div>`;
  } else {
    const a = await api('/api/tasks/analytics');
    body = `<div class="split-even"><div class="card card-pad stack"><h3 class="h3">By rule / source</h3><table class="tbl"><thead><tr><th>Rule</th><th class="r">Sent</th><th class="r">Done</th><th class="r">Overdue</th><th class="r">Escalated</th></tr></thead>
      <tbody>${a.by_rule.map(r => `<tr><td>${esc(r.rule)}</td><td class="r">${r.n}</td><td class="r">${r.done}</td><td class="r">${r.overdue}</td><td class="r">${r.escalated}</td></tr>`).join('')}</tbody></table>
      <h3 class="h3">Bottleneck stores</h3><table class="tbl"><tbody>${a.bottlenecks.map(r => `<tr><td>${esc(r.code)}</td><td class="r">${r.n} tasks</td><td class="r">${r.overdue} overdue</td></tr>`).join('')}</tbody></table></div>
      <div class="card card-pad stack"><h3 class="h3">Store capacity this week</h3><p class="muted">Estimated minutes of open work vs store capacity. Protected stores (≥100%) are skipped by non-urgent sends.</p>
      ${a.capacity.slice(0, 30).map(c => `<div class="hrow"><span style="width:60px">${esc(c.code)}</span><div class="grow capbar"><span class="${c.pct >= 100 ? 'over' : c.pct >= 80 ? 'warn' : ''}" style="width:${Math.min(100, c.pct)}%"></span></div><span class="num" style="width:48px;text-align:right">${c.pct}%</span></div>`).join('')}
      <button class="btn btn-secondary" onclick="post('/api/agent/run').then(r=>{toast('AI agent completed '+r.completed+' task(s)');route()})">${icon('sparkles')} Run AI agent on its tasks</button></div></div>`;
  }
  setContent(`<div class="pagehead"><h1 class="h1">Tasks</h1></div><div class="tabs">${tabs.map(([k, l]) => `<button class="${tab === k ? 'on' : ''}" onclick="location.hash='#/tasks/${k}'">${l}</button>`).join('')}</div><div class="stack-lg">${body}</div>`);
};
async function sendTask() {
  const r = $('#sendTask');
  const tgt = { formats: checked(r, 'input[name=sf]'), tags: checked(r, 'input[name=sg]'), stores: [...$('#sts').selectedOptions].map(o => +o.value) };
  const res = await post('/api/tasks', { template_id: val(r, '#stt') || null, title: val(r, '#stl') || null, body_md: val(r, '#stb'), est_minutes: +val(r, '#ste'), due_days: +val(r, '#std'), target: tgt, ignore_capacity: $('#sti').checked });
  $('#stres').innerHTML = `<div class="notice">Created ${res.created} task(s). ${res.skipped_at_capacity.length ? `Skipped at capacity: ${esc(res.skipped_at_capacity.join(', '))}` : ''}</div>`;
}
function questionInput(q, ans) {
  const v = ans[q.id], n = `q_${q.id}`, req = q.required ? ' *' : '';
  const img = q.image ? `<img src="${esc(q.image)}" style="max-width:240px;border-radius:8px">` : '';
  let inp = '';
  if (q.type === 'yesno') inp = `<div class="seg" style="max-width:240px">${['Yes', 'No'].map(o => `<button type="button" aria-pressed="${v === o}" onclick="setAns('${q.id}','${o}')">${o}</button>`).join('')}</div>`;
  else if (q.type === 'single') inp = `<select onchange="setAns('${q.id}',this.value)"><option value="">Choose…</option>${(q.options || []).map(o => `<option ${v === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
  else if (q.type === 'multi') inp = (q.options || []).map(o => `<label class="hrow"><input type="checkbox" ${(v || []).includes(o) ? 'checked' : ''} onchange="toggleAns('${q.id}','${esc(o)}',this.checked)">${esc(o)}</label>`).join('');
  else if (q.type === 'number') inp = `<input type="number" value="${esc(v ?? '')}" onchange="setAns('${q.id}',this.value===''?null:+this.value)">`;
  else if (q.type === 'date') inp = `<input type="date" value="${esc(v ?? '')}" onchange="setAns('${q.id}',this.value)">`;
  else if (q.type === 'photo') inp = `${v ? `<img src="${esc(v)}" style="max-width:200px;border-radius:8px">` : ''}<input type="file" accept="image/*" onchange="uploadAns('${q.id}',this.files[0])">`;
  else inp = `<textarea onchange="setAns('${q.id}',this.value)">${esc(v ?? '')}</textarea>`;
  return `<div class="stack" style="gap:6px"><b>${esc(q.text)}${req}</b>${img}${inp}</div>`;
}
const FORM = { ans: {}, refresh: null };
function setAns(id, v) { FORM.ans[id] = v; FORM.refresh && FORM.refresh(); }
function toggleAns(id, o, on) { const a = new Set(FORM.ans[id] || []); on ? a.add(o) : a.delete(o); FORM.ans[id] = [...a]; }
async function uploadFile(file) { const fd = new FormData(); fd.append('file', file); return api('/api/files', { body: fd, method: 'POST' }); }
async function uploadAns(id, f) { if (!f) return; const r = await uploadFile(f); setAns(id, r.url); }
function visibleLocal(qsList, ans) { return qsList.filter(q => !q.show_if || ans[q.show_if.q] === q.show_if.equals); }

Pages.task = async id => {
  const t = await api('/api/tasks/' + id);
  FORM.ans = { ...t.answers };
  const draw = () => { const el = $('#tq'); if (el) el.innerHTML = visibleLocal(t.questions, FORM.ans).map(q => questionInput(q, FORM.ans)).join('') || '<span class="muted">No questions – just mark it done.</span>'; };
  FORM.refresh = draw;
  const att = t.attachments.map(a => /\.(png|jpe?g|gif|svg|webp)$/i.test(a.url) ? `<img src="${esc(a.url)}" style="max-width:280px;border-radius:8px">` : /\.pdf$/i.test(a.url) ? `<iframe src="${esc(a.url)}" style="width:100%;height:360px;border:0"></iframe>` : `<a href="${esc(a.url)}" target="_blank">${icon('database')} ${esc(a.name || a.url)}</a>`).join('');
  setContent(`<div class="split"><div class="stack-lg"><div><a href="#/tasks" class="muted">Tasks</a><div class="hrow" style="margin-top:6px">${chipP(t.bucket)}${statusChip(t.status)}<span class="chip kind">${esc(t.store.code)}</span><span class="chip kind">${esc(t.source)}</span>${t.escalated ? '<span class="chip s-danger">Escalated</span>' : ''}</div>
    <h1 class="h1" style="margin-top:6px">${esc(t.title)}</h1><p class="lede">Due ${esc(t.due)} · ~${t.est_minutes} min · ${esc(t.assignee || t.assignee_role)}</p></div>
    <div class="card card-pad stack">${md(t.body_md)}${Object.keys(t.context).length ? `<div class="why"><span class="lbl">Why this was sent</span>${esc(Object.entries(t.context).map(([k, v]) => k + ': ' + (typeof v === 'object' ? JSON.stringify(v) : v)).join(' · '))}</div>` : ''}${att}</div>
    <div class="card card-pad stack"><h3 class="h3">Checklist</h3><div id="tq" class="stack"></div>
    ${t.status === 'open' ? `<button class="btn btn-primary btn-lg" onclick="completeTask(${t.id})">${icon('check')} Mark complete</button>` : `<div class="hrow"><span class="imp-pos">${icon('circle-check')} Completed ${esc(t.completed || '')}</span><button class="btn btn-secondary" onclick="post('/api/tasks/${t.id}/reopen').then(route)">Reopen</button></div>`}</div></div>
    <aside class="stack-lg"><div class="card card-pad stack"><h3 class="h4">Comments & photos</h3>${t.comments.map(c => `<div><b>${esc(c.author)}</b> <span class="muted">${esc(c.ts.slice(0, 16))}</span>${md(c.text)}</div>`).join('') || '<span class="muted">None yet.</span>'}
      <textarea id="tc" placeholder="Add a comment"></textarea><input type="file" id="tcf" accept="image/*"><button class="btn btn-secondary" onclick="taskComment(${t.id})">${icon('send')} Post</button></div>
    <div class="card card-pad stack"><h3 class="h4">Activity</h3>${t.activity.map(a => `<div class="s muted">${esc(a.ts.slice(0, 16))} · ${esc(a.who || 'System')} ${esc(a.action)} ${esc(a.detail || '')}</div>`).join('')}</div></aside></div>`);
  draw();
};
async function completeTask(id) { const r = await post(`/api/tasks/${id}/complete`, { answers: FORM.ans }); toast('Done' + (r.followups && r.followups.length ? ` – ${r.followups.length} follow-up task(s) created` : '')); route(); }
async function taskComment(id) { const f = $('#tcf').files[0]; const img = f ? (await uploadFile(f)).url : null; await post(`/api/tasks/${id}/comment`, { text: $('#tc').value, image: img }); route(); }

/* ---------- Store walks / audits / checklists ---------- */
Pages.walks = async () => {
  const sv = await api('/api/surveys');
  setContent(`<div class="pagehead"><div><h1 class="h1">Store walks, audits & checklists</h1><p class="lede">Questions adapt to the store (tags, format) and to live performance.</p></div></div>
    <div class="stack">${sv.filter(s => s.active).map(s => `<div class="card card-pad hrow"><div class="grow"><b>${esc(s.name)}</b><div class="muted">${esc(s.kind)} · ${s.questions.length} questions · ${s.responses} responses</div></div>
      <select id="ws${s.id}">${storeOpts(S.store, false)}</select><button class="btn btn-primary" onclick="location.hash='#/walk/${s.id}/'+$('#ws${s.id}').value">Start</button><button class="btn btn-secondary" onclick="showResponses(${s.id})">Results</button></div>`).join('')}</div><div id="resp"></div>`);
};
async function showResponses(id) {
  const r = await api(`/api/surveys/${id}/responses`);
  $('#resp').innerHTML = `<div class="card card-pad"><h3 class="h3">Latest responses</h3><table class="tbl"><thead><tr><th>Store</th><th>Week</th><th>By</th><th class="r">Score</th><th>Answers</th></tr></thead><tbody>
    ${r.map(x => `<tr><td>${esc(x.code)}</td><td>${x.week}</td><td>${esc(x.who || '')}</td><td class="r">${num(x.score, 0)}%</td><td class="s">${esc(Object.values(x.answers).filter(v => typeof v === 'string' && v.length > 3).join(' · ').slice(0, 120))}</td></tr>`).join('')}</tbody></table></div>`;
}
Pages.walk = async (sid, store, visit) => {
  FORM.ans = {};
  const load = async () => {
    const f = await post(`/api/surveys/${sid}/form?store=${store}`, { answers: FORM.ans });
    const el = $('#wq'); if (!el) return;
    el.innerHTML = f.questions.map(q => questionInput(q, FORM.ans)).join('') + (f.hidden ? `<p class="muted">${f.hidden} question(s) hidden – not relevant to this store or its answers.</p>` : '');
    $('#wprev').innerHTML = f.previous ? `<b>Last time (${esc(f.previous.ts.slice(0, 10))}, ${esc(f.previous.who || '')}) – score ${num(f.previous.score, 0)}%</b>${Object.entries(f.previous.answers).map(([k, v]) => `<div class="s">${esc(k)}: ${esc(Array.isArray(v) ? v.join(', ') : v)}</div>`).join('')}` : '<span class="muted">No previous response.</span>';
  };
  FORM.refresh = load;
  const st = S.meta.stores.find(s => s.id === +store) || {};
  setContent(`<div class="split"><div class="card card-pad stack"><a href="#/walks" class="muted">Store walks</a><h1 class="h2">${esc(st.code || '')} ${esc(st.name || '')}</h1><div id="wq" class="stack-lg">${loading()}</div>
    <button class="btn btn-primary btn-lg" onclick="submitWalk(${sid},${store},${visit || 'null'})">${icon('check')} Submit</button></div><aside class="card card-pad stack" id="wprev"></aside></div>`);
  await load();
};
async function submitWalk(sid, store, visit) {
  const r = await post(`/api/surveys/${sid}/submit`, { store_id: store, answers: FORM.ans, visit_id: visit });
  toast(`Submitted – score ${num(r.score, 0)}%` + (r.followups && r.followups.length ? `, ${r.followups.length} follow-up task(s)` : ''));
  location.hash = visit ? '#/visit/' + visit : '#/walks';
}

/* ---------- My business / KPI drill / P&L ---------- */
Pages.business = async () => {
  const b = await api('/api/business' + qs({ store: S.store }));
  const fmtv = (x, v) => x.unit === '$' ? kfmt(v) : num(v) + (x.unit === '%' ? '%' : x.unit && x.unit !== '$' ? ' ' + x.unit : '');
  setContent(`<div class="pagehead"><div><h1 class="h1">My business</h1><p class="lede">Week ${b.week}. ${S.store || S.meta.stores.length === 1 ? 'Rank is against all stores.' : 'Averages across your stores; click a tile for rankings and opportunities.'}</p></div></div>
    <div class="kpis">${b.tiles.map(x => { const v = x.trend.map(t => t.value), last = v[v.length - 1], prev = v[v.length - 2];
      const up = last > prev, good = (x.better === 'lower') ? !up : up;
      return `<a class="card kpi" href="#/kpi/${x.kpi}" style="text-decoration:none;color:inherit"><span class="k">${esc(x.label)}</span><span class="v num">${fmtv(x, last)}</span>
      <span class="d ${good ? 'imp-pos' : 'imp-neg'}">${icon(up ? 'trending-up' : 'trending-down', 'i-sm')} ${fmtv(x, last - prev)} vs last week</span>${Charts.spark(v)}
      <span class="s muted">${x.rank ? `#${x.rank} of ${x.of} ${x.rank_change ? (x.rank_change > 0 ? '▲' : '▼') + Math.abs(x.rank_change) : ''}` : `${x.below_avg}/${x.stores} stores below company avg`}${x.budget ? ` · budget ${kfmt(x.budget)} · LY ${kfmt(x.ly)}` : ''}</span>
      <span class="s">${x.live} live mission(s) · <span class="imp-pos">${x.improving} improving</span>${x.declining ? ` · <span class="imp-neg">${x.declining} declining</span>` : ''}</span></a>`; }).join('')}</div>`);
};
Pages.kpi = async (k, tab = 'graph') => {
  const d = await api(`/api/kpi/${k}` + qs({ store: S.store }));
  const g = d.graph, unit = d.unit;
  const f = v => unit === '$' ? money(v) : num(v, 2) + (unit === '%' ? '%' : '');
  let body = '';
  if (tab === 'graph') body = `<div class="card card-pad stack">${Charts.line({ labels: g.map(x => 'W' + x.week), series: [{ values: g.map(x => x.mine), color: 'var(--ct-color-impact-store-line)' }, { values: g.map(x => x.quart && x.quart[2]), color: 'var(--ct-color-impact-control-line)', dash: true }],
    band: g.map(x => x.quart && [x.quart[1], x.quart[3]]), band2: g.map(x => x.quart && [x.quart[0], x.quart[4]]) })}
    <div class="legend"><span><i style="background:var(--ct-color-impact-store-line)"></i>${S.store || S.meta.stores.length === 1 ? 'Your store' : 'Your stores (avg)'}</span><span><i style="background:var(--ct-color-impact-control-line)"></i>Company median</span><span><i style="background:var(--ct-color-impact-band);height:10px"></i>Middle 50%</span><span><i style="background:var(--ct-color-surface-sunken);height:10px"></i>Min–max</span></div></div>`;
  else if (tab === 'rank') body = `<div class="card"><table class="tbl"><thead><tr><th>#</th><th>Store</th><th class="r">${esc(d.label)}</th></tr></thead><tbody>${d.rankings.map(r => `<tr class="${r.mine ? 'sel' : ''}"><td>${r.rank}</td><td>${esc(r.code)} ${esc(r.name)}</td><td class="r">${f(r.value)}</td></tr>`).join('')}</tbody></table></div>`;
  else if (tab === 'opps') body = `<div class="card"><table class="tbl"><thead><tr><th>Store</th><th>Opportunity</th><th class="r">Gap/wk</th><th class="r">Score</th><th></th></tr></thead><tbody>${d.opportunities.map(o => `<tr><td>${esc(o.code)}</td><td>${esc(o.title)}</td><td class="r">${money(o.gap_value)}</td><td class="r">${num(o.score, 0)}</td>
    <td>${o.mission_id ? `<a class="chip s-info" href="#/mission/${o.mission_id}">${esc(o.label)}</a>` : `<button class="btn btn-secondary" onclick='writeMission(${JSON.stringify({ store_id: o.store_id, kpi: o.kpi, cat_id: o.cat_id, title: o.title })})'>${isStore() ? 'Write mission' : 'Send as mission'}</button>`}</td></tr>`).join('') || '<tr><td colspan=5 class="empty">No open opportunities.</td></tr>'}</tbody></table></div>`;
  else body = `<div class="stack">${d.activity.map(m => `<a class="card tile" href="#/mission/${m.id}"><span class="t">${esc(m.title)}</span><span class="s">${esc(m.store_code)} · ${esc(m.label)} · ${esc(m.action_type || '')} ${m.impact ? impactTxt(m.impact) : ''}</span></a>`).join('') || '<div class="empty">No mission activity on this KPI.</div>'}</div>`;
  setContent(`<div class="pagehead"><div><a href="#/business" class="muted">My business</a><h1 class="h1">${esc(d.label)}</h1></div></div>
    <div class="tabs">${[['graph', 'Graph'], ['rank', 'Rankings'], ['opps', 'Opportunities'], ['act', 'Activity']].map(([t, l]) => `<button class="${tab === t ? 'on' : ''}" onclick="location.hash='#/kpi/${k}/${t}'">${l}</button>`).join('')}</div>${body}`);
};
Pages.pnl = async (mode = 'tree') => {
  const single = S.store || (S.meta.stores.length === 1 ? S.meta.stores[0].id : null);
  if (mode === 'biggest') {
    const rows = await api('/api/pnl' + qs({ store: S.store, mode: 'biggest' }));
    return setContent(`${pnlHead(mode)}<div class="card"><table class="tbl"><thead><tr><th>Store</th><th>Opportunity</th><th class="r">Actual</th><th class="r">Expected</th><th class="r">Gap/wk</th><th></th></tr></thead><tbody>
      ${rows.map(o => `<tr><td>${esc(o.code)}</td><td>${esc(o.title)}</td><td class="r">${num(o.actual, 1)}</td><td class="r">${num(o.expected, 1)}</td><td class="r">${money(o.gap_value)}</td><td><button class="btn btn-ghost" onclick='writeMission(${JSON.stringify({ store_id: o.store_id, kpi: o.kpi, cat_id: o.cat_id, title: o.title })})'>${icon('send')}</button></td></tr>`).join('')}</tbody></table></div>`);
  }
  const [p, cl] = await Promise.all([api('/api/pnl' + qs({ store: S.store })), single ? api('/api/countlist?store=' + single) : Promise.resolve(null)]);
  setContent(`${pnlHead(mode)}<div class="${cl ? 'split' : ''}"><div class="card"><table class="tbl"><thead><tr><th>Department / category</th><th class="r">Sales</th><th class="r">Last year</th><th class="r">vs LY</th><th class="r">Opportunity/wk</th><th></th></tr></thead><tbody>
    ${p.departments.map(d => `<tr style="font-weight:600"><td>${esc(d.name)}</td><td class="r">${money(d.actual)}</td><td class="r">${money(d.ly)}</td><td class="r">${d.ly ? num((d.actual / d.ly - 1) * 100) + '%' : '—'}</td><td class="r">${money(d.opportunity)}</td><td class="r muted">waste ${money(d.waste)}</td></tr>
      ${d.children.map(c => `<tr><td style="padding-left:32px">${esc(c.name)}</td><td class="r">${money(c.actual)}</td><td class="r">${money(c.ly)}</td><td class="r ${c.actual >= c.ly ? 'imp-pos' : 'imp-neg'}">${c.ly ? num((c.actual / c.ly - 1) * 100) + '%' : '—'}</td><td class="r">${c.opportunity > 1 ? money(c.opportunity) : '—'}</td>
      <td>${c.opportunity > 1 && single ? `<button class="btn btn-ghost" title="Send as mission" onclick='writeMission(${JSON.stringify({ store_id: single, kpi: "sales", cat_id: c.id, title: c.name + " sales below peers" })})'>${icon('send')}</button>` : ''}</td></tr>`).join('')}`).join('')}</tbody></table></div>
    ${cl ? `<aside class="card card-pad stack"><h3 class="h4">${icon('list-checks')} Today's count list</h3><p class="muted">Categories most likely to have drifted between booked and actual stock.</p>${cl.map((r, i) => `<div class="row" style="padding:6px 0"><b>${i + 1}</b><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${esc(r.dept)} · volatility ${num(r.volatility * 100, 0)}% · waste ${num(r.waste_ratio * 100, 1)}%</div></div><span class="pill-num">${num(r.risk, 2)}</span></div>`).join('')}</aside>` : ''}</div>`);
};
const pnlHead = mode => `<div class="pagehead"><div><h1 class="h1">P&L explorer</h1><p class="lede">Sales by department and category vs last year, with the peer-benchmarked opportunity.</p></div>
  <div class="seg"><button aria-pressed="${mode === 'tree'}" onclick="location.hash='#/pnl/tree'">Hierarchy</button><button aria-pressed="${mode === 'biggest'}" onclick="location.hash='#/pnl/biggest'">Biggest opportunities</button></div></div>`;

/* ---------- Team / coaching ---------- */
Pages.team = async () => {
  const t = await api('/api/team');
  const sortSel = S.cache.teamSort || 'kpis_below';
  const list = [...t].sort((a, b) => (b[sortSel] ?? -1) - (a[sortSel] ?? -1));
  setContent(`<div class="pagehead"><div><h1 class="h1">Team</h1><p class="lede">Who needs support? Inbox backlog, logins, live missions and KPIs behind peers.</p></div>
    <label class="f">Sort by<select onchange="S.cache.teamSort=this.value;route()">${[['kpis_below', 'KPIs behind peers'], ['incoming', 'Inbox backlog'], ['days_since_login', 'Days since login'], ['overdue', 'Overdue tasks'], ['red', 'Declining missions']].map(([k, l]) => `<option value="${k}" ${sortSel === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
    <div class="grid3">${list.map(p => `<div class="card card-pad stack"><div class="hrow"><span class="avatar">${esc(p.name.split(' ').map(x => x[0]).join(''))}</span><div class="grow"><b>${esc(p.name)}</b><div class="muted s">${esc(S.meta.roles[p.role])} ${p.store ? '· ' + esc(p.store.code) : ''}</div></div></div>
      <div class="grid2 s"><span>Inbox <b>${p.incoming}</b></span><span>Last login <b>${p.days_since_login == null ? 'never' : p.days_since_login + 'd'}</b></span><span>Live <b>${p.live}</b> <span class="dotst green"></span>${p.green} <span class="dotst red"></span>${p.red}</span>
      <span>KPIs behind <b>${p.kpis_below}/${p.kpis}</b></span><span>Open tasks <b>${p.open_tasks}</b></span><span>Overdue <b class="${p.overdue ? 'imp-neg' : ''}">${p.overdue}</b></span></div>
      <div class="hrow"><button class="btn btn-secondary" onclick="coachNote(${p.id},'${esc(p.name)}')">${icon('message-square')} Coach</button>${p.store_id ? `<button class="btn btn-ghost" onclick="S.store=${p.store_id};location.hash='#/home'">View store</button>` : ''}</div></div>`).join('') || '<div class="empty">No team members in scope.</div>'}</div>`);
};
async function coachNote(uid, name) {
  const ok = await modal('Coaching note for ' + name, `<textarea id="cn" placeholder="What went well, what to focus on next"></textarea>`, [{ label: 'Cancel' }, { label: 'Send', primary: true, action: m => post('/api/coach', { user_id: uid, text: val(m, '#cn') }) }]);
  if (ok) toast('Coaching note sent');
}
Pages.coaching = async () => {
  const n = await api('/api/coach/' + S.user.id);
  setContent(`<h1 class="h1">Coaching notes</h1><div class="stack">${n.map(x => `<div class="card card-pad"><b>${esc(x.author)}</b> <span class="muted">${esc(x.ts.slice(0, 16))}</span><p>${esc(x.text)}</p></div>`).join('') || '<div class="empty">No coaching notes yet.</div>'}</div>`);
};

/* ---------- Visits ---------- */
Pages.visits = async () => {
  const [sg, v] = await Promise.all([api('/api/visits/suggest'), api('/api/visits')]);
  setContent(`<div class="pagehead"><div><h1 class="h1">Store visits</h1><p class="lede">Where you're needed most: urgent tasks, open opportunity value and time since last visit.</p></div></div>
    <div class="split-even"><div class="card"><div class="card-pad"><h3 class="h3">Suggested next visits</h3></div><table class="tbl"><thead><tr><th>Store</th><th class="r">Must tasks</th><th class="r">Inbox $/wk</th><th class="r">Days since</th><th></th></tr></thead><tbody>
      ${sg.slice(0, 15).map(s => `<tr><td>${esc(s.code)} ${esc(s.name)}</td><td class="r">${s.must}</td><td class="r">${money(s.opp_value)}</td><td class="r">${s.days_since_visit}</td><td>${s.planned ? `<span class="chip s-info">${esc(s.planned)}</span>` : `<button class="btn btn-secondary" onclick="planVisit(${s.store_id})">Plan</button>`}</td></tr>`).join('')}</tbody></table></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Visits</h3></div><div class="list">${v.map(x => `<a class="row" href="#/visit/${x.id}" style="text-decoration:none;color:inherit">${icon('calendar')}<div class="grow"><div class="t">${esc(x.code)} ${esc(x.store_name)}</div><div class="s">${esc(x.date)} · ${esc(x.dm || '')}</div></div>${statusChip(x.status === 'done' ? 'done' : 'open')}</a>`).join('') || '<div class="empty">No visits yet.</div>'}</div></div></div>`);
};
async function planVisit(sid) {
  const ok = await modal('Plan a visit', `<label class="f">Date<input type="date" id="vd" value="${S.meta.today}"></label>`, [{ label: 'Cancel' }, { label: 'Plan visit', primary: true, action: m => post('/api/visits', { store_id: sid, date: val(m, '#vd') }) }]);
  if (ok) { toast('Visit planned – store manager notified'); location.hash = '#/visit/' + ok.id; }
}
Pages.visit = async id => {
  const v = await api('/api/visits/' + id);
  const done = v.status === 'done';
  const walk = (S.cache.surveys = S.cache.surveys || await api('/api/surveys')).find(s => s.kind === 'storewalk');
  setContent(`<div class="stack-lg"><div><a href="#/visits" class="muted">Visits</a><h1 class="h1">Visit: ${esc(v.store.code)} ${esc(v.store.name)}</h1><p class="lede">${esc(v.date)} · ${esc(v.dm || '')} · ${done ? 'completed' : 'planned'}</p></div>
    <div class="split-even"><div class="stack-lg">
      <div class="card card-pad stack"><h3 class="h3">Since last visit</h3>${v.last_visit ? `<p class="muted">${esc(v.last_visit.date)}: ${esc(v.last_visit.notes || '')}</p><b>Agreed actions</b>${v.last_visit.agreed_actions.map(a => `<div>• ${esc(a)}</div>`).join('') || '<span class="muted">none</span>'}` : '<span class="muted">First recorded visit.</span>'}</div>
      <div class="card card-pad stack"><h3 class="h3">Latest store walk</h3>${v.last_walk ? `<p class="muted">${esc(v.last_walk.survey)} · ${esc(v.last_walk.ts.slice(0, 10))} · score ${num(v.last_walk.score, 0)}%</p>${Object.entries(v.last_walk.answers).map(([k, a]) => `<div class="s">${esc(k)}: <b>${esc(Array.isArray(a) ? a.join(', ') : a)}</b></div>`).join('')}` : '<span class="muted">No walk yet.</span>'}
        ${walk && !done ? `<a class="btn btn-secondary" href="#/walk/${walk.id}/${v.store_id}/${v.id}">${icon('circle-check')} Run store walk now</a>` : ''}</div>
      <div class="card card-pad stack"><h3 class="h3">Missions & tasks</h3>${v.missions.map(m => `<a href="#/mission/${m.id}">${esc(m.label)}: ${esc(m.title)}</a>`).join('<br>') || '<span class="muted">No open missions.</span>'}
        <b>${v.tasks.length} open task(s)</b>${v.tasks.slice(0, 6).map(t => `<a href="#/task/${t.id}" class="s">${esc(t.title)} – due ${esc(t.due)}</a>`).join('')}</div></div>
    <div class="card card-pad stack" id="vf"><h3 class="h3">Visit notes & coaching</h3>
      <label class="f">Notes<textarea id="vn" ${done ? 'disabled' : ''}>${esc(v.notes || '')}</textarea></label>
      <label class="f">Coaching points (one per line – sent to the manager's coaching notes)<textarea id="vc" ${done ? 'disabled' : ''}>${esc(v.coaching.join('\n'))}</textarea></label>
      <label class="f">Agreed actions (one per line – each becomes a task)<textarea id="va" ${done ? 'disabled' : ''}>${esc(v.agreed_actions.join('\n'))}</textarea></label>
      ${done ? '<span class="imp-pos">Visit completed.</span>' : `<button class="btn btn-primary btn-lg" onclick="completeVisit(${v.id})">${icon('check')} Complete visit</button>`}</div></div></div>`);
};
async function completeVisit(id) {
  const lines = s => $(s).value.split('\n').map(x => x.trim()).filter(Boolean);
  const r = await post(`/api/visits/${id}/complete`, { notes: $('#vn').value, coaching: lines('#vc'), agreed_actions: lines('#va') });
  toast(`Visit completed – ${r.tasks.length} task(s) created`); route();
}

/* ---------- Best practice ---------- */
Pages.bp = async () => {
  const b = await api('/api/bestpractices');
  setContent(`<div class="pagehead"><div><h1 class="h1">Best practices</h1><p class="lede">Actions that measurably beat control stores. Adopt one to start a pre-filled mission.</p></div></div>
    <div class="grid2">${b.map(x => `<div class="card card-pad stack"><div class="hrow">${x.kpi ? `<span class="chip kind">${esc((S.meta.kpis[x.kpi] || {}).label || x.kpi)}</span>` : ''}<span class="chip s-success">+${money(x.impact_value)} vs control</span></div>
      <b>${esc(x.title)}</b><p>"${esc(x.body)}"</p><span class="muted s">${esc(x.author || '')} · ${esc(x.code || '')} ${esc(x.store_name || '')} · adopted by ${x.adopted}</span>
      <div class="hrow"><button class="btn btn-secondary" onclick="post('/api/bestpractices/${x.id}/like').then(route)">${icon('thumbs-up')} ${x.likes}</button><button class="btn btn-primary" onclick="adoptBP(${x.id})">${icon('plus')} Adopt</button></div></div>`).join('') || '<div class="empty">Nothing shared yet.</div>'}</div>`);
};
async function adoptBP(id) {
  let store = S.store || (S.meta.stores.length === 1 ? S.meta.stores[0].id : null);
  if (!store) { store = await modal('Adopt in which store?', `<select id="as">${storeOpts(null, false)}</select>`, [{ label: 'Cancel' }, { label: 'Adopt', primary: true, action: m => val(m, '#as') }]); if (!store) return; }
  const r = await post(`/api/bestpractices/${id}/adopt`, { store_id: store }); toast('Draft mission created from the practice'); location.hash = '#/mission/' + r.mission_id;
}

/* ---------- Comms ---------- */
Pages.comms = async () => {
  const c = await api('/api/comms');
  setContent(`<div class="pagehead"><div><h1 class="h1">Comms</h1><p class="lede">Targeted announcements with read tracking.</p></div></div><div class="${can('comms') ? 'split' : ''}">
    <div class="stack">${c.map(a => `<div class="card card-pad stack"><div class="hrow between"><b>${esc(a.title)}</b>${a.priority === 'high' ? '<span class="chip p-must">High</span>' : ''}</div><p>${esc(a.body)}</p>
      <span class="muted s">${esc(a.author || '')} · ${esc(a.ts.slice(0, 10))} · target ${esc(JSON.stringify(a.target) === '{}' ? 'everyone' : JSON.stringify(a.target))} · ${a.reads} read</span>
      ${a.read ? `<span class="imp-pos s">${icon('check', 'i-sm')} Read</span>` : `<button class="btn btn-secondary" onclick="post('/api/comms/${a.id}/read').then(route)">${a.require_ack ? 'Acknowledge' : 'Mark read'}</button>`}</div>`).join('') || '<div class="empty">No announcements.</div>'}</div>
    ${can('comms') ? `<aside class="card card-pad stack" id="cmp"><h3 class="h3">New announcement</h3><label class="f">Title<input id="ct"></label><label class="f">Message<textarea id="cb"></textarea></label>
      <label class="f">Formats${['Superstore', 'Standard', 'Express'].map(f => `<label class="hrow"><input type="checkbox" name="cf" value="${f}">${f}</label>`).join('')}</label>
      <label class="f">Tags<select id="ctg" multiple size="4">${S.meta.all_tags.map(t => `<option>${esc(t)}</option>`).join('')}</select></label>
      <label class="f">Roles<select id="cro" multiple size="3"><option value="store_manager">Store managers</option><option value="associate">Associates</option></select></label>
      <label class="hrow"><input type="checkbox" id="cp"> High priority</label><label class="hrow"><input type="checkbox" id="ca"> Require acknowledgement</label>
      <button class="btn btn-primary" onclick="sendComm()">${icon('send')} Publish</button></aside>` : ''}</div>`);
};
async function sendComm() {
  const r = $('#cmp'), tgt = {}; const f = checked(r, 'input[name=cf]'), tg = [...$('#ctg').selectedOptions].map(o => o.value), ro = [...$('#cro').selectedOptions].map(o => o.value);
  if (f.length) tgt.formats = f; if (tg.length) tgt.tags = tg; if (ro.length) tgt.roles = ro;
  const res = await post('/api/comms', { title: $('#ct').value, body: $('#cb').value, target: tgt, priority: $('#cp').checked ? 'high' : 'normal', require_ack: $('#ca').checked ? 1 : 0 });
  toast(`Published to ${res.recipients} people`); route();
}

/* ---------- Impact ---------- */
Pages.impact = async () => {
  const [d, th, res] = await Promise.all([api('/api/impact'), api('/api/ai/themes'), api('/api/missions' + qs({ status: 'live,done', store: S.store }))]);
  const measured = res.filter(m => m.impact && m.impact.weeks_measured).sort((a, b) => b.end_week - a.end_week);
  const tbl = (rows, h) => `<table class="tbl"><thead><tr><th>${h}</th><th class="r">Missions</th><th class="r">Win rate</th><th class="r">Net impact</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="r">${r.n}</td><td class="r">${r.win_rate}%</td><td class="r ${r.value >= 0 ? 'imp-pos' : 'imp-neg'}">${money(r.value)}</td></tr>`).join('')}</tbody></table>`;
  setContent(`<div class="pagehead"><div><h1 class="h1">Impact</h1><p class="lede">Net results of every launched mission, measured as difference-in-differences against same-format control stores.</p></div>
    <a class="btn btn-secondary" href="#" onclick="dl('/api/export/impact.csv','impact.csv');return false">${icon('database')} Export CSV</a></div>
    <div class="kpis"><div class="card kpi"><span class="k">Net impact (in-mission weeks)</span><span class="v imp-pos">${kfmt(d.total)}</span></div><div class="card kpi"><span class="k">Missions measured</span><span class="v">${d.missions}</span></div>
    <div class="card kpi"><span class="k">Win rate</span><span class="v">${d.win_rate}%</span></div><div class="card kpi"><span class="k">Post-mission erosion</span><span class="v ${d.erosion < 0 ? 'imp-neg' : 'imp-pos'}">${kfmt(d.erosion)}</span></div></div>
    <div class="split"><div class="card"><div class="card-pad hrow between" style="padding-bottom:0"><h3 class="h3">All results</h3><span class="muted">${measured.length} measured</span></div><div class="list">
      ${measured.slice(0, 25).map(m => `<a class="row" href="#/mission/${m.id}" style="text-decoration:none;color:inherit"><div class="grow"><div>${verdict(m.impact)}</div><div class="t" style="margin-top:4px">${esc(m.title)} <span class="muted">· ${esc(m.store_code)}</span></div>
        <div class="s">${m.impact.weekly >= 0 ? '+' : ''}${kfmt(m.impact.weekly)}/wk · likely ${kfmt(m.impact.weekly_low)} to ${kfmt(m.impact.weekly_high)} · ${esc((m.impact.confidence || '').toLowerCase())} confidence · ${UI[m.status]}</div></div>${icon('chevron-right')}</a>`).join('') || '<div class="empty">Nothing measured yet.</div>'}</div></div>
    <aside class="card card-pad stack"><h3 class="h3">Can I trust this number?</h3>
      <div class="hrow" style="align-items:flex-start">${icon('circle-check')}<span><b>Fair comparison.</b> Each mission is compared with up to 12 same-format stores with similar space that were not running the same mission. The group is fixed when the mission is accepted.</span></div>
      <div class="hrow" style="align-items:flex-start">${icon('circle-check')}<span><b>Seasonality removed.</b> We subtract what the comparison stores did on their own over the same weeks (difference-in-differences).</span></div>
      <div class="hrow" style="align-items:flex-start">${icon('info')}<span><b>Likely range.</b> 90% range based on how much comparison stores move with no mission. "Worked" means the whole range is above zero.</span></div></aside></div>
    <div class="card card-pad stack"><h3 class="h3">Net impact by week</h3>${Charts.bars({ labels: d.weekly.map(x => 'W' + x.week), values: d.weekly.map(x => x.value) })}</div>
    <div class="split-even"><div class="card card-pad">${tbl(d.by_kpi, 'KPI')}</div><div class="card card-pad">${tbl(d.by_action, 'Action type')}</div><div class="card card-pad">${tbl(d.by_district, 'District')}</div><div class="card card-pad">${tbl(d.by_region, 'Region')}</div></div>
    <div class="split-even"><div class="card card-pad stack"><h3 class="h3">${icon('trophy')} Best managers (impact per $100k sales)</h3><table class="tbl"><tbody>${d.leaders.map((l, i) => `<tr><td>${i + 1}</td><td>${esc(l.manager || '')}</td><td>${esc(l.store)}</td><td class="r">${money(l.per_100k)}</td></tr>`).join('')}</tbody></table></div>
    <div class="card card-pad stack"><h3 class="h3">${icon('sparkles')} AI themes from walks, rejections & visit notes</h3>${th.map(t => `<div><b>${esc(t.label)}</b><div class="muted s">${esc(t.scope)} · ${t.count} stores · ${esc(t.keywords.join(', '))}</div></div>`).join('') || '<span class="muted">No themes this week.</span>'}
      <button class="btn btn-secondary" onclick="post('/api/ai/themes/run').then(r=>{toast(r.missions_created+' theme mission(s) created');route()})">Re-run theme extraction</button></div></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Engagement</h3></div><table class="tbl"><thead><tr><th>Store</th><th>Manager</th><th>Last login</th><th class="r">Accepted</th><th class="r">Rejected</th><th class="r">Waiting</th><th class="r">Action rate</th></tr></thead><tbody>
      ${d.engagement.map(e => `<tr><td>${esc(e.code)}</td><td>${esc(e.manager || '')}</td><td>${esc(e.last_login || 'never')}</td><td class="r">${e.accepted || 0}</td><td class="r">${e.rejected || 0}</td><td class="r">${e.waiting || 0}</td><td class="r">${e.action_rate}%</td></tr>`).join('')}</tbody></table></div>`);
};
async function dl(path, name) {
  const r = await fetch(path, { headers: { 'X-User': S.user.id } }); if (!r.ok) return toast('Download failed', true);
  const b = await r.blob(), a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; a.click();
}

/* ---------- Campaigns (HQ steering) ---------- */
Pages.campaigns = async () => {
  const [c, b] = await Promise.all([api('/api/campaigns'), api('/api/blackouts')]);
  const kp = Object.entries(S.meta.kpis).filter(([k]) => !['custom', 'equipment', 'dc_quality'].includes(k));
  setContent(`<div class="pagehead"><div><h1 class="h1">Campaigns & steering</h1><p class="lede">Boost KPIs or categories in every targeted inbox, and protect busy periods with blackouts.</p></div>
    <button class="btn btn-secondary" onclick="post('/api/admin/reprioritise').then(r=>{toast('Re-prioritised: '+r.sent+' missions sent');route()})">Re-run prioritisation now</button></div>
    <div class="split"><div class="stack">${c.map(x => `<div class="card card-pad stack"><div class="hrow between"><b>${esc(x.name)}</b>${x.active ? '<span class="chip s-success">Active</span>' : '<span class="chip s-neutral">Paused</span>'}</div>
      <p class="muted">${esc(x.message || '')}</p><div class="hrow"><span class="chip ${x.push === 'must' ? 'p-must' : 'kind'}">${x.push === 'must' ? 'Must-do' : esc(x.push)}</span><span class="chip kind">${x.accept_rate}% accepted</span><span class="chip kind">${x.holdout.length} comparison stores held back</span></div><div class="s">KPIs: ${esc(x.kpis.map(k => (S.meta.kpis[k] || {}).label || k).join(', ') || 'any')} · categories: ${esc(x.categories.map(catName).join(', ') || 'any')} · boost ×${x.boost} · weeks ${x.start_week}–${x.end_week}</div>
      <div class="grid3"><div class="fact"><span class="k">Missions sent</span><span class="v">${x.missions}</span></div><div class="fact"><span class="k">Launched</span><span class="v">${x.launched}</span></div><div class="fact"><span class="k">Net impact</span><span class="v imp-pos">${money(x.impact)}</span></div></div>
      <button class="btn btn-secondary" onclick='toggleCamp(${JSON.stringify(x)})'>${x.active ? 'Pause' : 'Activate'}</button></div>`).join('') || '<div class="empty">No campaigns.</div>'}
      <div class="card card-pad stack"><h3 class="h3">Blackout periods (no new missions)</h3>${b.map(x => `<div class="hrow"><span class="grow">${esc(x.name)} · ${esc(x.start_date)} → ${esc(x.end_date)}</span><button class="btn btn-ghost" onclick="api('/api/blackouts/${x.id}',{method:'DELETE'}).then(route)">${icon('x')}</button></div>`).join('')}
        <div class="hrow"><input id="bn" placeholder="Name"><input id="bs" type="date"><input id="be" type="date"><button class="btn btn-secondary" onclick="post('/api/blackouts',{name:$('#bn').value,start_date:$('#bs').value,end_date:$('#be').value}).then(route)">Add</button></div></div></div>
    <aside class="stack-lg"><div class="card card-pad stack" id="cf"><h3 class="h3">New campaign</h3><label class="f">Name<input id="cn" placeholder="e.g. Holiday Baking Push"></label><label class="f">Message to stores<textarea id="cm"></textarea></label>
      <label class="f">KPIs<select id="ck" multiple size="5" onchange="campPreview()">${kp.map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join('')}</select></label>
      <label class="f">Categories<select id="cc" multiple size="5" onchange="campPreview()">${S.meta.categories.map(c => `<option value="${c.id}">${c.parent_id ? '— ' : ''}${esc(c.name)}</option>`).join('')}</select></label>
      <label class="f">Which stores? (formats)<select id="cfm" multiple size="3" onchange="campPreview()"><option>Superstore</option><option>Standard</option><option>Express</option></select></label>
      <label class="f">Tags<select id="ctgs" multiple size="4" onchange="campPreview()">${S.meta.all_tags.map(t => `<option>${esc(t)}</option>`).join('')}</select></label>
      <b>How hard should it push?</b><div class="seg" id="cpush">${['gentle', 'standard', 'must'].map(p => `<button type="button" data-p="${p}" aria-pressed="${p === 'standard'}" onclick="document.querySelectorAll('#cpush button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.p==='${p}'));campPreview()">${p === 'must' ? 'Must-do' : p[0].toUpperCase() + p.slice(1)}</button>`).join('')}</div>
      <p class="muted s">Standard competes fairly with each store's own missions. Must-do skips the queue and is limited to ${S.meta.settings.max_must_per_quarter || 3} active per quarter.</p>
      <div class="grid2"><label class="f">From week<input id="cs" type="number" value="${S.meta.week}"></label><label class="f">To week<input id="ce" type="number" value="${S.meta.week + 4}"></label></div>
      <div id="cprev"></div><button class="btn btn-primary" onclick="saveCamp()">Launch & re-prioritise</button></div>
      <div class="card card-pad stack" id="pushback"><h3 class="h3">What stores are telling you</h3><p class="muted s">Reasons given when a mission was turned down or snoozed (last 4 weeks).</p>${loading()}</div></aside></div>`);
  campPreview(); loadPushback();
};
async function loadPushback() {
  const p = await api('/api/pushback'); const mx = Math.max(1, ...p.by_reason.map(r => r.n));
  $('#pushback').innerHTML = `<h3 class="h3">What stores are telling you</h3><p class="muted s">${p.total} missions turned down or snoozed · ${p.accept_rate}% of suggestions accepted.</p>
    ${p.by_reason.slice(0, 6).map(r => `<div class="stack" style="gap:4px"><div class="hrow between"><span>"${esc(r.key)}"</span><b>${r.n}</b></div><div class="bar"><span style="width:${r.n / mx * 100}%;background:var(--ct-color-priority-must-border)"></span></div></div>`).join('')}
    <details><summary class="s">By KPI and district</summary><div class="s">${p.by_kpi.map(x => `${esc(x.key)}: ${x.n}`).join(' · ')}</div><div class="s">${p.by_district.map(x => `${esc(x.key)}: ${x.n}`).join(' · ')}</div>
    <table class="tbl">${p.recent.slice(0, 12).map(r => `<tr><td>${esc(r.code)}</td><td><a href="#/mission/${r.id}">${esc(r.title)}</a></td><td>${esc(r.reason)}</td></tr>`).join('')}</table></details>`;
}
const pushSel = () => (document.querySelector('#cpush [aria-pressed=true]') || {}).dataset?.p || 'standard';
function campBody() {
  const tgt = {}; if (sel('#cfm').length) tgt.formats = sel('#cfm'); if (sel('#ctgs').length) tgt.tags = sel('#ctgs');
  return { name: $('#cn').value, message: $('#cm').value, kpis: sel('#ck'), categories: sel('#cc'), push: pushSel(), start_week: +$('#cs').value, end_week: +$('#ce').value, target: tgt };
}
async function campPreview() {
  const r = await post('/api/campaigns/preview', campBody());
  $('#cprev').innerHTML = `<div class="notice stack" style="gap:4px"><span><b>${r.stores}</b> stores match · ${r.regions} region(s) · ${r.with_gap} have a gap on these KPIs/categories now</span>
    ${r.at_limit.length ? `<span>${icon('triangle-alert', 'i-sm')} ${r.at_limit.length} store(s) already at their ${S.meta.settings.inbox_size || 3}-mission limit; their lowest-value suggestion moves to the backlog.</span>` : ''}
    ${pushSel() === 'must' ? `<span>Must-do campaigns this quarter: <b>${r.must_used}/${r.must_max}</b>${r.must_used >= r.must_max ? ' – limit reached' : ''}</span>` : ''}
    <span>${icon('shield-check', 'i-sm')} We'll hold back a few matching stores at random as a comparison group, so seasonal lift isn't counted as campaign impact.</span></div>`;
}
const sel = id => [...$(id).selectedOptions].map(o => o.value);
async function saveCamp() {
  const r = await post('/api/campaigns', campBody());
  toast(`Campaign saved – ${r.recompute.sent} missions re-prioritised`); route();
}
async function toggleCamp(x) { await post('/api/campaigns', { ...x, active: x.active ? 0 : 1 }); toast(x.active ? 'Paused' : 'Activated'); route(); }

/* ---------- DC load quality ---------- */
Pages.dc = async () => {
  const d = await api('/api/dc');
  const isDC = role() === 'dc_manager';
  setContent(`<div class="pagehead"><div><h1 class="h1">${isDC ? 'DC quality inbox' : 'Load quality'}</h1><p class="lede">Stores flag bad loads by pallet; the DC sees picker, loader, shift and history and closes the loop.</p></div></div>
    <div class="${isDC ? '' : 'split'}"><div class="stack">${d.flags.map(f => `<div class="card card-pad stack"><div class="hrow between"><b>${esc(f.issue_type)} · ${esc(f.pallet_id)} → ${esc(f.code)}</b>${statusChip(f.status === 'resolved' ? 'done' : 'open')}</div>
      <div class="s">${esc(f.dc)} · ${esc(f.shift)} shift · picker ${esc(f.picker)} (${f.picker_tenure_m} mo) · loader ${esc(f.loader)}</div><p>${esc(f.note || '')}</p>${f.photo ? `<img src="${esc(f.photo)}" style="max-width:200px;border-radius:8px">` : ''}
      ${f.status === 'resolved' ? `<span class="imp-pos s">Resolution: ${esc(f.resolution)}</span>` : can('dc') ? `<div class="hrow"><input id="rs${f.id}" class="grow" placeholder="What did the DC do?"><button class="btn btn-primary" onclick="post('/api/dc/flags/${f.id}/resolve',{resolution:$('#rs${f.id}').value}).then(()=>{toast('Resolved – store notified');route()})">Resolve</button></div>` : ''}</div>`).join('') || '<div class="empty">No load flags.</div>'}</div>
    ${!isDC ? `<aside class="card card-pad stack"><h3 class="h3">Flag a load</h3><label class="f">Pallet ID<select id="fp">${d.pallets.map(p => `<option>${esc(p.id)}</option>`).join('')}</select></label>
      <label class="f">Issue<select id="fi"><option>Crushed / damaged</option><option>Wrong store</option><option>Short / missing cases</option><option>Temperature breach</option><option>Poorly stacked</option></select></label>
      <label class="f">Note<textarea id="fn"></textarea></label><label class="f">Photo<input type="file" id="ff" accept="image/*"></label><button class="btn btn-primary" onclick="flagLoad()">${icon('send')} Send to DC</button></aside>` : ''}</div>`);
};
async function flagLoad() {
  const f = $('#ff').files[0]; const photo = f ? (await uploadFile(f)).url : null;
  const r = await post('/api/dc/flags', { pallet_id: $('#fp').value, issue_type: $('#fi').value, note: $('#fn').value, photo });
  await modal('Sent to the DC', `<p>${esc(r.context)}</p>`, [{ label: 'OK', primary: true }]); route();
}

/* ---------- Ask / notifications ---------- */
Pages.ask = async () => {
  setContent(`<div class="ai" style="max-width:820px"><div class="hd">${icon('sparkles')} Ask ColsTorso</div><div id="pageAsk" class="stack"><div class="msg">Answers are computed from the live database for your scope.</div></div>
    <div class="prompts">${['What should I focus on this week?', 'Which stores have the worst waste?', 'What worked for attachment rate?', 'Why is overtime high?', 'How much impact have missions delivered?', 'What themes are coming from store walks?', 'What tasks are overdue?'].map(p => `<button onclick="askSend(this.textContent,'#pageAsk')">${p}</button>`).join('')}</div>
    <form class="hrow" onsubmit="askSend(this.q.value,'#pageAsk');this.q.value='';return false"><input name="q" class="grow" placeholder="Ask anything about your stores"><button class="btn btn-primary">${icon('send')}</button></form></div>`);
};
Pages.notifications = async () => {
  const n = await api('/api/notifications'); await post('/api/notifications/read'); S.meta.unread = 0;
  setContent(`<h1 class="h1">Notifications</h1><div class="card"><div class="list">${n.map(x => `<a class="row" href="${esc(x.link || '#/home')}" style="text-decoration:none;color:inherit">${icon('bell', 'i-sm')}<div class="grow"><div class="t" style="font-weight:${x.read ? 400 : 600}">${esc(x.text)}</div><div class="s">${esc(x.ts.slice(0, 16))}</div></div></a>`).join('') || '<div class="empty">No notifications.</div>'}</div></div>`);
};

Pages.pushback = async () => {
  setContent(`<div class="pagehead"><div><h1 class="h1">Store feedback</h1><p class="lede">Why stores turn missions down or snooze them. Use it to fix data, supply and campaign design.</p></div></div><div class="card card-pad stack" id="pushback">${loading()}</div>`);
  await loadPushback();
};
