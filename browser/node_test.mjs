// Headless check of the browser runtime in Node: loads Pyodide, mounts the app, exercises the core loop through ASGI.
import { loadPyodide } from "/workspace/bin/pyo/node_modules/pyodide/pyodide.mjs";
import fs from "fs"; import zlib from "zlib";
const t0 = Date.now();
const py = await loadPyodide();
await py.loadPackage(["fastapi"]);
await py.loadPackage("micropip"); const mp = py.pyimport("micropip");
await mp.install(fs.existsSync("/workspace/colstorso/dist/browser/py/python_multipart-0.0.32-py3-none-any.whl") ? "emfs:/wheels/pm.whl" : "python-multipart==0.0.32");
console.log("pyodide+deps", Date.now() - t0, "ms");
const src = "/workspace/colstorso/colstorso";
py.FS.mkdirTree("/app/colstorso");
for (const f of fs.readdirSync(src)) if (f.endsWith(".py")) py.FS.writeFile("/app/colstorso/" + f, fs.readFileSync(src + "/" + f));
py.FS.mkdirTree("/data");
py.FS.writeFile("/data/colstorso.db", zlib.gunzipSync(fs.readFileSync("/workspace/colstorso/dist/browser/demo.db.gz")));
py.FS.writeFile("/app/ct_browser.py", fs.readFileSync("/workspace/colstorso/browser/ct_browser.py"));
await py.runPythonAsync("import sys; sys.path.insert(0,'/app'); import ct_browser; ct_browser.stamp_fresh()");
const handle = py.pyimport("ct_browser").handle;
async function call(method, path, body, uid = 1, ctype = "application/json") {
  const hdr = [["x-user", String(uid)], ["content-type", ctype]];
  const r = await handle(method, path, hdr, body ? new TextEncoder().encode(typeof body === "string" ? body : JSON.stringify(body)) : null);
  const [st, h, b] = r.toJs(); r.destroy();
  return [st, new TextDecoder().decode(b)];
}
console.log("boot", Date.now() - t0, "ms");
console.log(await call("GET", "/api/health"));
const users = JSON.parse((await call("GET", "/api/users"))[1]); const sm = users.find(u => u.role === "store_manager");
let [s, b] = await call("GET", "/api/missions?status=incoming", null, sm.id); const inbox = JSON.parse(b).filter(m => m.kind !== "theme");
console.log("inbox", s, inbox.length, inbox.map(m => m.label));
[s, b] = await call("POST", `/api/missions/${inbox[0].id}/quick`, { action: "accept" }, sm.id); console.log("accept", s, JSON.parse(b).label);
[s, b] = await call("POST", `/api/missions/${inbox[1].id}/quick`, { action: "not_for_us", reason: "Stock not delivered" }, sm.id); console.log("nfu", s, JSON.parse(b).label);
[s, b] = await call("GET", "/api/pushback", null, 1); console.log("pushback", s, JSON.parse(b).total);
[s, b] = await call("POST", "/api/ai/ask", { q: "What should I focus on this week?" }, sm.id); console.log("ask", s, JSON.parse(b).sources);
[s, b] = await call("GET", "/api/impact", null, 1); console.log("impact", s, b.slice(0, 80));
const boundary = "----ctb"; const csv = "Store,Sub Category,Net Sales,Date\nS001,Snacks,1000,2026-10-12\n";
const mp_ = `--${boundary}\r\nContent-Disposition: form-data; name="target"\r\n\r\nsales\r\n--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\nContent-Type: text/csv\r\n\r\n${csv}\r\n--${boundary}--\r\n`;
[s, b] = await call("POST", "/api/data/preview", mp_, 1, `multipart/form-data; boundary=${boundary}`); console.log("preview", s, b.slice(0, 120));
let t1 = Date.now(); [s, b] = await call("POST", "/api/admin/next_week", {}, 1); console.log("next_week", s, b.slice(0, 100), Date.now() - t1, "ms");
t1 = Date.now(); [s, b] = await call("POST", "/api/admin/reset", {}, 1); console.log("reset", s, b, Date.now() - t1, "ms");
const snap = py.pyimport("ct_browser").snapshot(); console.log("snapshot bytes", snap.toJs().length);
