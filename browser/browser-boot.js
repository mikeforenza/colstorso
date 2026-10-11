/* ColsTorso browser runtime: boots the real Python app in Pyodide and serves /api/* from it. Data persists in IndexedDB. */
(() => {
  const BASE = new URL('.', document.baseURI);
  const DBKEY = 'colstorso-db-v1';
  const nativeFetch = window.fetch.bind(window);
  const idb = (mode, fn) => new Promise((res, rej) => {
    const o = indexedDB.open('colstorso', 1);
    o.onupgradeneeded = () => o.result.createObjectStore('kv');
    o.onsuccess = () => { const tx = o.result.transaction('kv', mode); const r = fn(tx.objectStore('kv')); tx.oncomplete = () => res(r && r.result); tx.onerror = () => rej(tx.error); };
    o.onerror = () => rej(o.error);
  });
  const overlay = document.createElement('div');
  overlay.id = 'ct-boot';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:var(--ct-color-surface-canvas,#F8F9FB);font:16px Inter,system-ui,sans-serif;color:var(--ct-color-text-secondary,#4C5466)';
  overlay.innerHTML = '<div style="max-width:420px;text-align:center"><img src="design/logo.svg" alt="ColsTorso" style="height:36px"><p id="ct-boot-msg" style="margin-top:16px">Starting the ColsTorso engine in your browser…</p><p style="font-size:13px;opacity:.8">First visit downloads ~15 MB (Python + engine), then it is cached. Everything runs on this device; demo data only.</p></div>';
  const msg = t => { const el = document.getElementById('ct-boot-msg'); if (el) el.textContent = t; };
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(overlay));
  let py, handle, snapshot, saveTimer;
  const ready = (async () => {
    py = await loadPyodide({ indexURL: window.CT_PYODIDE });
    msg('Loading web framework…');
    await py.loadPackage(['fastapi', 'micropip']);
    const whl = new Uint8Array(await (await nativeFetch(new URL('python_multipart-0.0.32-py3-none-any.whl', BASE))).arrayBuffer());
    py.FS.writeFile('/tmp/python_multipart-0.0.32-py3-none-any.whl', whl);
    await py.pyimport('micropip').install('emfs:/tmp/python_multipart-0.0.32-py3-none-any.whl');
    msg('Loading mission engine…');
    const zip = new Uint8Array(await (await nativeFetch(new URL('app.zip', BASE))).arrayBuffer());
    py.FS.mkdirTree('/app'); py.FS.writeFile('/tmp/app.zip', zip);
    await py.runPythonAsync("import zipfile; zipfile.ZipFile('/tmp/app.zip').extractall('/app')");
    py.FS.mkdirTree('/data');
    let saved = null; try { saved = await idb('readonly', s => s.get(DBKEY)); } catch (e) { console.warn('IndexedDB unavailable', e); }
    let fresh = false;
    if (saved) { py.FS.writeFile('/data/colstorso.db', new Uint8Array(saved)); }
    else {
      msg('Unpacking demo data (50 stores, 52 weeks)…');
      const gz = await nativeFetch(new URL('demo.db.gz', BASE));
      const raw = new Uint8Array(await new Response(gz.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
      py.FS.writeFile('/data/colstorso.db', raw); fresh = true;
    }
    await py.runPythonAsync("import sys; sys.path.insert(0, '/app'); import ct_browser");
    const mod = py.pyimport('ct_browser'); handle = mod.handle; snapshot = mod.snapshot;
    if (fresh) { mod.stamp_fresh(); await persist(); }
    overlay.remove();
  })().catch(e => { msg('Could not start: ' + e); console.error(e); throw e; });
  async function persist() {
    const p = snapshot(); const bytes = p.toJs(); p.destroy && p.destroy();
    try { await idb('readwrite', s => s.put(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), DBKEY)); } catch (e) { console.warn('persist failed', e); }
  }
  const isApp = u => u.origin === location.origin && /^\/(?:.*\/)?(api\/|mcp$|embed\/)/.test(u.pathname) && !/\.(whl|zip|gz)$/.test(u.pathname);
  const appPath = u => u.pathname.slice(u.pathname.search(/\/(api\/|mcp$|embed\/)/)) + u.search;
  async function appFetch(input, init) {
    await ready;
    const req = new Request(input, init);
    const u = new URL(req.url);
    const body = ['GET', 'HEAD'].includes(req.method) ? null : new Uint8Array(await req.arrayBuffer());
    const hdrs = []; req.headers.forEach((v, k) => hdrs.push([k, v]));
    if (!req.headers.has('x-user')) { const id = localStorage.getItem('ct_user'); if (id) hdrs.push(['x-user', id]); }
    const r = await handle(req.method, appPath(u), hdrs, body);
    const [status, headers, bytes] = r.toJs(); r.destroy && r.destroy();
    if (!['GET', 'HEAD'].includes(req.method) && status < 400) { clearTimeout(saveTimer); saveTimer = setTimeout(persist, 300); }
    const h = new Headers(); for (const [k, v] of headers) { try { h.append(k, v); } catch (e) {} }
    return new Response([204, 304].includes(status) ? null : bytes, { status, headers: h });
  }
  window.fetch = (input, init) => {
    const u = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
    return isApp(u) ? appFetch(input, init) : nativeFetch(input, init);
  };
  // downloads and the embed preview are plain links: serve them from the in-browser app too
  document.addEventListener('click', async ev => {
    const a = ev.target.closest && ev.target.closest('a[href]'); if (!a) return;
    const u = new URL(a.getAttribute('href'), location.href); if (!isApp(u)) return;
    ev.preventDefault();
    const r = await window.fetch(u.href); const blob = await r.blob(); const url = URL.createObjectURL(blob);
    if (u.pathname.includes('/embed/')) { window.open(url, '_blank'); return; }
    const cd = r.headers.get('content-disposition') || ''; const name = (cd.match(/filename="?([^";]+)/) || [])[1] || u.pathname.split('/').pop();
    const dl = document.createElement('a'); dl.href = url; dl.download = name; document.body.appendChild(dl); dl.click(); dl.remove();
  }, true);
  window.CT_BROWSER = { ready, persist, wipe: () => idb('readwrite', s => s.delete(DBKEY)) };
})();
