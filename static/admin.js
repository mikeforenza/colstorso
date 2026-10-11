/* Architect: data ingestion, no-code mission & task builders, survey builder, stores, users & permissions, settings, integrations */
const QTYPES = ['yesno', 'single', 'multi', 'number', 'text', 'date', 'photo'];
const QB = { list: [] };
function qbRender(el) {
  $(el).innerHTML = QB.list.map((q, i) => `<div class="qrow"><select onchange="QB.list[${i}].type=this.value">${QTYPES.map(t => `<option ${q.type === t ? 'selected' : ''}>${t}</option>`).join('')}</select>
    <input value="${esc(q.text || '')}" placeholder="Question" onchange="QB.list[${i}].text=this.value"><input value="${esc((q.options || []).join('|'))}" placeholder="Options a|b|c" onchange="QB.list[${i}].options=this.value?this.value.split('|'):undefined">
    <label class="hrow s"><input type="checkbox" ${q.required ? 'checked' : ''} onchange="QB.list[${i}].required=this.checked">req</label><button class="iconbtn" onclick="QB.list.splice(${i},1);qbRender('${el}')">${icon('x')}</button>
    <div class="qadv"><input placeholder="Show if question id…" value="${esc(q.show_if?.q || '')}" onchange="qbSet(${i},'show_if','q',this.value)"><input placeholder="…equals" value="${esc(q.show_if?.equals || '')}" onchange="qbSet(${i},'show_if','equals',this.value)">
    <input placeholder="Only stores tagged" value="${esc((q.store_attr?.tags || []).join('|'))}" onchange="QB.list[${i}].store_attr=this.value?{tags:this.value.split('|')}:undefined">
    <input placeholder="Follow-up task if answer = No" value="${esc(q.followup?.task_title || '')}" onchange="QB.list[${i}].followup=this.value?{equals:'No',task_title:this.value}:undefined">
    <input placeholder="Perf: metric (e.g. labor_ratio)" value="${esc(q.perf_condition?.metric || '')}" onchange="qbSet(${i},'perf_condition','metric',this.value)"><select onchange="qbSet(${i},'perf_condition','op',this.value)">${['>', '<'].map(o => `<option ${q.perf_condition?.op === o ? 'selected' : ''}>${o}</option>`).join('')}</select>
    <input placeholder="threshold" value="${esc(q.perf_condition?.threshold ?? '')}" onchange="qbSet(${i},'perf_condition','threshold',this.value)"><span class="muted s">id: ${esc(q.id)}</span></div></div>`).join('') +
    `<button class="btn btn-secondary" onclick="QB.list.push({id:'q'+Date.now().toString(36),type:'yesno',text:''});qbRender('${el}')">${icon('plus')} Add question</button>`;
}
function qbSet(i, k, f, v) { const q = QB.list[i]; if (!v) { if (q[k]) delete q[k][f]; if (q[k] && !Object.keys(q[k]).length) delete q[k]; return; } q[k] = q[k] || (k === 'perf_condition' ? { op: '>' } : {}); q[k][f] = v; }

Pages.architect = async (tab) => {
  const tabs = [can('data') && ['data', 'Data & uploads'], can('architect') && ['missions', 'Mission rules'], can('tasks_admin') && ['tasks', 'Task builder'], can('surveys_admin') && ['surveys', 'Survey builder'],
    can('architect') && ['stores', 'Stores'], can('users') && ['users', 'People & permissions'], can('architect') && ['settings', 'Settings'], ['integrations', 'AI & integrations']].filter(Boolean);
  tab = tab || tabs[0][0];
  const head = `<div class="pagehead"><h1 class="h1">Architect</h1></div><div class="tabs">${tabs.map(([k, l]) => `<button class="${tab === k ? 'on' : ''}" onclick="location.hash='#/architect/${k}'">${l}</button>`).join('')}</div>`;
  setContent(head + `<div id="arch" class="stack-lg">${loading()}</div>`);
  await (ARCH[tab] || ARCH.integrations)();
};
const A = html => { $('#arch').innerHTML = html; };
const ARCH = {};

ARCH.data = async () => {
  const d = await api('/api/data/uploads');
  A(`<div class="split"><div class="stack-lg"><div class="card card-pad stack" id="up"><h3 class="h3">Upload a CSV</h3><p class="muted">Map your columns, we validate every row, load it and re-run the mission engine on the new data.</p>
    <div class="grid2"><label class="f">What is it?<select id="ut"><option value="sales">Category sales (weekly)</option><option value="store">Store KPIs: traffic, labor, CSAT…</option><option value="missions">Missions from analytics</option><option value="stores">Stores (new / changed)</option></select></label>
    <label class="f">File<input type="file" id="uf" accept=".csv,text/csv"></label></div>
    <div class="hrow"><button class="btn btn-primary" onclick="preview()">Preview & map columns</button>${['sales', 'store', 'missions', 'stores'].map(t => `<a href="/api/data/template/${t}" class="btn btn-ghost">${t} template</a>`).join('')}</div><div id="map"></div></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Upload history</h3></div><table class="tbl"><tbody>${d.uploads.map(u => `<tr><td>${esc(u.ts.slice(0, 16))}</td><td>${esc(u.filename)}</td><td>${esc(u.target)}</td><td>${u.rows} rows</td><td>${esc(u.status)}</td></tr>`).join('') || '<tr><td class="empty">No uploads yet.</td></tr>'}</tbody></table></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Data quality issues</h3></div><table class="tbl"><tbody>${d.issues.slice(0, 40).map(i => `<tr><td><span class="chip ${i.severity === 'error' ? 's-danger' : i.severity === 'warning' ? 's-warning' : 's-info'}">${esc(i.severity)}</span></td><td>${esc(i.message)}</td></tr>`).join('') || '<tr><td class="empty">No issues.</td></tr>'}</tbody></table></div></div>
  <aside class="stack-lg"><div class="card card-pad stack"><h3 class="h4">Warehouse</h3><p>${d.rows.toLocaleString()} sales rows · weeks ${d.weeks.a}–${d.weeks.b}</p>
    <button class="btn btn-secondary" onclick="post('/api/admin/next_week').then(r=>{toast('Week '+r.week+' loaded: '+r.sent+' new missions');refreshMeta().then(route)})">${icon('database')} Simulate next week's data drop</button>
    <button class="btn btn-secondary" onclick="post('/api/admin/recompute').then(r=>toast('Engine re-run: '+r.opportunities+' opportunities, '+r.sent+' new missions'))">Re-run mission engine</button></div>
    <div class="card card-pad stack"><h3 class="h4">File-drop connector</h3><p class="muted s">Drop sales_*.csv / store_*.csv / missions_*.csv / stores_*.csv into <code>${esc(d.drop_path)}</code>.</p><p class="s">${d.dropfolder.length} file(s) waiting</p>
      <button class="btn btn-secondary" onclick="post('/api/connectors/dropfolder').then(r=>{toast('Processed '+r.length+' file(s)');route()})">Process drop folder</button></div>
    <div class="card card-pad stack"><h3 class="h4">Event hub</h3><p class="muted s">POST /api/events – external systems trigger tasks (recalls, weather…).</p>
      <select id="evt"><option>product_recall</option><option>weather_warning</option><option>new_manager</option></select><input id="evs" placeholder="Store codes, comma separated (blank = all)"><input id="evm" placeholder="Message">
      <button class="btn btn-secondary" onclick="post('/api/events',{type:$('#evt').value,store_codes:$('#evs').value?$('#evs').value.split(',').map(x=>x.trim()):undefined,message:$('#evm').value}).then(r=>toast('Event fired: '+(r.created||0)+' task(s) created'))">Fire event</button>
      ${d.events.slice(0, 5).map(e => `<div class="s muted">${esc(e.ts.slice(0, 16))} ${esc(e.type)}</div>`).join('')}</div>
    <div class="card card-pad stack"><h3 class="h4">Exports</h3>${['missions', 'impact', 'tasks', 'surveys', 'opportunities'].map(n => `<button class="btn btn-ghost" onclick="dl('/api/export/${n}.csv','${n}.csv')">${icon('database')} ${n}.csv</button>`).join('')}</div></aside></div>`);
};
const UP = {};
async function preview() {
  const f = $('#uf').files[0]; if (!f) return toast('Choose a CSV file', true);
  const fd = new FormData(); fd.append('file', f); fd.append('target', $('#ut').value);
  const p = await api('/api/data/preview', { body: fd, method: 'POST' }); Object.assign(UP, p, { target: $('#ut').value });
  const fields = [...p.fields.required.map(x => [x, 1]), ...p.fields.optional.map(x => [x, 0])];
  $('#map').innerHTML = `<h4 class="h4">${esc(p.filename)} · ${p.rows} rows</h4><table class="tbl"><thead><tr><th>ColsTorso field</th><th>Your column</th></tr></thead><tbody>${fields.map(([f, r]) => `<tr><td>${esc(f)}${r ? ' *' : ''}</td><td><select data-f="${f}"><option value="">— not in file —</option>${p.headers.map(h => `<option ${p.suggested[f] === h ? 'selected' : ''}>${esc(h)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table>
    <div style="overflow:auto"><table class="tbl"><thead><tr>${p.headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${p.sample.slice(0, 5).map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    <button class="btn btn-primary" onclick="ingest()">${icon('check')} Load & recompute missions</button><div id="ires"></div>`;
}
async function ingest() {
  const mapping = {}; document.querySelectorAll('#map select[data-f]').forEach(s => mapping[s.dataset.f] = s.value);
  const r = await post('/api/data/ingest', { token: UP.token, target: UP.target, mapping, filename: UP.filename });
  if (!r.ok) return $('#ires').innerHTML = `<div class="notice">${esc(r.error)}</div>`;
  $('#ires').innerHTML = `<div class="notice stack"><b>Loaded ${r.loaded} rows${r.weeks.length ? ' into week(s) ' + r.weeks.join(', ') : ''}.</b>${r.recompute ? `<span>Engine re-ran for week ${r.recompute.week}: ${r.recompute.opportunities} opportunities, ${r.recompute.sent} new missions.</span>` : ''}
    ${r.issues.slice(0, 12).map(i => `<span class="s">${esc(i.severity)}: ${esc(i.message)}</span>`).join('')}</div>`;
  refreshMeta();
}

ARCH.missions = async () => {
  const r = await api('/api/mission_rules');
  const metrics = ['cash_abs', 'gapscan_pct', 'invacc_pct', 'labor_ratio', 'overtime_pct', 'conversion_pct', 'csat', 'attach_pct', 'sales_vs_budget_pct', ...S.meta.categories.filter(c => !c.parent_id).map(c => 'waste_pct:' + c.id)];
  const mlabel = m => m.startsWith('waste_pct:') ? catName(m.split(':')[1]) + ' waste %' : m;
  A(`<div class="split"><div class="card"><div class="card-pad"><h3 class="h3">No-code mission rules</h3><p class="muted">Conditions on live data that create alert missions. Peer-benchmarked opportunities run automatically.</p></div>
    <table class="tbl"><thead><tr><th>Rule</th><th>Condition</th><th>Priority</th><th>Active</th><th></th></tr></thead><tbody>${r.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(mlabel(x.metric))} ${esc(x.op)} ${x.threshold}</td><td>${chipP(x.priority)}</td><td>${x.active ? 'Yes' : 'No'}</td><td><button class="btn btn-ghost" onclick='editRule(${JSON.stringify(x)})'>Edit</button></td></tr>`).join('')}</tbody></table></div>
    <aside class="card card-pad stack" id="rf"><h3 class="h3" id="rft">New rule</h3><input type="hidden" id="rid"><label class="f">Name<input id="rn"></label>
      <div class="grid3"><label class="f">Metric<select id="rm">${metrics.map(m => `<option value="${m}">${esc(mlabel(m))}</option>`).join('')}</select></label><label class="f">Is<select id="ro"><option>&gt;</option><option>&lt;</option></select></label><label class="f">Threshold<input id="rth" type="number" step="any"></label></div>
      <label class="f">Mission title ({value} = the store's number)<input id="rti" placeholder="Cash variance of \${value}"></label><label class="f">Guidance<textarea id="rg"></textarea></label>
      <div class="grid2"><label class="f">Priority<select id="rp"><option>Must</option><option>Should</option><option>Could</option></select></label><label class="f">Send to<select id="rr"><option value="store_manager">Store manager</option><option value="district_manager">District manager</option></select></label></div>
      <label class="f">Only formats<select id="rfm" multiple size="3"><option>Superstore</option><option>Standard</option><option>Express</option></select></label><label class="hrow"><input type="checkbox" id="ra" checked> Active</label>
      <button class="btn btn-primary" onclick="saveRule()">Save & preview</button><div id="rprev"></div><button class="btn btn-secondary" onclick="post('/api/mission_rules/deploy').then(r=>toast('Deployed: '+r.sent+' new missions sent'))">Deploy all rules now</button></aside></div>`);
};
function editRule(x) { $('#rft').textContent = 'Edit rule'; $('#rid').value = x.id; $('#rn').value = x.name; $('#rm').value = x.metric; $('#ro').value = x.op; $('#rth').value = x.threshold; $('#rti').value = x.title; $('#rg').value = x.guidance; $('#rp').value = x.priority; $('#rr').value = x.assignee_role; $('#ra').checked = !!x.active; }
async function saveRule() {
  const fm = sel('#rfm');
  const r = await post('/api/mission_rules', { id: $('#rid').value || null, name: $('#rn').value, metric: $('#rm').value, op: $('#ro').value, threshold: $('#rth').value, title: $('#rti').value, guidance: $('#rg').value, priority: $('#rp').value, assignee_role: $('#rr').value, active: $('#ra').checked ? 1 : 0, target: fm.length ? { formats: fm } : {} });
  $('#rid').value = r.id; $('#rprev').innerHTML = `<div class="notice">Saved. With this week's data it would fire for <b>${r.would_fire}</b> store(s)${r.stores.length ? ': ' + esc(r.stores.join(', ')) : ''}. Deploy to send.</div>`;
}

ARCH.tasks = async () => {
  const [t, r] = await Promise.all([api('/api/task_templates'), api('/api/task_rules')]);
  A(`<div class="split-even"><div class="stack-lg"><div class="card"><div class="card-pad"><h3 class="h3">Task templates</h3></div><table class="tbl"><tbody>${t.map(x => `<tr><td>${esc(x.name)}</td><td class="muted">${x.questions.length} q · ${x.est_minutes} min · ${esc(x.assignee_role)}</td><td><button class="btn btn-ghost" onclick='editTpl(${JSON.stringify(x).replace(/'/g, "&#39;")})'>Edit</button></td></tr>`).join('')}</tbody></table>
      <div class="card-pad"><button class="btn btn-secondary" onclick="editTpl({questions:[]})">${icon('plus')} New template</button></div></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Intelligent task rules</h3><p class="muted">Event, condition (live data) or schedule triggers. Capacity-aware; overdue tasks escalate.</p></div><table class="tbl"><tbody>${r.map(x => `<tr><td>${esc(x.name)}</td><td><span class="chip kind">${esc(x.trigger_type)}</span></td><td class="s muted">${esc(JSON.stringify(x.config))}</td><td><button class="btn btn-ghost" onclick='editTRule(${JSON.stringify(x)})'>Edit</button><button class="btn btn-ghost" onclick="post('/api/task_rules/${x.id}/run').then(r=>toast('Created '+(r.created||0)+' task(s)'))">Run now</button></td></tr>`).join('')}</tbody></table>
      <div class="card-pad"><button class="btn btn-secondary" onclick="editTRule({config:{},target:{}})">${icon('plus')} New rule</button></div></div>
    <div class="card card-pad stack"><h3 class="h4">Schedule from CSV</h3><p class="muted s">Columns: store_code, due (YYYY-MM-DD), optional title.</p><div class="hrow"><select id="ctpl">${t.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select><input type="file" id="ccsv" accept=".csv"><button class="btn btn-secondary" onclick="csvTasks()">Upload</button></div></div></div>
    <div class="card card-pad stack" id="ted"><p class="muted">Select a template or rule to edit.</p></div></div>`);
};
function editTpl(x) {
  QB.list = JSON.parse(JSON.stringify(x.questions || []));
  $('#ted').innerHTML = `<h3 class="h3">${x.id ? 'Edit' : 'New'} template</h3><input type="hidden" id="tid" value="${x.id || ''}"><label class="f">Name<input id="tn" value="${esc(x.name || '')}"></label><label class="f">Task title<input id="tt" value="${esc(x.title || '')}"></label>
    <label class="f">Instructions (markdown; images: ![alt](url))<textarea id="tb" rows="5">${esc(x.body_md || '')}</textarea></label><div class="hrow"><input type="file" id="tfile"><button class="btn btn-ghost" onclick="tplAttach()">Attach file</button><span id="tatt" class="s muted">${(x.attachments || []).map(a => esc(a.name)).join(', ')}</span></div>
    <div class="grid2"><label class="f">Estimated minutes<input id="te" type="number" value="${x.est_minutes || 15}"></label><label class="f">Assign to<select id="tr">${['store_manager', 'associate', 'district_manager', 'ai_agent'].map(r => `<option ${x.assignee_role === r ? 'selected' : ''}>${r}</option>`).join('')}</select></label></div>
    <b>Checklist questions</b><div id="qb"></div><button class="btn btn-primary" onclick="saveTpl()">Save template</button>`;
  QB.att = x.attachments || []; qbRender('#qb');
}
async function tplAttach() { const f = $('#tfile').files[0]; if (!f) return; const r = await uploadFile(f); QB.att.push({ url: r.url, name: r.name }); $('#tatt').textContent = QB.att.map(a => a.name).join(', '); }
async function saveTpl() { await post('/api/task_templates', { id: $('#tid').value || null, name: $('#tn').value, title: $('#tt').value, body_md: $('#tb').value, est_minutes: +$('#te').value, assignee_role: $('#tr').value, questions: QB.list, attachments: QB.att }); toast('Template saved'); route(); }
async function editTRule(x) {
  const t = await api('/api/task_templates');
  $('#ted').innerHTML = `<h3 class="h3">${x.id ? 'Edit' : 'New'} task rule</h3><input type="hidden" id="xid" value="${x.id || ''}"><label class="f">Name<input id="xn" value="${esc(x.name || '')}"></label>
    <label class="f">Trigger<select id="xt" onchange="trCfg()">${['event', 'condition', 'schedule'].map(k => `<option ${x.trigger_type === k ? 'selected' : ''}>${k}</option>`).join('')}</select></label><div id="xcfg"></div>
    <label class="f">Template<select id="xtp">${t.map(y => `<option value="${y.id}" ${x.template_id === y.id ? 'selected' : ''}>${esc(y.name)}</option>`).join('')}</select></label>
    <label class="f">Only formats<select id="xfm" multiple size="3">${['Superstore', 'Standard', 'Express'].map(f => `<option ${(x.target.formats || []).includes(f) ? 'selected' : ''}>${f}</option>`).join('')}</select></label>
    <div class="grid2"><label class="f">Due in days<input id="xd" type="number" value="${x.due_days || 3}"></label><label class="f">Escalate after (days overdue)<input id="xe" type="number" value="${x.escalate_after_days || 2}"></label></div>
    <label class="hrow"><input type="checkbox" id="xa" ${x.active !== 0 ? 'checked' : ''}> Active</label><button class="btn btn-primary" onclick="saveTRule()">Save rule</button>`;
  QB.cfg = x.config || {}; trCfg();
}
function trCfg() {
  const t = $('#xt').value, c = QB.cfg;
  $('#xcfg').innerHTML = t === 'event' ? `<label class="f">Event name<input id="xc1" value="${esc(c.event || '')}" placeholder="product_recall"></label><label class="hrow"><input type="checkbox" id="xc2" ${c.urgent ? 'checked' : ''}> Urgent (ignores capacity)</label>` :
    t === 'condition' ? `<div class="grid3"><label class="f">Metric<input id="xc1" value="${esc(c.metric || 'labor_ratio')}"></label><label class="f">Op<select id="xc2"><option ${c.op === '>' ? 'selected' : ''}>&gt;</option><option ${c.op === '<' ? 'selected' : ''}>&lt;</option></select></label><label class="f">Threshold<input id="xc3" type="number" step="any" value="${c.threshold ?? ''}"></label></div>` :
    `<div class="grid2"><label class="f">Every N weeks<input id="xc1" type="number" value="${c.every_weeks || 1}"></label><label class="f">Offset<input id="xc2" type="number" value="${c.offset || 0}"></label></div>`;
}
async function saveTRule() {
  const t = $('#xt').value; const cfg = t === 'event' ? { event: $('#xc1').value, urgent: $('#xc2').checked } : t === 'condition' ? { metric: $('#xc1').value, op: $('#xc2').value, threshold: +$('#xc3').value } : { every_weeks: +$('#xc1').value, offset: +$('#xc2').value };
  const fm = sel('#xfm');
  await post('/api/task_rules', { id: $('#xid').value || null, name: $('#xn').value, trigger_type: t, config: cfg, template_id: $('#xtp').value, target: fm.length ? { formats: fm } : {}, due_days: +$('#xd').value, escalate_after_days: +$('#xe').value, active: $('#xa').checked ? 1 : 0 });
  toast('Rule saved'); route();
}
async function csvTasks() { const f = $('#ccsv').files[0]; if (!f) return toast('Choose a CSV', true); const fd = new FormData(); fd.append('file', f); fd.append('template_id', $('#ctpl').value); const r = await api('/api/tasks/csv', { body: fd, method: 'POST' }); toast('Scheduled ' + (r.created ?? r) + ' task(s)'); }

ARCH.surveys = async () => {
  const sv = await api('/api/surveys');
  A(`<div class="split-even"><div class="card"><div class="card-pad"><h3 class="h3">Store walks, audits & checklists</h3></div><table class="tbl"><tbody>${sv.map(x => `<tr><td>${esc(x.name)}</td><td><span class="chip kind">${esc(x.kind)}</span></td><td>${x.questions.length} q · ${x.responses} responses</td><td><button class="btn btn-ghost" onclick='editSurvey(${JSON.stringify(x).replace(/'/g, "&#39;")})'>Edit</button></td></tr>`).join('')}</tbody></table>
    <div class="card-pad"><button class="btn btn-secondary" onclick="editSurvey({questions:[],kind:'storewalk',active:1})">${icon('plus')} New</button></div></div><div class="card card-pad stack" id="sed"><p class="muted">Select one to edit. Questions can depend on earlier answers, store tags and live performance; "No" answers can create follow-up tasks.</p></div></div>`);
};
function editSurvey(x) {
  QB.list = JSON.parse(JSON.stringify(x.questions || []));
  $('#sed').innerHTML = `<h3 class="h3">${x.id ? 'Edit' : 'New'} survey</h3><input type="hidden" id="sid" value="${x.id || ''}"><label class="f">Name<input id="sn" value="${esc(x.name || '')}"></label>
    <div class="grid2"><label class="f">Kind<select id="sk">${['storewalk', 'audit', 'checklist'].map(k => `<option ${x.kind === k ? 'selected' : ''}>${k}</option>`).join('')}</select></label><label class="hrow"><input type="checkbox" id="sa" ${x.active ? 'checked' : ''}> Active</label></div>
    <b>Questions</b><div id="sqb"></div><button class="btn btn-primary" onclick="saveSurvey()">Save</button>`;
  qbRender('#sqb');
}
async function saveSurvey() { await post('/api/surveys', { id: $('#sid').value || null, name: $('#sn').value, kind: $('#sk').value, questions: QB.list, active: $('#sa').checked ? 1 : 0, trigger: { type: 'schedule', every_weeks: 1 } }); S.cache.surveys = null; toast('Saved'); route(); }

ARCH.stores = async () => {
  const st = await api('/api/admin/stores');
  A(`<div class="card"><table class="tbl"><thead><tr><th>Store</th><th>Format</th><th>District</th><th>Status</th><th>Tags (comma separated)</th><th class="r">Capacity h/wk</th></tr></thead><tbody>
    ${st.map(s => `<tr><td>${esc(s.code)} ${esc(s.name)}</td><td>${esc(s.format)}</td><td>${esc(s.district)}</td><td><select onchange="post('/api/admin/stores/${s.id}',{status:this.value}).then(()=>toast('Status saved'))">${['New', 'Open', 'Closed'].map(x => `<option ${s.status === x ? 'selected' : ''}>${x}</option>`).join('')}</select></td>
    <td><input value="${esc(JSON.parse(s.tags || '[]').join(', '))}" onchange="post('/api/admin/stores/${s.id}',{tags:this.value.split(',')}).then(()=>toast('Tags saved'))"></td><td class="r"><input type="number" style="width:90px" value="${s.capacity_hours}" onchange="post('/api/admin/stores/${s.id}',{capacity_hours:this.value}).then(()=>toast('Capacity saved'))"></td></tr>`).join('')}</tbody></table></div>
    <p class="muted">Only Open stores receive missions. New stores start as New until you switch them to Open.</p>`);
};

ARCH.users = async () => {
  const [u, p] = await Promise.all([api('/api/admin/users'), api('/api/admin/permissions')]);
  A(`<div class="card"><div class="card-pad hrow between"><h3 class="h3">People</h3><button class="btn btn-secondary" onclick="editUser({})">${icon('plus')} Add person</button></div><table class="tbl"><thead><tr><th>Name</th><th>Role</th><th>Store / district</th><th>Last login</th><th></th></tr></thead><tbody>
    ${u.map(x => `<tr class="${x.active ? '' : 'muted'}"><td>${esc(x.name)}</td><td>${esc(p.roles[x.role] || x.role)}</td><td>${x.store_id ? 'Store ' + x.store_id : x.district_id ? 'District ' + x.district_id : x.region_id ? 'Region ' + x.region_id : '—'}</td><td>${esc(x.last_login || '—')}</td>
    <td>${x.active ? `<button class="btn btn-ghost" onclick='editUser(${JSON.stringify(x)})'>Edit</button><button class="btn btn-ghost" onclick="removeUser(${x.id})">Remove</button>` : 'removed'}</td></tr>`).join('')}</tbody></table></div>
    <div class="card"><div class="card-pad"><h3 class="h3">Role permissions</h3></div><div style="overflow:auto"><table class="tbl" id="perm"><thead><tr><th>Role</th>${p.capabilities.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>
    ${Object.keys(p.roles).map(r => `<tr><td>${esc(p.roles[r])}</td>${p.capabilities.map(c => `<td><input type="checkbox" data-r="${r}" data-c="${c}" ${(p.permissions[r] || []).includes(c) ? 'checked' : ''}></td>`).join('')}</tr>`).join('')}</tbody></table></div>
    <div class="card-pad"><button class="btn btn-primary" onclick="savePerms()">Save permissions</button></div></div>`);
};
async function editUser(x) {
  const roles = S.meta.roles;
  const ok = await modal(x.id ? 'Edit person' : 'Add person', `<label class="f">Name<input id="un" value="${esc(x.name || '')}"></label><label class="f">Email (demo only)<input id="ue" value="${esc(x.email || '')}"></label>
    <label class="f">Role<select id="ur">${Object.entries(roles).map(([k, v]) => `<option value="${k}" ${x.role === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>
    <label class="f">Store (for store roles)<select id="us"><option value="">—</option>${S.meta.stores.map(s => `<option value="${s.id}" ${x.store_id === s.id ? 'selected' : ''}>${esc(s.code)} ${esc(s.name)}</option>`).join('')}</select></label>
    <label class="f">District (for district managers)<select id="ud"><option value="">—</option>${S.meta.districts.map(d => `<option value="${d.id}" ${x.district_id === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></label>
    <label class="f">Region (for regional managers)<select id="ug"><option value="">—</option>${S.meta.regions.map(d => `<option value="${d.id}" ${x.region_id === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select></label><p class="muted s">A new store manager replaces the current one and gets the onboarding task automatically.</p>`,
    [{ label: 'Cancel' }, { label: 'Save', primary: true, action: m => post('/api/admin/users', { id: x.id, name: val(m, '#un'), email: val(m, '#ue'), role: val(m, '#ur'), store_id: val(m, '#us') || null, district_id: val(m, '#ud') || null, region_id: val(m, '#ug') || null }) }]);
  if (ok) { toast('Saved'); route(); }
}
async function removeUser(id) { const ok = await modal('Remove person?', '<p>Deactivates the account and anonymises their name and email. Their past work stays, attributed to "Former user".</p>', [{ label: 'Cancel' }, { label: 'Remove', primary: true, action: () => post(`/api/admin/users/${id}/remove`) }]); if (ok) { toast('Removed'); route(); } }
async function savePerms() { const p = {}; document.querySelectorAll('#perm input').forEach(i => { p[i.dataset.r] = p[i.dataset.r] || []; if (i.checked) p[i.dataset.r].push(i.dataset.c); }); await post('/api/admin/permissions', { permissions: p }); toast('Permissions saved'); await refreshMeta(); }

ARCH.settings = async () => {
  const s = S.meta.settings;
  A(`<div class="card card-pad stack" style="max-width:640px"><h3 class="h3">Mission engine settings</h3>
    <label class="f">Max suggested missions per store at a time<input id="si" type="number" min="1" max="10" value="${s.inbox_size || 3}"></label>
    <label class="f">Default measurement period (weeks)<input id="sd" type="number" min="1" max="12" value="${s.mission_duration || 4}"></label>
    <label class="f">Benchmark window (weeks averaged)<input id="sw" type="number" min="1" max="8" value="${s.window_weeks || 1}"></label>
    <label class="f">Max active Must-do campaigns per quarter<input id="sm" type="number" min="0" max="10" value="${s.max_must_per_quarter || 3}"></label>
    <label class="hrow"><input type="checkbox" id="sa" ${s.require_approval ? 'checked' : ''}> District manager must approve store plans before they start</label>
    <button class="btn btn-primary" onclick="post('/api/admin/settings',{inbox_size:+$('#si').value,mission_duration:+$('#sd').value,window_weeks:+$('#sw').value,max_must_per_quarter:+$('#sm').value,require_approval:$('#sa').checked}).then(()=>{toast('Settings saved');refreshMeta()})">Save</button></div>`);
};

ARCH.integrations = async () => {
  const ctx = await api('/api/ai/context');
  A(`<div class="split-even"><div class="card card-pad stack"><h3 class="h3">MCP-style tool endpoint</h3><p class="muted">AI assistants can call ColsTorso over JSON-RPC at <code>POST /mcp</code> (header <code>X-User</code>). Tools: list_opportunities, get_store_summary, list_live_missions, create_mission.</p>
    <button class="btn btn-secondary" onclick="mcpTest()">Test: list tools + top opportunities</button><pre class="code" id="mcpout"></pre>
    <h3 class="h3">Embed in BI / comms tools</h3><pre class="code">&lt;iframe src="${location.origin}/embed/store/S001?as=11" width="420" height="320"&gt;&lt;/iframe&gt;</pre><a class="btn btn-ghost" target="_blank" href="/embed/store/${(S.meta.stores[0] || {}).code}?as=${S.user.id}">Open embed preview</a></div>
    <div class="card card-pad stack"><h3 class="h3">Company brain (context graph)</h3><p class="muted">Org structure, KPIs, playbook and live mission state that the AI layer answers from.</p>
    <p>${ctx.regions.length} regions · ${ctx.districts.length} districts · ${ctx.store_count} stores · ${Object.keys(ctx.kpis || {}).length} KPIs</p><pre class="code" style="max-height:320px">${esc(JSON.stringify(ctx, null, 1).slice(0, 4000))}</pre>
    <p class="muted s">LLM: set COLSTORSO_LLM_URL and COLSTORSO_LLM_KEY (OpenAI-compatible) to rephrase answers; without it answers come from the built-in rules engine and always cite their data sources.</p></div></div>`);
};
async function mcpTest() {
  const call = (method, params) => fetch('/mcp', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-User': S.user.id }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) }).then(r => r.json());
  const a = await call('tools/list'), b = await call('tools/call', { name: 'list_opportunities', arguments: { limit: 5 } });
  $('#mcpout').textContent = JSON.stringify({ tools: a.result.tools.map(t => t.name), top: JSON.parse(b.result.content[0].text) }, null, 2);
}

/* ---------- Self-serve onboarding wizard: CSVs -> first missions ---------- */
const OBS = {};
Pages.onboarding = async () => {
  const st = await api('/api/onboarding/status');
  const step = (n, title, done, body) => `<div class="card card-pad stack"><div class="hrow"><span class="chip ${done ? 's-success' : 'kind'}">${done ? icon('check') + ' Done' : 'Step ' + n}</span><h3 class="h3 grow">${title}</h3></div>${body}</div>`;
  const upl = (target, sample, help) => `<p class="muted">${help}</p><div class="hrow"><a class="btn btn-ghost" href="/api/onboarding/sample/${sample}.csv">${icon('database')} Sample file</a>
    <input type="file" accept=".csv,text/csv" id="obf-${target}"><button class="btn btn-secondary" onclick="obPreview('${target}')">Preview & map columns</button></div><div id="obm-${target}"></div>`;
  const blankBody = st.blank || st.stores === 0 ? '' : `<p>You're on the demo workspace (${st.stores} stores). To try ColsTorso on your own files, start a blank workspace. ${S.meta.public_demo ? 'This replaces the shared demo data; "Reset demo data" brings it back.' : ''}</p>`;
  setContent(`<div class="pagehead"><div><h1 class="h1">Get started</h1><p class="lede">From your own CSV files to first missions in under 10 minutes. ${st.elapsed_min != null && st.blank ? `<b>${st.elapsed_min} min</b> so far.` : ''}</p></div></div>
    <div class="stack-lg" style="max-width:860px">
    ${step(1, 'Create your workspace', st.blank || db_onboarded(st), blankBody + `<div class="hrow"><input id="obc" placeholder="Company name" value="${esc(st.company || '')}"><input id="oba" placeholder="Your name"><button class="btn ${st.blank ? 'btn-secondary' : 'btn-primary'}" onclick="obBlank()">${st.blank ? 'Start over' : 'Start a blank workspace'}</button></div>`)}
    ${step(2, 'Upload your stores', st.open_stores > 0, upl('stores', 'stores', 'One row per store: code, name and format (like Superstore / Standard / Express). Optional: district, tags (separate with |). We create a demo login for every store manager.') + (st.stores ? `<p>${st.stores} stores loaded, ${st.open_stores} open.</p>` : ''))}
    ${step(3, 'Upload weekly sales by category', st.sales_weeks >= 2, upl('sales', 'sales', 'Store code, category, sales and a week number or week-start date. Department is optional (new categories are created). Waste is optional. At least 2 weeks; 4+ stores per format works best.') + (st.sales_weeks ? `<p>${st.sales_weeks} week(s) of sales loaded.</p>` : ''))}
    ${step(4, 'Optional: store KPIs (traffic, labor, CSAT)', st.kpi_weeks > 0, upl('store', 'store', 'Adds labor, overtime, conversion and customer-satisfaction missions. Skip it if you only have sales.') + (st.kpi_weeks ? `<p>${st.kpi_weeks} week(s) of store KPIs loaded.</p>` : ''))}
    ${step(5, 'Find my first missions', st.missions > 0, `<p class="muted">Runs the peer-benchmarking engine once over everything you loaded.</p><button class="btn btn-primary" ${st.ready ? '' : 'disabled'} onclick="obRun()">${icon('sparkles')} Find my first missions</button>${st.ready ? '' : ' <span class="muted s">Needs 4+ open stores and 2+ weeks of sales.</span>'}<div id="obr"></div>`)}
    </div>`);
};
const db_onboarded = st => !st.blank && st.stores > 0;
async function obBlank() {
  const ok = await modal('Start a blank workspace?', `<p>This removes the current data${S.meta.public_demo ? ' for everyone using this demo' : ''} and leaves an empty workspace with you as HQ admin.</p>`, [{ label: 'Cancel' }, { label: 'Start blank', primary: true, action: () => post('/api/onboarding/blank', { company: $('#obc').value, admin_name: $('#oba').value }) }]);
  if (!ok) return;
  S.user = await post('/api/login', { user_id: ok.user_id }); localStorage.setItem('ct_user', ok.user_id);
  await loadMeta(); location.hash = '#/onboarding'; route();
}
async function obPreview(target) {
  const f = $('#obf-' + target).files[0]; if (!f) return toast('Choose a CSV file first', true);
  const fd = new FormData(); fd.append('file', f); fd.append('target', target);
  const p = await api('/api/data/preview', { body: fd, method: 'POST' }); OBS[target] = p;
  const fields = [...p.fields.required.map(x => [x, 1]), ...p.fields.optional.map(x => [x, 0])];
  $('#obm-' + target).innerHTML = `<p><b>${esc(p.filename)}</b> · ${p.rows} rows. We matched ${Object.keys(p.suggested).length} column(s) – check them:</p>
    <div class="grid3">${fields.map(([fl, r]) => `<label class="f">${esc(fl)}${r ? ' *' : ''}<select data-f="${fl}"><option value="">— not in file —</option>${p.headers.map(h => `<option ${p.suggested[fl] === h ? 'selected' : ''}>${esc(h)}</option>`).join('')}</select></label>`).join('')}</div>
    <button class="btn btn-primary" onclick="obIngest('${target}')">${icon('check')} Load ${p.rows} rows</button><div id="obi-${target}"></div>`;
}
async function obIngest(target) {
  const mapping = {}; document.querySelectorAll(`#obm-${target} select[data-f]`).forEach(s => mapping[s.dataset.f] = s.value);
  const p = OBS[target];
  const r = await post('/api/data/ingest', { token: p.token, target, mapping, filename: p.filename });
  if (!r.ok) { $('#obi-' + target).innerHTML = `<div class="notice">${esc(r.error)}</div>`; return; }
  if (target === 'stores') await post('/api/onboarding/stores_done');
  const errs = r.issues.filter(i => i.severity === 'error');
  toast(`Loaded ${r.loaded} rows${errs.length ? ` · ${errs.length} row(s) skipped` : ''}`);
  await refreshMeta(); route();
}
async function obRun() {
  const r = await post('/api/onboarding/run');
  await refreshMeta();
  const ms = (await api('/api/missions?status=incoming')).filter(m => m.kind !== 'theme');
  const users = await api('/api/users');
  const sm = users.find(u => u.role === 'store_manager' && ms.length && u.store_id === ms[0].store_id) || users.find(u => u.role === 'store_manager');
  $('#obr').innerHTML = `<div class="notice stack"><b>${r.missions} missions found across ${r.open_stores} stores</b><span>Engine time ${r.engine_ms} ms · ${r.elapsed_min} min since you started.</span>
    <div class="hrow"><a class="btn btn-primary" href="#/missions">See all missions</a>${sm ? `<button class="btn btn-secondary" onclick="login(${sm.id})">See it as ${esc(sm.name)}</button>` : ''}</div></div>`;
}
