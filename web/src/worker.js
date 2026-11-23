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
      voice: info.voice || '', by: info.by || '', fallback: info.fallback || '', script: info.script || '',
    });
  }
  return { items, voices: voices || [] };
}

async function videoRedirect(env, id) {
  const rel = await ghJson(env, `/releases/tags/job-${id}`);
  const mp4 = rel && (rel.assets || []).find(a => a.name.endsWith('.mp4'));
  if (!mp4) return new Response('Chưa có video', { status: 404 });
  const r = await gh(env, `/releases/assets/${mp4.id}`, { headers: { accept: 'application/octet-stream' }, redirect: 'manual' });
  const loc = r.headers.get('location');
  if (loc) return Response.redirect(loc, 302);
  return new Response(r.body, { headers: { 'content-type': 'video/mp4' } });
}

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
      if (p === '/api/login' && req.method === 'POST') {
        const { password } = await req.json().catch(() => ({}));
        if (!env.APP_PASSWORD || password !== env.APP_PASSWORD) return err('Sai mật khẩu', 401);
        const tok = await sha256(env.APP_PASSWORD + '|hdvideos');
        return json({ ok: true }, 200, { 'set-cookie': `hdv=${tok}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${60 * 86400}` });
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
        return json({ ok: true }, 200, { 'set-cookie': 'hdv=; Path=/; Max-Age=0' });
      }

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
      if (m) return videoRedirect(env, m[1]);
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

      // ---- nhân vật, logo
      m = p.match(/^\/img\/nv\/((anh|chi)_(chao|chi|like)\.png)$/);
      if (m) return rawFile(env, `engine/assets/nhanvat/${m[1]}`, 'image/png');
      if (p === '/img/logo') return rawFile(env, 'engine/assets/logo.png', 'image/png');
      if (p === '/api/nhanvat' && req.method === 'POST') {
        const b = await req.json();
        if (!['anh', 'chi'].includes(b.gender) || !['chao', 'chi', 'like'].includes(b.pose) || !b.data) return err('Thiếu thông tin');
        await putFile(env, `engine/assets/nhanvat_moi/${b.gender}_${b.pose}.png`, b.data, `Nhân vật: thay ${b.gender}_${b.pose}`);
        return json({ ok: true });
      }
      if (p === '/api/nhanvat/restore' && req.method === 'POST') {
        await putFile(env, 'engine/assets/nhanvat_moi/_khoi_phuc', btoa('1'), 'Nhân vật: khôi phục gốc');
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
        return rawFile(env, f, 'text/plain; charset=utf-8');
      }
      return new Response('Không tìm thấy', { status: 404 });
    } catch (e) {
      return err(String(e && e.message || e), 500);
    }
  },
};
