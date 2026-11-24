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

const STATS = 'thongke/videos.json';
async function readJson(env, path) {
  const r = await gh(env, `/contents/${path}`);
  if (!r.ok) return { data: {}, sha: null };
  const j = await r.json();
  try {
    const txt = new TextDecoder().decode(Uint8Array.from(atob(j.content.replace(/\n/g, '')), c => c.charCodeAt(0)));
    return { data: JSON.parse(txt), sha: j.sha };
  } catch { return { data: {}, sha: j.sha }; }
}
async function saveStats(env, id, rec) {
  for (let i = 0; i < 3; i++) {
    const { data, sha } = await readJson(env, STATS);
    if (rec === null) delete data[id]; else data[id] = rec;
    const bytes = new TextEncoder().encode(JSON.stringify(data, null, 1));
    let bin = ''; bytes.forEach(b => { bin += String.fromCharCode(b); });
    const body = { message: 'Cập nhật lượt xem', content: btoa(bin), branch: 'main' };
    if (sha) body.sha = sha;
    const r = await gh(env, `/contents/${STATS}`, { method: 'PUT', body: JSON.stringify(body) });
    if (r.ok) return true;
  }
  return false;
}


// ===================== AI VIẾT KỊCH BẢN =====================
// Gemini/Claude chặn yêu cầu từ vài nơi (vd máy chủ Hồng Kông gần Việt Nam) -> gọi qua Durable Object đặt ở Mỹ
export class AiProxy {
  constructor(state, env) { this.state = state; this.env = env; }
  async fetch(req) {
    const { url, headers, body } = await req.json();
    if (!/^https:\/\/(generativelanguage\.googleapis\.com|api\.anthropic\.com)\//.test(url)) return new Response('bad', { status: 400 });
    const h = { ...headers };
    if (url.includes('googleapis')) h['x-goog-api-key'] = this.env.GEMINI_KEY;
    else h['x-api-key'] = this.env.CLAUDE_KEY;
    const r = await fetch(url, { method: 'POST', headers: h, body });
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json' } });
  }
}
let _ENV = null;
async function aiFetch(url, init) {
  const env = _ENV;
  if (env && env.AIPROXY) {
    const hint = (env.AI_REGION || 'wnam');
    const stub = env.AIPROXY.get(env.AIPROXY.idFromName('ai-' + hint), { locationHint: hint });
    const headers = { ...(init.headers || {}) };
    delete headers['x-goog-api-key']; delete headers['x-api-key'];
    return stub.fetch('https://proxy/', { method: 'POST', body: JSON.stringify({ url, headers, body: init.body }) });
  }
  return fetch(url, init);
}
const AI_FILE = 'thongke/ai.json';
const AI_DEF = { free: 20, paid: 5, paid_staff: true };
const OFFICIAL = ['roc-taiwan.org', 'studyintaiwan.org', 'edu.tw', 'gov.tw', 'go.kr', 'ac.kr', 'gov.vn', 'mofa.go.kr'];
async function chatgptPrompt(env) {
  const [txt, kho] = await Promise.all([
    gh(env, '/contents/engine/LENH_CHATGPT.txt', { headers: { accept: 'application/vnd.github.raw' } }).then(r => r.text()),
    listDir(env, 'engine/assets/kho'),
  ]);
  const names = kho.filter(x => x.name.endsWith('.png') && !x.name.startsWith('_')).map(x => x.name.slice(0, -4).replace(/_/g, ' '));
  const extra = names.length ? `\n\nẢNH TRONG KHO (ưu tiên dùng, viết có dấu cũng được, ví dụ [vẽ: hồ sơ du học]):\n${names.join(', ')}\n` : '';
  return txt.replace(/^﻿/, '') + extra;
}
const AI_COMMON = `

====================================================
CHẾ ĐỘ TỰ ĐỘNG (QUAN TRỌNG NHẤT, ĐÈ LÊN MỌI DÒNG Ở TRÊN)
====================================================
Bạn đang được phần mềm gọi tự động, không có người chat với bạn.
- KHÔNG trả lời "Sẵn sàng". Viết NGAY kịch bản cho CHỦ ĐỀ trong tin nhắn.
- Trả lời đúng 3 phần của PHẦN C: (1) MỘT khối \`\`\` chỉ chứa kịch bản, (2) CAPTION, (3) NGUỒN.
- Mỗi video 1 điểm kiến thức, 8–12 dòng cảnh, lời đọc tổng khoảng 60–100 chữ.
- Nếu THÔNG TIN THÊM có số liệu của trung tâm thì dùng đúng, không sửa.`;
const AI_LENGTHS = Object.freeze({
  quick: '30–60 giây, khoảng 65–140 chữ lời đọc, một điểm kiến thức',
  short: '1–3 phút, khoảng 140–420 chữ lời đọc, giải thích có ví dụ',
  medium: '3–10 phút, khoảng 420–1400 chữ lời đọc, phân tích nhiều khía cạnh',
  long: '10–15 phút, khoảng 1400–2100 chữ lời đọc, bài giảng hoặc chuyên đề có trình tự',
});
const AI_CONVERT_TIMED = `
- CHUYỂN bài viết thành kịch bản theo thời lượng người dùng đã chọn. Được biên tập, chọn lọc ý chính để phù hợp với thời lượng; giữ đúng các số liệu, điều kiện và lời khuyên thiết yếu, không thêm hoặc bịa thông tin.
- Nếu bài gốc ngắn hơn thời lượng mong muốn, không lặp ý hoặc tự thêm dữ kiện để kéo dài.
- Viết chữ màn hình ngắn, lời đọc tự nhiên; tách cảnh dài thành nhiều cảnh. Chữ Trung/Hàn chuyển sang phiên âm và giải nghĩa tiếng Việt.
- Phần NGUỒN ghi "Nội dung do người dùng cung cấp".`;
const AI_FREE = `
- Bạn KHÔNG có công cụ tra web. TUYỆT ĐỐI không viết con số, mức phí, mốc thời gian, số tháng, điều kiện visa, quy định cụ thể nào (trừ khi có trong THÔNG TIN THÊM). Chỉ chia sẻ kinh nghiệm và kiến thức chung, ví dụ "tùy trường", "xem thông báo mới nhất".
- Phần NGUỒN ghi đúng: "Chưa kiểm chứng trên web".`;
const AI_PAID = `
- Hãy dùng công cụ web_search (tối đa 3 lần) để tìm trên trang CHÍNH THỨC trước khi viết. Mọi con số, quy định, giấy tờ đưa vào kịch bản phải thấy trên trang đã tìm. Không tìm thấy thì nói chung chung, không bịa.
- Phần NGUỒN liệt kê 1–3 đường link chính thức bạn đã dùng.`;

const AI_CONVERT = `
- NHIỆM VỤ LẦN NÀY: CHUYỂN NỘI DUNG người dùng viết (trong tin nhắn, mục NỘI DUNG) thành kịch bản đúng định dạng PHẦN B.
- GIỮ NGUYÊN ý, số liệu, tên trường, mốc thời gian, lời khuyên của người dùng. KHÔNG thêm thông tin, con số hay quy định mới. KHÔNG bỏ ý quan trọng.
- Được phép: rút gọn câu cho dễ đọc, chia thành các cảnh, viết câu mở gây tò mò từ chính nội dung, gom ý thành danh sách "- " có hình, các bước thành sơ đồ " → ", thêm [1/3]..., *từ khoá*, [vẽ: ...] trong danh sách hình, câu kết rủ bình luận + mời inbox Du Học Hải Dương.
- ƯU TIÊN TUYỆT ĐỐI: Chuyển đầy đủ toàn bộ bài, không tóm tắt, không bỏ đoạn, không gộp mất chi tiết. Bỏ tất cả giới hạn tổng 60–100 chữ, 8–14 cảnh, 15–25 cảnh, một điểm kiến thức, 20–45 giây ở mọi phần trước. Số cảnh và thời lượng phụ thuộc vào bài gốc; có thể trên 25 cảnh.
- Chỉ rút ngắn chữ trên màn hình (bên trái ||). Lời đọc bên phải || phải giữ sát nguyên văn, chỉ sửa chính tả, viết số bằng chữ hoặc điều chỉnh nhẹ để đọc tự nhiên. Nếu lời đọc dài hơn 24 chữ, chia tiếp thành nhiều cảnh, không bỏ chữ để đạt giới hạn. Giữ trình tự các đoạn, toàn bộ ví dụ, danh sách, địa danh, số liệu, điều kiện và lời khuyên.
- Chữ Trung/Hàn trong nội dung gốc phải chuyển sang phiên âm và giải nghĩa bằng tiếng Việt vì bộ đọc không hỗ trợ ký tự gốc. Giữ các từ khóa dưới dạng phiên âm, không bỏ ý.
- Tự đối chiếu từng đoạn với bài gốc trước khi trả lời. Không bỏ đoạn cuối hoặc CTA. Tổng lời đọc phải gần bằng độ dài bài gốc, không phải bản tóm tắt.
- Phần NGUỒN ghi: "Nội dung do người dùng cung cấp".`;

const AI_FIX = `
- NHIỆM VỤ LẦN NÀY: SỬA kịch bản trong tin nhắn cho hết các LỖI được liệt kê, đúng định dạng PHẦN B.
- GIỮ NGUYÊN nội dung, ý, số liệu. Chỉ sửa cách trình bày: rút ngắn chữ màn hình (dùng " / " xuống dòng, mỗi dòng ≤22 ký tự), tách cảnh dài, rút gọn câu mở, sửa danh sách, sơ đồ, thẻ.
- Không thêm thông tin mới, không tóm tắt. Không áp dụng giới hạn tổng số cảnh, tổng số chữ hay thời lượng. Nếu cảnh dài, tách thành nhiều cảnh mà giữ lời đọc và mọi chi tiết. Không bỏ nội dung để xử lý cảnh báo thời lượng hoặc số cảnh. Trả lời đúng PHẦN C; phần NGUỒN ghi "Nội dung do người dùng cung cấp".`;

function parseAi(text) {
  const m = text.match(/```[a-zA-Z]*\n?([\s\S]*?)```/);
  const script = (m ? m[1] : text).trim();
  const rest = m ? text.slice(text.indexOf(m[0]) + m[0].length) : '';
  const si = rest.search(/^\s*\**\s*(NGUỒN|Nguồn|\(3\))/m);
  const caption = (si >= 0 ? rest.slice(0, si) : rest).replace(/^\s*\**\s*(CAPTION|\(2\))[^\n]*\n?/im, '').trim();
  const srcTxt = si >= 0 ? rest.slice(si) : '';
  return { script, caption, srcTxt };
}
async function aiGemini(env, sys, user) {
  let last = '';
  for (const model of ['gemini-flash-latest', 'gemini-3.5-flash-lite']) {
    const r = await aiFetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-goog-api-key': env.GEMINI_KEY },
      body: JSON.stringify({ systemInstruction: { parts: [{ text: sys }] }, contents: [{ role: 'user', parts: [{ text: user }] }],
        generationConfig: { maxOutputTokens: 8192 } }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      const parts = (((d.candidates || [])[0] || {}).content || {}).parts || [];
      const text = parts.filter(x => !x.thought && x.text).map(x => x.text).join('');
      if (text.trim()) {
        const finish = (d.candidates || [])[0]?.finishReason;
        if (finish === 'MAX_TOKENS') throw new Error('AI chưa trả hết nội dung. Hãy chia bài viết thành các phần ngắn hơn.');
        return { text, sources: [] };
      }
      last = 'Gemini không trả về nội dung';
      continue;
    }
    last = (d.error && d.error.message) || ('Gemini lỗi ' + r.status);
    if (/location is not supported/i.test(last)) last = 'Gemini chưa hỗ trợ vị trí máy chủ hiện tại. Báo admin kiểm tra cài đặt vùng (AI_REGION).';
    if (r.status === 429) last = 'Gemini miễn phí đã hết lượt hôm nay (hoặc gọi quá nhanh). Thử lại sau ít phút, hoặc dùng "Viết có kiểm chứng".';
    if (![404, 429, 500, 503].includes(r.status)) break;
  }
  throw new Error(last);
}
async function aiClaude(env, sys, user, search = true) {
  const tool = { type: 'web_search_20250305', name: 'web_search', max_uses: 4, allowed_domains: OFFICIAL };
  let useDomains = true, stop = '', diag = [];
  const blocks = [];                                   // toàn bộ nội dung trợ lý (kể cả các lượt tạm dừng)
  const call = async (messages, extra = {}) => {
    for (let k = 0; k < 2; k++) {
      const r = await aiFetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-api-key': env.CLAUDE_KEY, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model: 'claude-sonnet-5-5', max_tokens: 8000, system: sys, messages,
          ...(search ? { tools: [useDomains ? tool : { type: tool.type, name: tool.name, max_uses: tool.max_uses }], ...extra } : {}) }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) return d;
      const msg = (d.error && d.error.message) || ('Claude lỗi ' + r.status);
      if (r.status === 400 && useDomains && /domain/i.test(msg)) { useDomains = false; continue; }
      if (/web search/i.test(msg) && /enable|disabled|not enabled/i.test(msg)) throw new Error('Cần bật Web search trong trang quản lý Claude (Console → Settings).');
      if (/credit|balance/i.test(msg)) throw new Error('Tài khoản Claude đã hết tiền nạp. Admin hãy nạp thêm trong Claude Console.');
      if (/location is not supported|not available in your/i.test(msg)) throw new Error('Claude chưa hỗ trợ vị trí máy chủ hiện tại.');
      throw new Error(msg);
    }
    throw new Error('Claude từ chối danh sách trang chính thức');
  };
  for (let step = 0; step < 5; step++) {
    const msgs = blocks.length ? [{ role: 'user', content: user }, { role: 'assistant', content: blocks }] : [{ role: 'user', content: user }];
    const d = await call(msgs);
    blocks.push(...(d.content || []));
    stop = d.stop_reason || '';
    diag.push(stop);
    if (stop !== 'pause_turn') break;
  }
  const textOf = arr => arr.filter(b => b.type === 'text').map(b => b.text).join('');
  let text = textOf(blocks);
  if (search && !/```/.test(text)) {                   // tra xong nhưng chưa viết: bảo viết ngay, không tra thêm
    const d = await call([{ role: 'user', content: user }, { role: 'assistant', content: blocks },
      { role: 'user', content: 'Bạn đã tra đủ. Hãy viết NGAY kịch bản theo đúng PHẦN C (khối ``` kịch bản, CAPTION, NGUỒN), không tìm thêm.' }],
      { tool_choice: { type: 'none' } });
    blocks.push(...(d.content || []));
    diag.push('retry:' + (d.stop_reason || ''));
    text = textOf(blocks);
  }
  if (!text.trim()) {
    const errs = blocks.filter(b => b.type === 'web_search_tool_result' && b.content && b.content.error_code).map(b => b.content.error_code);
    throw new Error('Claude chưa trả về chữ (mã: ' + diag.join(',') + (errs.length ? '; tra web: ' + errs.join(',') : '') + '; khối: ' + [...new Set(blocks.map(b => b.type))].join(',') + ')');
  }
  const seen = new Map();
  for (const b of blocks) {
    if (b.type === 'text') for (const c of (b.citations || [])) if (c.url && !seen.has(c.url)) seen.set(c.url, c.title || c.url);
  }
  return { text, sources: [...seen].map(([url, title]) => ({ url, title })) };
}
function today() { return new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 10); }
async function aiRecord(env, who, mode) {
  for (let i = 0; i < 3; i++) {
    const { data, sha } = await readJson(env, AI_FILE);
    const d = today();
    data.use = data.use || {};
    for (const k of Object.keys(data.use)) if (k < new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10)) delete data.use[k];
    const day = data.use[d] = data.use[d] || {};
    const u = day[who] = day[who] || { free: 0, paid: 0 };
    u[mode] = (u[mode] || 0) + 1;
    const bytes = new TextEncoder().encode(JSON.stringify(data, null, 1));
    let bin = ''; bytes.forEach(b => { bin += String.fromCharCode(b); });
    const body = { message: 'Ghi lượt dùng AI', content: btoa(bin), branch: 'main' };
    if (sha) body.sha = sha;
    const r = await gh(env, `/contents/${AI_FILE}`, { method: 'PUT', body: JSON.stringify(body) });
    if (r.ok) return;
  }
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
      tpl: info.tpl || '', ab: info.ab || '', abg: info.abg || '', fmt: info.fmt || '',
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
  async fetch(req, env, ctx) {
    _ENV = env;
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
          stroke: b.stroke !== false,
          trans: ['xoa', 'lia', 'xen'].includes(b.trans) ? b.trans : 'xen',
          reveal: b.reveal === 'quet' ? 'quet' : 'net',
          hook: b.hook !== false,
          tpl: /^[a-z0-9_]{1,30}$/.test(b.tpl || '') ? b.tpl : '',
          ab: ['A', 'B'].includes(b.ab) ? b.ab : '',
          abg: /^[a-z0-9]{1,24}$/.test(b.abg || '') ? b.abg : '',
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
      if (p === '/api/stats' && req.method === 'GET') return json((await readJson(env, STATS)).data);
      m = p.match(/^\/api\/stats\/([a-z0-9]+)$/);
      if (m && req.method === 'POST') {
        const b = await req.json();
        const n = k => Math.max(0, Math.min(1e9, parseInt(b[k] || 0, 10) || 0));
        const rec = { views: n('views'), likes: n('likes'), comments: n('comments'), shares: n('shares'), saves: n('saves'),
          platform: ['tiktok', 'facebook', 'youtube', 'khac'].includes(b.platform) ? b.platform : 'tiktok',
          by: String(b.by || '').slice(0, 40), at: Math.floor(Date.now() / 1000) };
        if (!(await saveStats(env, m[1], rec))) return err('Không lưu được, thử lại', 502);
        return json({ ok: true, rec });
      }
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

      // ---- AI viết kịch bản từ chủ đề
      if (p === '/api/ai/config' && req.method === 'GET') {
        const { data } = await readJson(env, AI_FILE);
        const cfg = { ...AI_DEF, ...(data.config || {}) };
        return json({ ...cfg, has_free: !!env.GEMINI_KEY, has_paid: !!env.CLAUDE_KEY, admin, today: admin ? (data.use || {})[today()] || {} : undefined });
      }
      if (p === '/api/ai/config' && req.method === 'POST') {
        if (!admin) return err(ADMIN_ONLY, 403);
        const b = await req.json();
        for (let i = 0; i < 3; i++) {
          const { data, sha } = await readJson(env, AI_FILE);
          data.config = { free: Math.max(0, Math.min(500, parseInt(b.free, 10) || 0)), paid: Math.max(0, Math.min(200, parseInt(b.paid, 10) || 0)), paid_staff: !!b.paid_staff };
          const bytes = new TextEncoder().encode(JSON.stringify(data, null, 1));
          let bin = ''; bytes.forEach(x => { bin += String.fromCharCode(x); });
          const body = { message: 'Cài đặt AI', content: btoa(bin), branch: 'main' };
          if (sha) body.sha = sha;
          const r = await gh(env, `/contents/${AI_FILE}`, { method: 'PUT', body: JSON.stringify(body) });
          if (r.ok) return json({ ok: true, ...data.config });
        }
        return err('Không lưu được, thử lại', 502);
      }
      if (p === '/api/ai/script' && req.method === 'POST') {
        const b = await req.json();
        const fix = b.task === 'fix';
        const convert = b.task === 'convert' || fix;
        const duration = fix ? 'full' : Object.prototype.hasOwnProperty.call(AI_LENGTHS, b.duration) ? b.duration : convert ? 'full' : 'quick';
        const content = String(b.content || '').trim();
        if (convert && content.length > 12000) return err('Nội dung dài hơn 12.000 ký tự. Hãy chia thành các phần để AI không bỏ sót nội dung.');
        const issues = (Array.isArray(b.issues) ? b.issues : []).slice(0, 12).map(x => String(x).slice(0, 200));
        const topic = convert ? 'chuyển nội dung' : String(b.topic || '').trim().slice(0, 400);
        if (convert && content.length < 20) return err('Hãy viết nội dung (ít nhất vài câu) trước khi chuyển');
        const extra = String(b.extra || '').trim().slice(0, 2500);
        const mode = b.mode === 'paid' && !convert ? 'paid' : 'free';   // chuyển/sửa định dạng luôn dùng Gemini miễn phí
        if (topic.length < 4) return err('Hãy nhập chủ đề video');
        const { data } = await readJson(env, AI_FILE);
        const cfg = { ...AI_DEF, ...(data.config || {}) };
        if (mode === 'paid' && !env.CLAUDE_KEY) return err('Chưa gắn khoá Claude. Admin xem hướng dẫn trong mục Cài đặt.');
        if (mode === 'free' && !env.GEMINI_KEY) return err('Chưa gắn khoá Gemini. Admin xem hướng dẫn trong mục Cài đặt.');
        if (mode === 'paid' && !admin && !cfg.paid_staff) return err('Chế độ dùng Claude (trả phí) hiện chỉ dành cho admin.', 403);
        const ip = req.headers.get('cf-connecting-ip') || 'ip';
        const who = (slug(b.by || '') || 'khong_ten') + '@' + ip.replace(/[^0-9a-f.:]/gi, '').slice(-20);
        const used = (((data.use || {})[today()] || {})[who] || {})[mode] || 0;
        const limit = cfg[mode];
        if (!admin && !fix && used >= limit) return err(`Bạn đã dùng hết ${limit} lượt "${mode === 'paid' ? 'Viết có kiểm chứng' : 'Viết nhanh'}" hôm nay. Mai dùng tiếp, hoặc nhờ admin tăng giới hạn.`, 429);
        const common = AI_COMMON.replace('- Mỗi video 1 điểm kiến thức, 8–12 dòng cảnh, lời đọc tổng khoảng 60–100 chữ.', '- Số cảnh và tổng lời đọc tuân theo chế độ thời lượng ở cuối câu lệnh.');
        const durationRule = duration === 'full'
          ? '\n- CHẾ ĐỘ GIỮ NGUYÊN: Không áp dụng bất kỳ giới hạn tổng số cảnh, tổng số chữ, một điểm kiến thức hoặc thời lượng video ngắn nào ở trên. Giữ nội dung đầy đủ.'
          : '\n- THỜI LƯỢNG ĐƯỢC CHỌN (ưu tiên hơn giới hạn video ngắn ở trên): ' + AI_LENGTHS[duration] + '. Không ép 8–14 hoặc 15–25 cảnh, không giới hạn 60–100 chữ. Chia số cảnh linh hoạt theo lời đọc. Không cố kéo dài khi thiếu thông tin đáng tin cậy.';
        const sys = (await chatgptPrompt(env)) + common + (fix ? AI_FIX : convert ? (duration === 'full' ? AI_CONVERT : AI_CONVERT_TIMED) : mode === 'paid' ? AI_PAID : AI_FREE) + durationRule;
        const user = fix ? `KỊCH BẢN CẦN SỬA:\n\`\`\`\n${content}\n\`\`\`\n\nCÁC LỖI CẦN SỬA:\n${issues.map((x, i) => (i + 1) + '. ' + x).join('\n')}`
          : convert ? `NỘI DUNG CỦA TÔI (chuyển thành kịch bản, giữ nguyên ý và số liệu):\n${content}`
          : `CHỦ ĐỀ: ${topic}` + (extra ? `\n\nTHÔNG TIN THÊM (của trung tâm, dùng đúng như vậy):\n${extra}` : '');
        let out;
        try { out = mode === 'paid' ? await aiClaude(env, sys, user, !convert) : await aiGemini(env, sys, user); }
        catch (e) { return err(String(e.message || e), 502); }
        const res = parseAi(out.text);
        if (res.script.length > 20000) return err('Kịch bản vượt giới hạn 20.000 ký tự của bộ dựng. Hãy chia bài thành các phần.', 422);
        if (!res.script) return err('AI chưa viết được kịch bản, hãy thử lại hoặc đổi cách nói chủ đề.', 502);
        const urls = [...res.srcTxt.matchAll(/https?:\/\/[^\s)\]]+/g)].map(x => ({ url: x[0], title: '' }));
        const sources = [...out.sources];
        for (const u of urls) if (!sources.some(x => x.url === u.url)) sources.push(u);
        if (!fix) {                                                    // vòng tự sửa không tính lượt
          const rec = aiRecord(env, admin ? 'admin' : who, mode);
          if (ctx && ctx.waitUntil) ctx.waitUntil(rec); else await rec;
        }
        return json({ script: res.script, caption: res.caption, sources: convert ? [] : sources.slice(0, 8), mode, convert, duration,
          verified: !convert && mode === 'paid' && sources.length > 0, used: used + 1, limit: admin ? null : limit });
      }
      if (p === '/api/names') {
        const [hv, kho] = await Promise.all([
          gh(env, '/contents/engine/TEN_HINH.txt', { headers: { accept: 'application/vnd.github.raw' } }).then(r => r.ok ? r.text() : ''),
          listDir(env, 'engine/assets/kho'),
        ]);
        const khoNames = kho.filter(x => x.name.endsWith('.png') && !x.name.startsWith('_')).map(x => x.name.slice(0, -4).replace(/_/g, ' '));
        return json({ hv: hv.split('\n').map(s => s.trim()).filter(Boolean), kho: khoNames });
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
