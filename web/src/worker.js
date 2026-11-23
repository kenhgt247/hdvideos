// Video Vẽ Tay – Du Học Hải Dương: trang web cho nhân viên.
// Trang web chỉ nhận kịch bản và chuyển lệnh; video được dựng trên GitHub Actions
// và lưu ở mục Releases của repo riêng tư.
import PAGE from './page.html';

const WF = 'render.yml';
const enc = new TextEncoder();

async function sha256(s) {
  const d = await crypto.subtle.digest('SHA-256', enc.encode(s));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...extra },
  });
}

function err(msg, status = 400) { return json({ error: msg }, status); }

function cookieVal(req, name) {
  const c = req.headers.get('cookie') || '';
  const m = c.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? m[1] : null;
}

async function authed(req, env) {
  if (!env.APP_PASSWORD) return false;
  return cookieVal(req, 'hdv') === await sha256(env.APP_PASSWORD + '|hdvideos');
}

async function isAdmin(req, env) {
  if (!env.ADMIN_PASSWORD) return false;
  return cookieVal(req, 'hda') === await sha256(env.ADMIN_PASSWORD + '|hdv-admin');
}

const ADMIN_ONLY = 'Chỉ quản lý mới làm được việc này. Hãy đăng nhập bằng mật khẩu quản lý.';

function gh(env, path, opt = {}) {
  const url = path.startsWith('http') ? path : `https://api.github.com/repos/${env.REPO}${path}`;
  return fetch(url, {
    ...opt,
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`,
      accept: 'application/vnd.github+json',
      'user-agent': 'hdvideos-web',
      'x-github-api-version': '2022-11-28',
      ...(opt.headers || {}),
    },
  });
}

async function ghJson(env, path, opt) {
  const r = await gh(env, path, opt);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.status === 204 ? {} : r.json();
}

function parseInfo(body) {
  try { return JSON.parse(body || '{}'); } catch { return {}; }
}

function slug(s) {
  return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd')
    .toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60);
}

async function putFile(env, path, b64, message) {
  const cur = await ghJson(env, `/contents/${path}`);
  const body = { message, content: b64, branch: 'main' };
  if (cur && cur.sha) body.sha = cur.sha;
  const r = await gh(env, `/contents/${path}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`Không lưu được ảnh (GitHub ${r.status}): ${(await r.text()).slice(0, 200)}`);
}

async function readNames(env, folder) {
  const r = await gh(env, `/contents/engine/assets/${folder}/_danh_sach.json`);
  if (!r.ok) return { data: {}, sha: null };
  const j = await r.json();
  try {
    const txt = new TextDecoder().decode(Uint8Array.from(atob(j.content.replace(/\n/g, '')), c => c.charCodeAt(0)));
    return { data: JSON.parse(txt), sha: j.sha };
  } catch { return { data: {}, sha: j.sha }; }
}

async function saveName(env, folder, file, ten, who) {
  for (let i = 0; i < 3; i++) {
    const { data, sha } = await readNames(env, folder);
    if (ten === null) delete data[file]; else data[file] = { ...(data[file] || {}), ten, ...(who ? { who } : {}) };
    const bytes = new TextEncoder().encode(JSON.stringify(data, null, 1));
    let bin = ''; bytes.forEach(b => { bin += String.fromCharCode(b); });
    const body = { message: `Cập nhật tên ${folder}`, content: btoa(bin), branch: 'main' };
    if (sha) body.sha = sha;
    const r = await gh(env, `/contents/engine/assets/${folder}/_danh_sach.json`, { method: 'PUT', body: JSON.stringify(body) });
    if (r.ok) return;
  }
}

async function saveCredit(env, file, credit) {
  const { data, sha } = await readNames(env, 'nhac');
  data[file] = { ...(data[file] || {}), mo_ta: credit };
  const bytes = new TextEncoder().encode(JSON.stringify(data, null, 1));
  let bin = ''; bytes.forEach(b => { bin += String.fromCharCode(b); });
  const body = { message: 'Ghi nguồn nhạc', content: btoa(bin), branch: 'main' };
  if (sha) body.sha = sha;
  await gh(env, '/contents/engine/assets/nhac/_danh_sach.json', { method: 'PUT', body: JSON.stringify(body) });
}

async function rawFile(env, path, type) {
  const r = await gh(env, `/contents/${path}`, { headers: { accept: 'application/vnd.github.raw' } });
  if (!r.ok) return new Response('Không tìm thấy', { status: 404 });
  return new Response(r.body, {
    headers: { 'content-type': type || r.headers.get('content-type') || 'application/octet-stream', 'cache-control': 'private, max-age=600' },
  });
}

const STEP_VI = {
  'Lay ma nguon': 'Chuẩn bị máy dựng',
  'Cai Python': 'Cài đặt máy dựng',
  'Nho thu vien': 'Nạp thư viện',
  'Nho mo hinh giong doc': 'Nạp giọng đọc',
  'Cai thu vien': 'Cài thư viện giọng đọc',
  'Dung video': 'Đang đọc giọng và vẽ video',
  'Dua video len': 'Đang lưu video',
};

async function jobStatus(env, id) {
  const prev = await ghJson(env, `/releases/tags/prev-${id}`);
  if (prev) {
    const info = parseInfo(prev.body);
    if (!info.ok) return { state: 'error', error: info.error || 'Không xem trước được.', info: strip(info) };
    const imgs = (prev.assets || []).map(a => a.name).filter(n => /^c\d+\.jpg$/.test(n)).sort();
    return { state: 'done', preview: true, info: strip(info), imgs };
  }
  const rel = await ghJson(env, `/releases/tags/job-${id}`);
  if (rel) {
    const info = parseInfo(rel.body);
    const mp4 = (rel.assets || []).find(a => a.name.endsWith('.mp4'));
    if (info.ok && mp4) return { state: 'done', info: strip(info) };
    return { state: 'error', error: info.error || 'Không dựng được video.', info: strip(info) };
  }
  const runs = await ghJson(env, `/actions/workflows/${WF}/runs?per_page=50`);
  const run = (runs && runs.workflow_runs || []).find(r => r.display_title === `job ${id}`);
  if (!run) return { state: 'queued', step: 'Đang gửi lệnh tới máy dựng' };
  if (run.status === 'completed') {
    return { state: 'error', error: run.conclusion === 'cancelled' ? 'Việc dựng đã bị huỷ.' : 'Máy dựng gặp lỗi. Hãy thử lại hoặc báo quản trị.', run: run.html_url };
  }
  let step = run.status === 'queued' ? 'Đang chờ máy dựng trống' : 'Đang chạy';
  const jobs = await ghJson(env, `/actions/runs/${run.id}/jobs`);
  const steps = (jobs && jobs.jobs && jobs.jobs[0] && jobs.jobs[0].steps) || [];
  const cur = steps.find(s => s.status === 'in_progress');
  if (cur) step = STEP_VI[cur.name] || step;
  return { state: run.status === 'queued' ? 'queued' : 'running', step, started: run.run_started_at || run.created_at };
}

function strip(info) {
  const { voices, ...rest } = info || {};
  return rest;
}

async function listVideos(env) {
  const rels = await ghJson(env, '/releases?per_page=60') || [];
  let voices = null;
  const items = [];
  for (const r of rels) {
    if (!r.tag_name.startsWith('job-')) continue;
    const info = parseInfo(r.body);
    if (!voices && Array.isArray(info.voices) && info.voices.length) voices = info.voices;
    items.push({
      id: r.tag_name.slice(4), name: info.name || r.tag_name, created: info.created || Date.parse(r.created_at) / 1000,
      ok: !!info.ok && (r.assets || []).some(a => a.name.endsWith('.mp4')), error: info.error || '',
      voice: info.voice || '', by: info.by || '', fallback: info.fallback || '', script: info.script || '', credit: info.credit || '', posts: info.posts || null,
    });
  }
  return { items, voices: voices || [] };
}

async function videoProxy(req, env, id, dl) {
  // Phát/tải video qua chính trang web (cùng địa chỉ) để iPhone/Android lưu được dễ dàng.
  const rel = await ghJson(env, `/releases/tags/job-${id}`);
  const mp4 = rel && (rel.assets || []).find(a => a.name.endsWith('.mp4'));
  if (!mp4) return new Response('Chưa có video', { status: 404 });
  const r = await gh(env, `/releases/assets/${mp4.id}`, { headers: { accept: 'application/octet-stream' }, redirect: 'manual' });
  const loc = r.headers.get('location');
  const range = req.headers.get('range');
  const src = loc ? await fetch(loc, { headers: range ? { range } : {} }) : r;
  const h = new Headers({ 'content-type': 'video/mp4', 'accept-ranges': 'bytes', 'cache-control': 'private, max-age=86400' });
  for (const k of ['content-length', 'content-range', 'etag', 'last-modified']) {
    const v = src.headers.get(k); if (v) h.set(k, v);
  }
  if (dl) h.set('content-disposition', `attachment; filename="${mp4.name.replace(/[^A-Za-z0-9_.-]/g, '_')}"`);
  return new Response(src.body, { status: src.status === 206 ? 206 : 200, headers: h });
}

const MANIFEST = JSON.stringify({
  name: 'Video Vẽ Tay – Du Học Hải Dương', short_name: 'Video Vẽ Tay', start_url: '/', scope: '/', display: 'standalone',
  background_color: '#f4f6fb', theme_color: '#1f46aa', lang: 'vi',
  icons: [{ src: '/img/logo', sizes: '512x512', type: 'image/png', purpose: 'any' }],
});

async function listDir(env, path) {
  const d = await ghJson(env, `/contents/${path}`);
  return Array.isArray(d) ? d : [];
}

const LOGIN = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đăng nhập – Video Vẽ Tay</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f6fb;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d2433}
form{background:#fff;padding:28px 24px;border-radius:18px;box-shadow:0 8px 30px rgba(20,40,90,.10);width:min(340px,88vw)}
h1{font-size:20px;margin:0 0 4px;color:#1f46aa}p{margin:0 0 18px;color:#667;font-size:14px}
input,button{width:100%;box-sizing:border-box;font-size:17px;padding:13px 14px;border-radius:12px}
input{border:1.5px solid #d5dbe8;margin-bottom:12px}button{border:0;background:#1f46aa;color:#fff;font-weight:600}
.e{color:#d62632;font-size:14px;min-height:18px;margin-top:10px}</style></head><body>
<form id="f"><h1>Video Vẽ Tay</h1><p>Du Học Hải Dương · nhập mật khẩu</p>
<input id="p" type="password" placeholder="Mật khẩu" autocomplete="current-password" autofocus>
<button>Vào</button><div class="e" id="e"></div></form>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();
const r=await fetch('/api/login',{method:'POST',body:JSON.stringify({password:document.getElementById('p').value})});
if(r.ok)location.href='/';else document.getElementById('e').textContent='Sai mật khẩu';}</script></body></html>`;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    try {
      if (p === '/manifest.webmanifest') return new Response(MANIFEST, { headers: { 'content-type': 'application/manifest+json' } });
      if (p === '/img/logo') return rawFile(env, 'engine/assets/logo.png', 'image/png');
      if (p === '/api/login' && req.method === 'POST') {
        const { password } = await req.json().catch(() => ({}));
        const admin = !!env.ADMIN_PASSWORD && password === env.ADMIN_PASSWORD;
        if (!env.APP_PASSWORD || (!admin && password !== env.APP_PASSWORD)) return err('Sai mật khẩu', 401);
        const opt = `Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${60 * 86400}`;
        const h = new Headers({ 'content-type': 'application/json' });
        h.append('set-cookie', `hdv=${await sha256(env.APP_PASSWORD + '|hdvideos')}; ${opt}`);
        h.append('set-cookie', admin ? `hda=${await sha256(env.ADMIN_PASSWORD + '|hdv-admin')}; ${opt}` : 'hda=; Path=/; Max-Age=0');
        return new Response(JSON.stringify({ ok: true, admin }), { headers: h });
      }
      if (!(await authed(req, env))) {
        if (p.startsWith('/api/')) return err('Chưa đăng nhập', 401);
        return new Response(LOGIN, { headers: { 'content-type': 'text/html; charset=utf-8' } });
      }
      if (!env.GH_TOKEN) return err('Chưa cài mã GH_PAT cho trang web', 500);

      if (p === '/' || p === '/index.html') {
        return new Response(PAGE, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
      }
      if (p === '/api/logout') {
        const h = new Headers({ 'content-type': 'application/json' });
        h.append('set-cookie', 'hdv=; Path=/; Max-Age=0');
        h.append('set-cookie', 'hda=; Path=/; Max-Age=0');
        return new Response('{"ok":true}', { headers: h });
      }
      const admin = await isAdmin(req, env);
      if (p === '/api/me') return json({ admin });
      const needAdmin = /^\/api\/(jobs\/[a-z0-9]+\/delete|kho\/[^/]+\/delete|logo)$/.test(p) && req.method === 'POST';
      if (needAdmin && !admin) return err(ADMIN_ONLY, 403);

      // ---- tạo video
      if (p === '/api/jobs' && req.method === 'POST') {
        const b = await req.json();
        const script = (b.script || '').trim();
        if (script.length < 5) return err('Kịch bản đang trống');
        if (script.length > 20000) return err('Kịch bản quá dài');
        const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
        const job = {
          name: (b.name || '').slice(0, 80), script, voice: b.voice || 'vieneu_nam', vieneu_voice: b.vieneu_voice || '',
          character: b.character || 'auto', label: (b.label || '').slice(0, 30), hotline: (b.hotline || '').slice(0, 40),
          auto: b.auto !== false, logo: b.logo !== false, rate: Math.max(-30, Math.min(30, parseInt(b.rate || 0, 10) || 0)),
          by: (b.by || '').slice(0, 40),
          who: slug(b.by || ''),
          pen: Math.max(0, Math.min(3, Number(b.pen ?? 1) || 0)),
          bg: /^[a-z_]{2,20}$/.test(b.bg || '') ? b.bg : 'trang',
          fmt: ['doc', 'ngang', 'vuong', 'doc45'].includes(b.fmt) ? b.fmt : 'doc',
          subs: !!b.subs,
          preview: !!b.preview,
          music: /^[a-z0-9_]+\.(mp3|m4a|aac|wav|ogg)$/.test(b.music || '') ? b.music : '',
          music_vol: Math.max(0, Math.min(40, parseInt(b.music_vol || 12, 10) || 12)),
          clone: /^[a-z0-9_]+\.(mp3|m4a|aac|wav|ogg|webm|mp4)$/.test(b.clone || '') ? b.clone : '',
        };
        const r = await gh(env, `/actions/workflows/${WF}/dispatches`, {
          method: 'POST', body: JSON.stringify({ ref: 'main', inputs: { job_id: id, job: JSON.stringify(job) } }),
        });
        if (!r.ok) return err(`Không gửi được lệnh dựng (GitHub ${r.status}): ${(await r.text()).slice(0, 200)}`, 502);
        return json({ id });
      }
      let m = p.match(/^\/api\/jobs\/([a-z0-9]+)$/);
      if (m) return json(await jobStatus(env, m[1]));
      if (p === '/api/list') return json(await listVideos(env));
      m = p.match(/^\/video\/([a-z0-9]+)$/);
      if (m) return videoProxy(req, env, m[1], url.searchParams.get('dl') === '1');
      m = p.match(/^\/prev\/([a-z0-9]+)\/(c\d+\.jpg)$/);
      if (m) {
        const rel = await ghJson(env, `/releases/tags/prev-${m[1]}`);
        const a = rel && (rel.assets || []).find(x => x.name === m[2]);
        if (!a) return new Response('Không có', { status: 404 });
        const r = await gh(env, `/releases/assets/${a.id}`, { headers: { accept: 'application/octet-stream' } });
        return new Response(r.body, { headers: { 'content-type': 'image/jpeg', 'cache-control': 'private, max-age=86400' } });
      }
      m = p.match(/^\/img\/nen\/([a-z_]+)\.jpg$/);
      if (m) return rawFile(env, `engine/assets/nen/${m[1]}.jpg`, 'image/jpeg');
      m = p.match(/^\/api\/jobs\/([a-z0-9]+)\/delete$/);
      if (m && req.method === 'POST') {
        const rel = await ghJson(env, `/releases/tags/job-${m[1]}`);
        if (rel) {
          await gh(env, `/releases/${rel.id}`, { method: 'DELETE' });
          await gh(env, `/git/refs/tags/job-${m[1]}`, { method: 'DELETE' });
        }
        return json({ ok: true });
      }

      // ---- kho hình
      if (p === '/api/kho' && req.method === 'GET') {
        const [kho, moi] = await Promise.all([listDir(env, 'engine/assets/kho'), listDir(env, 'engine/assets/kho_moi')]);
        return json({
          items: kho.filter(f => f.name.endsWith('.png') && !f.name.startsWith('_')).map(f => ({ file: f.name, name: f.name.slice(0, -4).replace(/_/g, ' ') })),
          pending: moi.filter(f => !f.name.startsWith('.')).map(f => f.name),
        });
      }
      if (p === '/api/kho' && req.method === 'POST') {
        const b = await req.json();
        const name = slug(b.name);
        if (!name) return err('Hãy đặt tên ảnh (ví dụ: ký túc xá)');
        if (!b.data) return err('Thiếu ảnh');
        await putFile(env, `engine/assets/kho_moi/${name}.png`, b.data, `Kho: thêm ${name}`);
        return json({ ok: true, name });
      }
      m = p.match(/^\/api\/kho\/([a-z0-9_]+\.png)\/delete$/);
      if (m && req.method === 'POST') {
        const cur = await ghJson(env, `/contents/engine/assets/kho/${m[1]}`);
        if (cur) await gh(env, `/contents/engine/assets/kho/${m[1]}`, { method: 'DELETE', body: JSON.stringify({ message: `Kho: xoá ${m[1]}`, sha: cur.sha, branch: 'main' }) });
        return json({ ok: true });
      }
      m = p.match(/^\/img\/kho\/([a-z0-9_]+\.png)$/);
      if (m) return rawFile(env, `engine/assets/kho/${m[1]}`, 'image/png');

      // ---- nhạc nền, giọng mẫu (nhân bản)
      if (p === '/api/media' && req.method === 'GET') {
        const [nhac, giong, nn, gn] = await Promise.all([listDir(env, 'engine/assets/nhac'), listDir(env, 'engine/assets/giong'),
          readNames(env, 'nhac'), readNames(env, 'giong')]);
        const pick = (arr, names) => arr.filter(f => !/^[._]/.test(f.name)).map(f => {
          const m = names[f.name] || {};
          return { file: f.name, name: m.ten || f.name.replace(/\.[^.]+$/, '').replace(/_/g, ' '), desc: m.mo_ta || '', builtin: !!m.san, who: m.who || '', size: f.size };
        }).sort((a, b) => (b.builtin - a.builtin) || a.name.localeCompare(b.name, 'vi'));
        return json({ nhac: pick(nhac, nn.data), giong: pick(giong, gn.data) });
      }
      m = p.match(/^\/api\/(nhac|giong)$/);
      if (m && req.method === 'POST') {
        const b = await req.json();
        const name = slug(b.name);
        const ext = String(b.ext || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        if (!name) return err('Hãy đặt tên');
        if (!['mp3', 'm4a', 'aac', 'wav', 'ogg', 'webm', 'mp4'].includes(ext)) return err('Định dạng âm thanh không hỗ trợ');
        if (!b.data || b.data.length > 20e6) return err('File trống hoặc quá lớn (tối đa khoảng 14MB)');
        await putFile(env, `engine/assets/${m[1]}/${name}.${ext}`, b.data, `${m[1] === 'nhac' ? 'Nhạc nền' : 'Giọng mẫu'}: thêm ${name}`);
        await saveName(env, m[1], `${name}.${ext}`, String(b.name).trim().slice(0, 60), slug(b.who || ''));
        return json({ ok: true, file: `${name}.${ext}` });
      }
      if (p === '/api/timnhac') {
        const q = (url.searchParams.get('q') || 'background').slice(0, 60);
        const lic = 'cc0,pdm,by';
        const api = `https://api.openverse.org/v1/audio/?q=${encodeURIComponent(q)}&license=${lic}&category=music&page_size=20&mature=false`;
        const r = await fetch(api, { headers: { 'user-agent': 'hdvideos/1.0 (Du Hoc Hai Duong)', accept: 'application/json' } });
        if (!r.ok) return err(`Kho nhạc Openverse đang bận (lỗi ${r.status}), thử lại sau`, 502);
        const d = await r.json();
        const items = (d.results || []).filter(x => x.url && (!x.duration || (x.duration >= 30000 && x.duration <= 420000)))
          .map(x => ({
            title: (x.title || 'Không tên').slice(0, 70), creator: x.creator || '', url: x.url, dur: Math.round((x.duration || 0) / 1000),
            license: (x.license || '').toUpperCase(), source: x.source || x.provider || '', page: x.foreign_landing_url || '',
            attr: x.attribution || '',
          }));
        return json({ items });
      }
      if (p === '/api/nhac/link' && req.method === 'POST') {
        const b = await req.json();
        const name = slug(b.name);
        if (!name) return err('Hãy đặt tên nhạc');
        let u;
        try { u = new URL(String(b.url || '').trim()); } catch { return err('Link không hợp lệ'); }
        if (!/^https?:$/.test(u.protocol)) return err('Link phải bắt đầu bằng http hoặc https');
        const r = await fetch(u.toString(), { redirect: 'follow', headers: { 'user-agent': 'Mozilla/5.0 hdvideos' } });
        if (!r.ok) return err(`Không tải được nhạc từ link (lỗi ${r.status})`);
        const ct = (r.headers.get('content-type') || '').toLowerCase();
        if (ct.includes('text/html')) return err('Link này là trang web, không phải file nhạc. Hãy dùng link tải trực tiếp (thường kết thúc bằng .mp3)');
        const buf = new Uint8Array(await r.arrayBuffer());
        if (buf.length < 10000) return err('File nhạc quá nhỏ hoặc không đúng');
        if (buf.length > 14e6) return err('File nhạc quá lớn (tối đa 14MB)');
        let ext = (u.pathname.match(/\.(mp3|m4a|aac|wav|ogg)$/i) || [])[1];
        ext = (ext || (ct.includes('mp4') || ct.includes('m4a') ? 'm4a' : ct.includes('wav') ? 'wav' : ct.includes('ogg') ? 'ogg' : 'mp3')).toLowerCase();
        let bin = '';
        for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
        await putFile(env, `engine/assets/nhac/${name}.${ext}`, btoa(bin), `Nhạc nền: thêm ${name} từ link`);
        await saveName(env, 'nhac', `${name}.${ext}`, String(b.name).trim().slice(0, 60), slug(b.who || ''));
        if (b.credit) await saveCredit(env, `${name}.${ext}`, String(b.credit).slice(0, 300));
        return json({ ok: true, file: `${name}.${ext}` });
      }
      m = p.match(/^\/api\/(nhac|giong)\/([a-z0-9_]+\.[a-z0-9]+)\/delete$/);
      if (m && req.method === 'POST') {
        const path = `engine/assets/${m[1]}/${m[2]}`;
        const bb = await req.json().catch(() => ({}));
        const owner = ((await readNames(env, m[1])).data[m[2]] || {}).who || '';
        if (!admin && !(owner && owner === slug(bb.who || ''))) return err('Bạn chỉ xoá được giọng/nhạc do chính bạn tải lên. Muốn xoá cái khác hãy nhờ quản lý.', 403);
        const cur = await ghJson(env, `/contents/${path}`);
        if (cur) await gh(env, `/contents/${path}`, { method: 'DELETE', body: JSON.stringify({ message: `Xoá ${m[2]}`, sha: cur.sha, branch: 'main' }) });
        await saveName(env, m[1], m[2], null);
        return json({ ok: true });
      }
      m = p.match(/^\/media\/(nhac|giong)\/([a-z0-9_]+)\.([a-z0-9]+)$/);
      if (m) {
        const types = { mp3: 'audio/mpeg', m4a: 'audio/mp4', mp4: 'audio/mp4', aac: 'audio/aac', wav: 'audio/wav', ogg: 'audio/ogg', webm: 'audio/webm' };
        return rawFile(env, `engine/assets/${m[1]}/${m[2]}.${m[3]}`, types[m[3]] || 'application/octet-stream');
      }

      // ---- nhân vật, logo
      const NVF = /^(anh|chi)_(chao|chi|like)\.png$/;
      m = p.match(/^\/img\/nv\/((anh|chi)_(chao|chi|like)\.png)$/);
      if (m) {
        const who = slug(url.searchParams.get('who') || '');
        if (who) {
          const r = await gh(env, `/contents/engine/assets/nhanvat_rieng/${who}/${m[1]}`, { headers: { accept: 'application/vnd.github.raw' } });
          if (r.ok) return new Response(r.body, { headers: { 'content-type': 'image/png', 'cache-control': 'no-store' } });
        }
        return rawFile(env, `engine/assets/nhanvat/${m[1]}`, 'image/png');
      }
      if (p === '/img/logo') return rawFile(env, 'engine/assets/logo.png', 'image/png');
      if (p === '/api/nhanvat' && req.method === 'GET') {
        const who = slug(url.searchParams.get('who') || '');
        const mine = who ? (await listDir(env, `engine/assets/nhanvat_rieng/${who}`)).map(f => f.name).filter(n => NVF.test(n)) : [];
        const pending = (await listDir(env, 'engine/assets/nhanvat_moi')).map(f => f.name).filter(n => !n.startsWith('.'));
        return json({ mine, pending: pending.filter(n => who ? n.startsWith(who + '__') : !n.includes('__')) });
      }
      if (p === '/api/nhanvat' && req.method === 'POST') {
        const b = await req.json();
        if (!['anh', 'chi'].includes(b.gender) || !['chao', 'chi', 'like'].includes(b.pose) || !b.data) return err('Thiếu thông tin');
        if (b.scope === 'chung') {
          if (!admin) return err(ADMIN_ONLY, 403);
          await putFile(env, `engine/assets/nhanvat_moi/${b.gender}_${b.pose}.png`, b.data, `Nhân vật chung: thay ${b.gender}_${b.pose}`);
        } else {
          const who = slug(b.who || '');
          if (!who) return err('Hãy nhập tên của bạn ở ô "Người tạo" (tab Tạo video) trước');
          await putFile(env, `engine/assets/nhanvat_moi/${who}__${b.gender}_${b.pose}.png`, b.data, `Nhân vật của ${who}: thay ${b.gender}_${b.pose}`);
        }
        return json({ ok: true });
      }
      if (p === '/api/nhanvat/restore' && req.method === 'POST') {
        const b = await req.json().catch(() => ({}));
        if (b.scope === 'chung') {
          if (!admin) return err(ADMIN_ONLY, 403);
          await putFile(env, 'engine/assets/nhanvat_moi/_khoi_phuc', btoa('1'), 'Nhân vật chung: khôi phục gốc');
          return json({ ok: true });
        }
        const who = slug(b.who || '');
        if (!who) return err('Thiếu tên');
        for (const f of await listDir(env, `engine/assets/nhanvat_rieng/${who}`)) {
          await gh(env, `/contents/${f.path}`, { method: 'DELETE', body: JSON.stringify({ message: `Nhân vật của ${who}: về bộ chung`, sha: f.sha, branch: 'main' }) });
        }
        return json({ ok: true });
      }
      if (p === '/api/logo' && req.method === 'POST') {
        const b = await req.json();
        if (!b.data) return err('Thiếu ảnh');
        await putFile(env, 'engine/assets/logo.png', b.data, 'Đổi logo');
        return json({ ok: true });
      }
      if (p === '/api/text') {
        const f = { chatgpt: 'engine/LENH_CHATGPT.txt', anh: 'engine/KHO_HINH_CAU_LENH.txt', luoi: 'engine/KHO_HINH_LUOI.txt' }[url.searchParams.get('f')];
        if (!f) return err('Không có');
        if (url.searchParams.get('f') === 'chatgpt') {
          const [txt, kho] = await Promise.all([
            gh(env, `/contents/${f}`, { headers: { accept: 'application/vnd.github.raw' } }).then(r => r.text()),
            listDir(env, 'engine/assets/kho'),
          ]);
          const names = kho.filter(x => x.name.endsWith('.png') && !x.name.startsWith('_')).map(x => x.name.slice(0, -4).replace(/_/g, ' '));
          const extra = names.length ? `\n\nẢNH TRONG KHO (ưu tiên dùng, viết có dấu cũng được, ví dụ [vẽ: hồ sơ du học]):\n${names.join(', ')}\n` : '';
          return new Response(txt.replace(/^\uFEFF/, '') + extra, { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
        }
        return rawFile(env, f, 'text/plain; charset=utf-8');
      }
      return new Response('Không tìm thấy', { status: 404 });
    } catch (e) {
      return err(String(e && e.message || e), 500);
    }
  },
};
