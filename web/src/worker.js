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

// Bộ nhớ tạm ngắn hạn cho các lần ĐỌC GitHub (danh sách kho, cấu hình, danh sách video) -> trang mở nhanh hơn.
// Mọi thao tác GHI (thêm/xoá/sửa) đều xoá sạch bộ nhớ tạm để không hiện dữ liệu cũ.
const MEMO = new Map();
function memoTtl(path, opt) {
  const method = (opt.method || 'GET').toUpperCase();
  if (method !== 'GET' || (opt.headers && opt.headers.accept === 'application/octet-stream')) return 0;
  if (path.startsWith('/contents/')) return (opt.headers && /raw/.test(opt.headers.accept || '')) ? 0 : 45000;
  if (path.startsWith('/releases?')) return 12000;
  return 0;
}
async function gh(env, path, opt = {}) {
  const method = (opt.method || 'GET').toUpperCase();
  if (method !== 'GET') MEMO.clear();
  const ttl = memoTtl(path, opt);
  if (ttl) {
    const hit = MEMO.get(path);
    if (hit && Date.now() - hit.t < ttl) return new Response(hit.body, { status: hit.status, headers: hit.headers });
  }
  const r = await ghRaw(env, path, opt);
  if (ttl && (r.ok || r.status === 404)) {
    const body = await r.arrayBuffer();
    if (MEMO.size > 200) MEMO.clear();
    MEMO.set(path, { t: Date.now(), body, status: r.status, headers: [...r.headers] });
    return new Response(body, { status: r.status, headers: r.headers });
  }
  return r;
}
function ghRaw(env, path, opt = {}) {
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

// Ảnh (kho, nền, logo, ảnh xem trước, ảnh bìa) lưu ở bộ nhớ đệm Cloudflare gần người dùng: mở lần sau gần như tức thì.
async function edgeCached(req, ctx, ttl, make) {
  const cache = caches.default;
  const key = new Request(new URL(req.url).toString(), { method: 'GET' });
  const hit = await cache.match(key);
  if (hit) return hit;
  const r = await make();
  if (r.ok) {
    const h = new Headers(r.headers);
    h.set('cache-control', `public, max-age=${ttl}`);
    const out = new Response(r.body, { status: r.status, headers: h });
    const put = cache.put(key, out.clone());
    if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
    h.set('cache-control', `private, max-age=${ttl}`);
    return new Response(out.body, { status: out.status, headers: h });
  }
  return r;
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
    const path = new URL(req.url).pathname;
    if (path === '/status') return Response.json((await this.state.storage.get('job')) || { state: '' });
    if (path === '/start') {
      const job = await req.json();
      const cur = await this.state.storage.get('job');
      if (cur && cur.state === 'running' && Date.now() - cur.t < 16 * 60e3) return Response.json({ state: 'running', kind: cur.kind, t: cur.t });
      const rec = { ...job, state: 'running', t: Date.now() };
      await this.state.storage.put('job', rec);
      await this.state.storage.setAlarm(Date.now() + 50);
      return Response.json({ state: 'running', kind: job.kind, t: rec.t });
    }
    const { url, headers, body } = await req.json();
    if (!/^https:\/\/(generativelanguage\.googleapis\.com|api\.anthropic\.com)\//.test(url)) return new Response('bad', { status: 400 });
    const h = { ...headers };
    if (url.includes('googleapis')) h['x-goog-api-key'] = this.env.GEMINI_KEY;
    else h['x-api-key'] = this.env.CLAUDE_KEY;
    const r = await fetch(url, { method: 'POST', headers: h, body });
    return new Response(await r.text(), { status: r.status, headers: { 'content-type': 'application/json' } });
  }
  async alarm() {
    const job = await this.state.storage.get('job');
    if (!job || job.state !== 'running') return;
    _ENV = this.env;                                          // gọi AI qua máy trung gian ở Mỹ như mọi khi
    try {
      await trJobRun(_ENV, job);
      await this.state.storage.put('job', { kind: job.kind, state: 'done', t: Date.now() });
    } catch (e) {
      await this.state.storage.put('job', { kind: job.kind, state: 'error', error: String(e && e.message || e).slice(0, 300), t: Date.now() });
    }
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
async function chatgptPrompt(env, lv) {
  const dh = !lv || lv.id === 'duhoc';
  const [txt, kho] = await Promise.all([
    gh(env, dh ? '/contents/engine/LENH_CHATGPT.txt' : '/contents/engine/linhvuc/_mau.txt', { headers: { accept: 'application/vnd.github.raw' } }).then(r => r.text()),
    khoItems(env, lv),
  ]);
  const names = kho.map(x => x.name);
  const vd = dh ? 'hồ sơ du học' : (names[0] || 'tên hình');
  const extra = names.length ? `\n\nẢNH TRONG KHO (ưu tiên dùng, viết có dấu cũng được, ví dụ [vẽ: ${vd}]):\n${names.join(', ')}\n` : '';
  let t = txt.replace(/^\uFEFF/, '');
  if (!dh) {
    const f = { TEN: lv.ten, SLOGAN: lv.slogan || lv.ten, NGANH: lv.nganh || '', KHACH: lv.khach || 'khách hàng', LUU_Y: lv.luu_y || '',
      HASHTAG: lv.hashtag || '', VI_DU: String(lv.vi_du || '').replace(/\{TEN\}/g, lv.ten) };
    t = t.replace(/\{(TEN|SLOGAN|NGANH|KHACH|LUU_Y|HASHTAG|VI_DU)\}/g, (_, k) => f[k]);
  }
  return t + extra;
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

const AI_BAY = `
- PHONG CÁCH CAMERA BAY (ưu tiên hơn quy tắc B5 về [tiếp]): video kể theo từng "GÓC BẢNG", camera bay giữa các góc. Mỗi góc bảng là MỘT ý, gồm 2–3 dòng cảnh liền nhau vẽ dần vào cùng một chỗ.
- Dòng ĐẦU của mỗi góc: câu ngắn nêu ý (có thể kèm huy hiệu [1/3], [2/3]... khi kể theo từng phần). Các dòng SAU trong cùng góc: thêm thẻ [tiếp] ở cuối phần chữ màn hình (ngay trước ||).
- Dòng đầu video (câu mở) và dòng kết (mời bình luận/inbox) đứng riêng, không thêm [tiếp]. Bảng so sánh "A vs B" và dòng số liệu lớn đứng riêng một góc.
- Trong một góc, mỗi dòng nên có hình [vẽ: ...] hoặc danh sách ngắn để camera có thứ cận cảnh rồi lùi ra.
- Mỗi góc tối đa 3 dòng. Khi SỬA kịch bản: giữ nguyên các thẻ [tiếp], chỉ sửa lỗi được nêu.`;

const AI_REMIX = `
- NHIỆM VỤ LẦN NÀY: Trong tin nhắn có LỜI CỦA MỘT VIDEO CỦA KÊNH KHÁC (đối thủ). Chỉ được HỌC Ý TƯỞNG / CHỦ ĐỀ, rồi VIẾT MỚI HOÀN TOÀN một kịch bản của Du Học Hải Dương đúng định dạng PHẦN B.
- CẤM SAO CHÉP: không chép lại bất kỳ câu nào; không được có cụm 6 chữ liên tiếp giống bài gốc. Câu mở phải khác hẳn câu mở của họ. Đổi thứ tự trình bày, đổi ví dụ, đổi cách kết. Giọng tư vấn viên Du Học Hải Dương, nói với "bạn".
- Bỏ hết tên kênh, tên người, tên trung tâm, số điện thoại, link, mã giảm giá, lời quảng cáo của bên kia. Không nhắc tới video gốc.
- Nếu bài gốc có thông tin sai, phóng đại hoặc hứa hẹn kiểu môi giới (bao đậu visa, đi làm kiếm nhiều tiền...), KHÔNG lặp lại; chỉ giữ phần đúng và hữu ích.
- Lời gốc có thể là bản dịch máy (tiếng Anh, sai chính tả, lộn xộn): hiểu ý rồi viết tiếng Việt tự nhiên.
- Nếu lời gốc có nhiều ý mà thời lượng ngắn: chỉ chọn MỘT ý hay nhất (hoặc ý ghi ở mục CHỈ VIẾT VỀ), các ý khác bỏ.
- Chữ Trung/Hàn chuyển sang phiên âm và giải nghĩa tiếng Việt.
- Phần NGUỒN: ghi trang chính thức đã dùng; nếu không tra web thì ghi "Ý tưởng tham khảo, nội dung viết lại".`;
const AI_REMIX_FREE = `
- Bạn KHÔNG tra web được, nên KHÔNG giữ con số, mức phí, mốc thời gian, điều kiện cụ thể nào từ bài gốc (chưa kiểm chứng). Viết theo hướng kinh nghiệm, kiến thức chung, "tùy trường", "xem thông báo mới nhất".`;
const AI_REMIX_PAID = `
- Mọi con số, quy định lấy từ bài gốc PHẢI kiểm tra bằng web_search trên trang chính thức. Đúng thì dùng (theo số liệu chính thức), không thấy thì bỏ hoặc nói chung chung. Phần NGUỒN liệt kê link đã dùng.`;
function wordsOf(t) { return String(t || '').toLowerCase().normalize('NFC').replace(/\[[^\]]*\]/g, ' ').split(/[^\p{L}\p{N}]+/u).filter(Boolean); }
function spokenOf(script) {
  return script.split('\n').map(l => l.includes('||') ? l.split('||').slice(1).join(' ') : l.replace(/^\s*[-+]\s/, '')).join(' ');
}
// Độ giống: % cụm 6 chữ của kịch bản mới xuất hiện trong lời gốc + cụm giống dài nhất
function copyScore(src, script) {
  const a = wordsOf(src), b = wordsOf(spokenOf(script)), N = 6;
  if (b.length < N || a.length < N) return { pct: 0, longest: 0 };
  const set = new Set();
  for (let i = 0; i + N <= a.length; i++) set.add(a.slice(i, i + N).join(' '));
  let hit = 0, run = 0, longest = 0;
  for (let i = 0; i + N <= b.length; i++) {
    if (set.has(b.slice(i, i + N).join(' '))) { hit++; run++; longest = Math.max(longest, run + N - 1); } else run = 0;
  }
  return { pct: Math.round(100 * hit / (b.length - N + 1)), longest };
}
async function getTranscript(env, link) {
  const H = { 'x-api-key': env.SUPADATA_KEY };
  let r = await fetch('https://api.supadata.ai/v1/transcript?text=true&mode=auto&lang=vi&url=' + encodeURIComponent(link), { headers: H });
  let d = await r.json().catch(() => ({}));
  if (r.status === 202 && d.jobId) {
    for (let k = 0; k < 40; k++) {
      await new Promise(ok => setTimeout(ok, 1500));
      r = await fetch('https://api.supadata.ai/v1/transcript/' + encodeURIComponent(d.jobId), { headers: H });
      const j = await r.json().catch(() => ({}));
      if (j.status === 'completed') { d = j; break; }
      if (j.status === 'failed') throw new Error('Không lấy được lời video này (' + ((j.error && (j.error.message || j.error)) || 'lỗi') + ')');
      if (k === 39) throw new Error('Video dài, lấy lời quá lâu. Thử lại sau hoặc dán lời vào ô bên dưới.');
    }
  } else if (!r.ok || r.status === 206) {
    if (r.status === 404) throw new Error('Không tìm thấy video (video riêng tư hoặc đã xoá).');
    if (r.status === 403) throw new Error('Video bị giới hạn, cần đăng nhập mới xem được.');
    if (r.status === 206) throw new Error('Video này không có lời để lấy.');
    if (r.status === 401) throw new Error('Khoá Supadata sai. Báo admin kiểm tra.');
    if (r.status === 429) throw new Error('Hết lượt lấy lời miễn phí tháng này (Supadata).');
    throw new Error((d && (d.message || d.error)) || ('Lấy lời lỗi ' + r.status));
  }
  const c = d.content;
  const text = (Array.isArray(c) ? c.map(x => x.text).join(' ') : String(c || '')).replace(/\s+/g, ' ').trim();
  if (text.length < 20) throw new Error('Video này gần như không có lời nói.');
  return { text: text.slice(0, 12000), lang: d.lang || '' };
}
// =====================================================================
// MỖI NGÀY MỘT TRƯỜNG (chỉ quản lý): nghiên cứu có nguồn, kho ảnh thật riêng từng trường, kịch bản, tạo video
// Dữ liệu: truong/_ds.json (danh sách + bật/tắt), truong/<mã>/nghien_cuu.json, truong/<mã>/kich_ban.json
// Ảnh: engine/assets/truong/<mã>/*.jpg|png + _anh.json (nguồn, quyền dùng, ngày, kích thước)
// =====================================================================
const TR_DS = 'truong/_ds.json';
const TR_ID = /^(tw|kr)_[a-z0-9_]{2,40}$/;
const TR_CHU_DE = [['logo', 'logo trường'], ['cong_truong', 'cổng trường'], ['khuon_vien', 'toàn cảnh khuôn viên'], ['toa_nha', 'tòa nhà'],
  ['ban_do', 'bản đồ vị trí'], ['thu_vien', 'thư viện'], ['phong_hoc', 'phòng học'], ['phong_thuc_hanh', 'phòng thực hành'],
  ['phong_thi_nghiem', 'phòng thí nghiệm'], ['ky_tuc_xa', 'ký túc xá'], ['nha_an', 'nhà ăn'], ['hoat_dong', 'hoạt động sinh viên'],
  ['tot_nghiep', 'lễ tốt nghiệp'], ['xung_quanh', 'khu vực xung quanh trường'], ['giao_thong', 'giao thông gần trường']];
const TR_MUC = [['ten', 'Tên tiếng Việt, tiếng Anh, tên bản địa'], ['thanh_lap', 'Năm thành lập và lịch sử'], ['loai_hinh', 'Công lập hay tư thục'],
  ['vi_tri', 'Vị trí, địa chỉ, cơ sở đào tạo'], ['giao_thong', 'Giao thông'], ['the_manh', 'Thế mạnh đào tạo'], ['nganh', 'Ngành nổi bật'],
  ['co_so', 'Cơ sở vật chất'], ['chuong_trinh_qt', 'Chương trình cho sinh viên quốc tế'], ['tuyen_sinh', 'Điều kiện tuyển sinh'],
  ['ngoai_ngu', 'Yêu cầu ngoại ngữ'], ['hoc_phi', 'Học phí'], ['hoc_bong', 'Học bổng và trợ cấp'], ['ky_tuc_xa', 'Ký túc xá'],
  ['sinh_hoat', 'Chi phí sinh hoạt'], ['viec_lam', 'Thực tập và việc làm'], ['uu_diem', 'Ưu điểm'], ['han_che', 'Hạn chế'],
  ['phu_hop', 'Đối tượng phù hợp']];
const TR_NGUON = { tw: ['studyintaiwan.org', 'edu.tw', 'gov.tw', 'roc-taiwan.org'], kr: ['studyinkorea.go.kr', 'go.kr', 'ac.kr', 'hikorea.go.kr'] };

function trClean(x) { return String(x || '').replace(/<\/?cite[^>]*>/gi, '').replace(/<[^>]{0,40}>/g, '').replace(/\s+/g, ' ').trim(); }
function trHost(u) { try { return new URL(/^https?:/i.test(u) ? u : 'https://' + u).hostname.replace(/^www\./, ''); } catch { return ''; } }
function trB64(str) { const by = new TextEncoder().encode(str); let s = ''; by.forEach(x => { s += String.fromCharCode(x); }); return btoa(s); }
async function trSave(env, path, data, message) {
  for (let i = 0; i < 3; i++) {
    const cur = await ghJson(env, `/contents/${path}`);
    const body = { message, content: trB64(JSON.stringify(data, null, 1) + '\n'), branch: 'main' };
    if (cur && cur.sha) body.sha = cur.sha;
    const r = await gh(env, `/contents/${path}`, { method: 'PUT', body: JSON.stringify(body) });
    if (r.ok) return;
    if (r.status !== 409 && r.status !== 422) throw new Error('Không lưu được (GitHub ' + r.status + ')');
  }
  throw new Error('Không lưu được, thử lại');
}
async function trDs(env) {
  const { data } = await readJson(env, TR_DS);
  return { bat: !!data.bat, items: data.items && typeof data.items === 'object' ? data.items : {}, phut_ai: data.phut_ai || {} };
}
async function trDsEdit(env, fn, message) {
  for (let i = 0; i < 3; i++) {
    const { data, sha } = await readJson(env, TR_DS);
    const d = { bat: !!data.bat, items: data.items || {}, phut_ai: data.phut_ai || {} };
    const out = fn(d) || d;
    const body = { message, content: trB64(JSON.stringify(out, null, 1) + '\n'), branch: 'main' };
    if (sha) body.sha = sha;
    const r = await gh(env, `/contents/${TR_DS}`, { method: 'PUT', body: JSON.stringify(body) });
    if (r.ok) return out;
  }
  throw new Error('Không lưu được danh sách trường, thử lại');
}
function trNorm(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase().replace(/[^a-z0-9㐀-鿿가-힯]+/g, ' ').trim(); }
function trStatus(it) {
  if (it.dang) return 'Đã đăng video';
  if (it.can_cap_nhat) return 'Cần cập nhật thông tin';
  if ((it.video || []).length) return 'Đã xuất video';
  if (it.cho_duyet) return 'Chờ duyệt';
  if (it.kb) return 'Đã có kịch bản';
  if ((it.anh || 0) >= 3) return 'Đã có hình ảnh';
  if (it.nc) return 'Đã nghiên cứu';
  return 'Chưa nghiên cứu';
}
async function trAnh(env, id) {
  const [files, meta] = await Promise.all([listDir(env, `engine/assets/truong/${id}`), readJson(env, `engine/assets/truong/${id}/_anh.json`)]);
  const m = meta.data || {};
  return files.filter(f => /\.(jpg|png)$/.test(f.name) && !f.name.startsWith('_')).map(f => {
    const k = f.name.replace(/\.(jpg|png)$/, '');
    return { file: f.name, url: `/img/truong/${id}/${f.name}`, ...(m[k] || { ten: k.replace(/_/g, ' ') }) };
  });
}
// Tìm ảnh trên website chính thức: đọc trang chủ (theo cả chuyển hướng meta refresh) + vài trang giới thiệu/quốc tế
async function trFindImages(web) {
  const host = trHost(web);
  if (!host) throw new Error('Chưa có website chính thức của trường');
  const seen = new Set(), out = [], pages = [];
  const get = async u => {
    const r = await fetch(u, { headers: { 'user-agent': 'Mozilla/5.0 (HDVideos; tra anh truong)', accept: 'text/html' }, redirect: 'follow' });
    if (!r.ok || !/html/i.test(r.headers.get('content-type') || '')) return null;
    return { url: r.url, html: (await r.text()).slice(0, 600000) };
  };
  const abs = (u, base) => { try { return new URL(u.replace(/&amp;/g, '&'), base).href; } catch { return ''; } };
  const queue = [/^https?:/i.test(web) ? web : 'https://' + web];
  for (let n = 0; queue.length && n < 6; n++) {
    const u = queue.shift();
    if (seen.has(u)) continue;
    seen.add(u);
    let pg = null;
    try { pg = await get(u); } catch { pg = null; }
    if (!pg) continue;
    const refresh = pg.html.match(/http-equiv=["']?refresh["']?[^>]*content=["'][^"']*url=([^"'>\s]+)/i);
    if (refresh) { queue.unshift(abs(refresh[1], pg.url)); n--; continue; }
    pages.push(pg.url);
    const og = pg.html.match(/property=["']og:image["'][^>]*content=["']([^"']+)/i);
    if (og) out.push({ url: abs(og[1], pg.url), alt: 'ảnh đại diện trang', trang: pg.url });
    for (const mm of pg.html.matchAll(/<img\b[^>]*>/gi)) {
      const tag = mm[0];
      const src = (tag.match(/\s(?:data-src|src)=["']([^"']+)/i) || [])[1];
      if (!src || /^data:/i.test(src)) continue;
      const alt = ((tag.match(/\salt=["']([^"']*)/i) || [])[1] || '').trim();
      out.push({ url: abs(src, pg.url), alt, trang: pg.url });
    }
    for (const mm of pg.html.matchAll(/<link\b[^>]*rel=["'][^"']*icon[^"']*["'][^>]*>/gi)) {
      const h = (mm[0].match(/href=["']([^"']+)/i) || [])[1];
      if (h) out.push({ url: abs(h, pg.url), alt: 'biểu tượng', trang: pg.url });
    }
    if (n < 2) {                                   // thêm vài trang con cùng trường: giới thiệu, quốc tế, khuôn viên
      for (const mm of pg.html.matchAll(/<a\b[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]{0,80}?)<\/a>/gi)) {
        const h = abs(mm[1], pg.url), txt = mm[2].replace(/<[^>]+>/g, '');
        if (!h.startsWith('http') || !trHost(h).endsWith(host.split('.').slice(-3).join('.'))) continue;
        if (/about|intro|campus|plan|international|oia|簡介|關於|校園|環境|國際|소개|캠퍼스|국제/i.test(h + ' ' + txt) && queue.length < 8) queue.push(h);
      }
    }
  }
  const okExt = /\.(jpe?g|png|webp)(\?|$)/i;
  const bad = /sprite|icon-|\/icons?\/|blank|spacer|pixel|loading|arrow|btn|button|banner_ad|qrcode|qr_|facebook|line\.|youtube|instagram|twitter|share/i;
  const res = [], urls = new Set();
  for (const c of out) {
    if (!c.url.startsWith('http') || urls.has(c.url)) continue;
    if (!okExt.test(c.url) && !/og:|ảnh đại diện|logo/i.test(c.alt + c.url)) continue;
    if (bad.test(c.url) && !/logo/i.test(c.url)) continue;
    urls.add(c.url);
    res.push({ ...c, logo: /logo/i.test(c.url + ' ' + c.alt) });
  }
  return { pages, items: res.slice(0, 60) };
}
function trResearchPrompt(it, ds) {
  const fields = TR_MUC.map(([k, t]) => `"${k}": {"gia_tri": "...", "nguon": "URL chính thức", "nam_hoc": "năm học/kỳ nhập học áp dụng (nếu có)", "kiem_chung": true}   // ${t}`).join('\n');
  return `Bạn là chuyên viên nghiên cứu của trung tâm Du Học Hải Dương. Nhiệm vụ: tra cứu THÔNG TIN THẬT về một trường đại học ${it.qg === 'kr' ? 'Hàn Quốc' : 'Đài Loan'} để làm video giới thiệu.

QUY TẮC BẮT BUỘC:
- Chỉ dùng thông tin bạn ĐÃ THẤY trên website chính thức của trường hoặc trang chính phủ/tổ chức chính thức (${(TR_NGUON[it.qg] || []).join(', ')}). Ghi URL nguồn cho từng mục.
- Không tìm thấy nguồn chính thức thì để "gia_tri": "" và "kiem_chung": false. TUYỆT ĐỐI không bịa, không đoán.
- Học phí, học bổng, điều kiện tuyển sinh phải ghi rõ năm học, kỳ nhập học và chương trình áp dụng (vào "nam_hoc").
- Tiền giữ đúng đơn vị gốc (NT$ / KRW). Viết tiếng Việt, ngắn gọn, đủ ý (mỗi mục tối đa khoảng 60 chữ).
- "uu_diem", "han_che", "phu_hop": nhận xét khách quan dựa trên dữ kiện đã kiểm chứng ở các mục khác (nguon có thể để trống, kiem_chung = true nếu suy ra từ dữ kiện có nguồn). Không tự xếp hạng trường.

Trả lời DUY NHẤT một khối \`\`\`json chứa:
{
"ten_vi": "...", "ten_en": "...", "ten_bd": "tên chữ Hán/Hàn",
${fields}
}`;
}
function trScriptRules(it, opt, photos) {
  const ty = opt.phong_cach === 've' ? 0 : opt.phong_cach === 'that' ? 80 : Math.max(0, Math.min(100, opt.ty_le || 60));
  const scenes = Math.round(opt.phut * 7);
  return `

====================================================
CHẾ ĐỘ "MỖI NGÀY MỘT TRƯỜNG" (ĐÈ LÊN MỌI DÒNG Ở TRÊN)
====================================================
Phần mềm gọi tự động. Viết NGAY kịch bản video giới thiệu trường, dài khoảng ${opt.phut} phút: khoảng ${Math.max(6, scenes - 3)}–${scenes + 3} dòng cảnh, lời đọc tổng khoảng ${Math.round(opt.phut * 140)} chữ.
- Giữ đúng định dạng: "Chữ màn hình / Dòng thứ hai || Lời đọc", mỗi dòng một cảnh.
- CHỈ dùng dữ kiện trong HỒ SƠ NGHIÊN CỨU (mục có kiem_chung = true). Mục trống hoặc chưa kiểm chứng thì bỏ qua, không bịa, không đoán.
- Học phí, học bổng, điều kiện: nói rõ năm học/kỳ nhập học/chương trình áp dụng. Không cam kết đỗ visa, không cam kết có việc làm, không tự xếp hạng trường, không quảng cáo quá mức.
- Bố cục (chọn ý hay, không cần đủ): mở đầu thu hút → tên trường → lịch sử → vị trí, giao thông → thế mạnh, ngành nổi bật → cơ sở vật chất → các hệ cho sinh viên quốc tế → điều kiện → học phí, học bổng → ký túc xá, sinh hoạt → thực tập, việc làm → ưu điểm và hạn chế → ai phù hợp → mời theo dõi series "Mỗi ngày một trường" của Du Học Hải Dương.
- Dòng đầu: "Tập ${String(it.tap || 1).padStart(3, '0')}" + tên trường ngắn gọn, gây tò mò.
- ẢNH THẬT CỦA TRƯỜNG (chỉ dùng đúng tên trong danh sách, viết [vẽ: tên ảnh]): ${photos.length ? photos.join(', ') : '(chưa có)'}.
  Khoảng ${ty}% số cảnh dùng ảnh thật: giới thiệu trường → logo/cổng trường; vị trí → bản đồ/khu vực; cơ sở vật chất → ảnh tương ứng. Một ảnh thật có thể dùng lại nhưng không dùng 2 cảnh liền nhau.
  Các cảnh còn lại (học phí, học bổng, điều kiện, hồ sơ, ưu nhược điểm) dùng hình vẽ tay trong danh sách kho.
- Trả lời đúng 3 phần: (1) MỘT khối \`\`\` chỉ chứa kịch bản, (2) CAPTION (2–3 dòng + 4–5 hashtag, có #MoiNgayMotTruong #DuHocHaiDuong), (3) NGUỒN: liệt kê các URL nguồn đã dùng từ hồ sơ.`;
}

async function trRoute(req, env, ctx, url, p, admin) {
  if (!p.startsWith('/api/truong') && !p.startsWith('/img/truong/')) return null;
  if (!admin) return err(ADMIN_ONLY, 403);
  const ds0 = await trDs(env);
  if (p === '/api/truong' && req.method === 'GET') {
    const items = Object.values(ds0.items).map(it => ({ ...it, trang_thai: trStatus(it) }))
      .sort((a, b) => (a.tap ? 0 : 1) - (b.tap ? 0 : 1) || (a.tap || 0) - (b.tap || 0) || String(a.ten_vi).localeCompare(String(b.ten_vi), 'vi'));
    return json({ bat: ds0.bat, items, chu_de: TR_CHU_DE, muc: TR_MUC });
  }
  if (p === '/api/truong/bat' && req.method === 'POST') {
    const b = await req.json();
    await trDsEdit(env, d => { d.bat = !!b.bat; }, b.bat ? 'Bật Mỗi ngày một trường' : 'Tắt Mỗi ngày một trường');
    return json({ ok: true, bat: !!b.bat });
  }
  if (!ds0.bat) return err('Mục "Mỗi ngày một trường" đang tắt. Bật trong Cài đặt.', 403);
  let m = p.match(/^\/img\/truong\/((?:tw|kr)_[a-z0-9_]+)\/([a-z0-9_]+\.(?:jpg|png))$/);
  if (m) return rawFile(env, `engine/assets/truong/${m[1]}/${m[2]}`, m[2].endsWith('.png') ? 'image/png' : 'image/jpeg');
  if (p === '/api/truong/proxy') {                 // xem trước ảnh tìm được (tránh trang trường chặn nhúng ảnh)
    const u = url.searchParams.get('u') || '';
    if (!/^https?:\/\//i.test(u)) return err('Link ảnh không hợp lệ');
    const r = await fetch(u, { headers: { 'user-agent': 'Mozilla/5.0 (HDVideos)', referer: new URL(u).origin + '/' } });
    if (!r.ok || !/^image\//.test(r.headers.get('content-type') || '')) return err('Không tải được ảnh', 404);
    return new Response(r.body, { headers: { 'content-type': r.headers.get('content-type'), 'cache-control': 'private, max-age=3600' } });
  }
  if (p === '/api/truong' && req.method === 'POST') {          // thêm / sửa thông tin cơ bản của trường
    const b = await req.json();
    const qg = b.qg === 'kr' ? 'kr' : 'tw';
    const ten_vi = String(b.ten_vi || '').trim().slice(0, 120), ten_en = String(b.ten_en || '').trim().slice(0, 160);
    if (!ten_vi && !ten_en) return err('Hãy nhập tên trường');
    let id = String(b.id || '');
    if (!TR_ID.test(id)) {
      const w = slug(ten_en || ten_vi).split('_').filter(x => x && !['university', 'of', 'science', 'and', 'technology', 'the', 'dai', 'hoc', 'truong', 'khoa', 'cong', 'nghe'].includes(x));
      id = qg + '_' + ((w.join('_') || slug(ten_en || ten_vi)).slice(0, 30) || 'truong');
      if (id.length < 5) id += '_' + Date.now().toString(36).slice(-3);
    }
    const web = String(b.web || '').trim().slice(0, 200);
    const keyN = [ten_vi, ten_en, b.ten_bd].map(trNorm).filter(Boolean), host = trHost(web);
    const curWeb = ds0.items[id] && ds0.items[id].web;
    const trung = Object.values(ds0.items).filter(x => x.id !== id && (keyN.some(k => [x.ten_vi, x.ten_en, x.ten_bd].map(trNorm).includes(k)) || (host && trHost(x.web) === host)));
    if (trung.length && !b.ep && !ds0.items[id]) return json({ trung: trung.map(x => ({ id: x.id, ten: x.ten_vi || x.ten_en, tap: x.tap, video: (x.video || []).length })) });
    const out = await trDsEdit(env, d => {
      const cur = d.items[id] || { id, tao: today(), video: [] };
      const taps = Object.values(d.items).map(x => x.tap || 0);
      Object.assign(cur, { qg, ten_vi, ten_en, ten_bd: String(b.ten_bd || '').trim().slice(0, 80), web,
        tap: Math.max(1, parseInt(b.tap, 10) || cur.tap || (taps.length ? Math.max(...taps) + 1 : 1)) });
      if (web !== curWeb) cur.web_kt = false;
      for (const k of ['dang', 'cho_duyet', 'can_cap_nhat']) if (b[k] !== undefined) cur[k] = !!b[k];
      d.items[id] = cur;
    }, `Trường: ${ten_vi || ten_en}`);
    return json({ ok: true, id, item: out.items[id] });
  }
  m = p.match(/^\/api\/truong\/((?:tw|kr)_[a-z0-9_]+)(\/.*)?$/);
  if (!m) return err('Không tìm thấy', 404);
  const id = m[1], sub = m[2] || '', it = ds0.items[id];
  if (!it) return err('Chưa có trường này trong danh sách', 404);
  if (!sub && req.method === 'GET') {
    const [nc, kb, anh, viec] = await Promise.all([readJson(env, `truong/${id}/nghien_cuu.json`), readJson(env, `truong/${id}/kich_ban.json`), trAnh(env, id), trJobStatus(env, id)]);
    return json({ viec, item: { ...it, trang_thai: trStatus(it) }, nghien_cuu: nc.data && nc.data.muc ? nc.data : null, kich_ban: kb.data && kb.data.script ? kb.data : null, anh });
  }
  if (sub === '/viec' && req.method === 'GET') return json(await trJobStatus(env, id));
  if (sub === '/xoa' && req.method === 'POST') {
    await trDsEdit(env, d => { delete d.items[id]; }, `Bỏ trường ${id} khỏi danh sách`);
    return json({ ok: true });
  }
  if (sub === '/nghien-cuu' && req.method === 'POST') {
    const b = await req.json().catch(() => ({}));
    const cur = await readJson(env, `truong/${id}/nghien_cuu.json`);
    if (cur.data && cur.data.muc && !b.lam_lai) return json({ ...cur.data, tu_bo_nho: true });    // đã có: không gọi AI lại (đỡ tốn)
    if (!env.CLAUDE_KEY) return err('Chưa cài khoá Claude (cần để AI tự lên mạng kiểm chứng).');
    return trStart(env, ctx, id, 'nghien_cuu', b);
  }
  if (sub === '/tim-anh' && req.method === 'GET') {
    const [found, have] = await Promise.all([trFindImages(it.web), trAnh(env, id)]);
    const got = new Set(have.map(x => x.url_anh).filter(Boolean));
    return json({ pages: found.pages, items: found.items.filter(x => !got.has(x.url)) });
  }
  if (sub === '/anh' && req.method === 'POST') {             // lưu 1 ảnh vào kho của trường (từ link tìm được hoặc tải lên)
    const b = await req.json();
    const cd = TR_CHU_DE.find(x => x[0] === b.chu_de) || ['khac', String(b.chu_de || 'ảnh').slice(0, 40)];
    let data = b.data || '', type = /png/.test(b.type || '') ? 'png' : 'jpg';
    if (!data && b.url) {
      if (!/^https?:\/\//i.test(b.url)) return err('Link ảnh không hợp lệ');
      const r = await fetch(b.url, { headers: { 'user-agent': 'Mozilla/5.0 (HDVideos)', referer: new URL(b.url).origin + '/' } });
      const ct = r.headers.get('content-type') || '';
      if (!r.ok || !/^image\/(jpeg|png|webp)/.test(ct)) return err('Không tải được ảnh (hoặc không phải ảnh JPG/PNG)');
      const buf = new Uint8Array(await r.arrayBuffer());
      if (buf.length < 12000 && cd[0] !== 'logo') return err('Ảnh quá nhỏ, chất lượng thấp');
      if (buf.length > 6e6) return err('Ảnh quá lớn (trên 6 MB)');
      if (/webp/.test(ct)) return err('Ảnh dạng WEBP: hãy tải về rồi bấm "Tải ảnh lên" (máy sẽ tự đổi sang JPG).');
      let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
      data = btoa(s); type = /png/.test(ct) ? 'png' : 'jpg';
    }
    if (!data) return err('Thiếu ảnh');
    const { data: meta } = await readJson(env, `engine/assets/truong/${id}/_anh.json`);
    const base = 'anh_' + slug(cd[1]);
    let k = base, n = 2;
    while (meta[k]) k = base + '_' + (n++);
    // logo giữ .png (hiện như hình vẽ); ảnh chụp lưu .jpg -> máy dựng hiện kiểu ảnh thật (khung, phóng nhẹ)
    if (cd[0] !== 'logo' && type === 'png' && !b.data) return err('Ảnh PNG: hãy tải về rồi bấm "Tải ảnh lên" (máy sẽ đổi sang JPG).');
    const file = k + '.' + (cd[0] === 'logo' ? type : 'jpg');
    await putFile(env, `engine/assets/truong/${id}/${file}`, data, `Ảnh trường ${id}: ${cd[1]}`);
    meta[k] = { ten: 'ảnh ' + cd[1] + (k === base ? '' : ' ' + (n - 1)), chu_de: cd[0], tu_khoa: [cd[1]].concat((b.tu_khoa || []).slice(0, 6)),
      url_anh: b.url || '', url_trang: String(b.trang || '').slice(0, 300), nguon: b.url ? trHost(b.url) : (b.nguon || 'Admin tải lên'),
      ban_quyen: String(b.ban_quyen || (b.url ? 'Ảnh từ website chính thức của trường, ghi nguồn khi đăng' : 'Admin xác nhận được phép dùng')).slice(0, 200),
      ngay: today(), w: parseInt(b.w, 10) || 0, h: parseInt(b.h, 10) || 0 };
    await trSave(env, `engine/assets/truong/${id}/_anh.json`, meta, `Ảnh trường ${id}: thông tin ${k}`);
    const cnt = (await trAnh(env, id)).length;
    await trDsEdit(env, d => { if (d.items[id]) d.items[id].anh = cnt; }, `Ảnh trường ${id}`);
    return json({ ok: true, file, ten: meta[k].ten });
  }
  m = sub.match(/^\/anh\/([a-z0-9_]+\.(?:jpg|png))\/xoa$/);
  if (m && req.method === 'POST') {
    const path = `engine/assets/truong/${id}/${m[1]}`;
    const cur = await ghJson(env, `/contents/${path}`);
    if (cur) await gh(env, `/contents/${path}`, { method: 'DELETE', body: JSON.stringify({ message: `Bỏ ảnh ${m[1]}`, sha: cur.sha, branch: 'main' }) });
    const { data: meta } = await readJson(env, `engine/assets/truong/${id}/_anh.json`);
    delete meta[m[1].replace(/\.(jpg|png)$/, '')];
    await trSave(env, `engine/assets/truong/${id}/_anh.json`, meta, `Bỏ ảnh ${m[1]}`);
    const cnt = (await trAnh(env, id)).length;
    await trDsEdit(env, d => { if (d.items[id]) d.items[id].anh = cnt; }, `Ảnh trường ${id}`);
    return json({ ok: true });
  }
  if (sub === '/kich-ban' && req.method === 'POST') {
    const b = await req.json();
    if (typeof b.script === 'string' && b.luu) {               // admin sửa tay rồi lưu
      const cur = (await readJson(env, `truong/${id}/kich_ban.json`)).data || {};
      const rec = { ...cur, script: b.script.slice(0, 20000), caption: String(b.caption ?? cur.caption ?? '').slice(0, 3000), ngay: today(), sua_tay: true };
      await trSave(env, `truong/${id}/kich_ban.json`, rec, `Sửa kịch bản ${id}`);
      await trDsEdit(env, d => { if (d.items[id]) d.items[id].kb = today(); }, `Kịch bản ${id}`);
      return json(rec);
    }
    const nc = (await readJson(env, `truong/${id}/nghien_cuu.json`)).data;
    if (!nc || !nc.muc) return err('Hãy bấm "Nghiên cứu và kiểm chứng" trước.');
    if (!env.CLAUDE_KEY && !env.GEMINI_KEY) return err('Chưa cài khoá AI');
    return trStart(env, ctx, id, 'kich_ban', b);
  }
  if (sub === '/video' && req.method === 'POST') {            // ghi lại mã video đã tạo cho trường (để cảnh báo trùng, theo dõi trạng thái)
    const b = await req.json();
    if (!/^[a-z0-9]{4,20}$/.test(b.job || '')) return err('Thiếu mã video');
    await trDsEdit(env, d => { const x = d.items[id]; if (x) { x.video = [...new Set([...(x.video || []), b.job])].slice(-20); x.cho_duyet = false; } }, `Video trường ${id}`);
    return json({ ok: true });
  }
  return err('Không tìm thấy', 404);
}

async function trDoResearch(env, id, b) {
  const it = (await trDs(env)).items[id];
  if (!it) throw new Error('Không còn trường này');
    const host = trHost(it.web);
    const domains = [...new Set([host, ...(host ? [host.split('.').slice(-3).join('.')] : []), ...(TR_NGUON[it.qg] || [])].filter(Boolean))];
    const user = `Trường: ${[it.ten_vi, it.ten_en, it.ten_bd].filter(Boolean).join(' / ')}\nWebsite chính thức: ${it.web || '(chưa có, hãy tự tìm)'}\nNgày hôm nay: ${today()}`;
    const out = await aiClaude(env, trResearchPrompt(it), user, true, domains,
      { maxUses: 10, maxTokens: 32000, retry: 'Bạn đã tra đủ. Trả lời NGAY một khối ```json đúng mẫu, mục nào chưa có nguồn thì để trống và kiem_chung=false.' });
    const jm = out.text.match(/```(?:json)?\s*([\s\S]*?)```/);
    let j = null;
    try { j = JSON.parse((jm ? jm[1] : out.text).replace(/\/\/[^\n"]*$/gm, '')); } catch { j = null; }
    if (!j) throw new Error('AI trả về sai định dạng, bấm nghiên cứu lại.');
    const muc = {};
    for (const [k] of TR_MUC) {
      const v = j[k] || {};
      const val = trClean(v.gia_tri);
      muc[k] = { gia_tri: val, nguon: String(v.nguon || '').trim(), nam_hoc: trClean(v.nam_hoc), kiem_chung: !!(val && v.kiem_chung) };
    }
    const rec = { ngay: today(), ten_vi: j.ten_vi || it.ten_vi, ten_en: j.ten_en || it.ten_en, ten_bd: j.ten_bd || it.ten_bd, muc, nguon: out.sources };
    await trSave(env, `truong/${id}/nghien_cuu.json`, rec, `Nghiên cứu: ${it.ten_vi || it.ten_en}`);
    await trDsEdit(env, d => { const x = d.items[id]; if (x) { x.nc = rec.ngay; x.web_kt = true;
      if (!x.tap) x.tap = Math.max(0, ...Object.values(d.items).map(y => y.tap || 0)) + 1; if (!x.ten_bd && rec.ten_bd) x.ten_bd = rec.ten_bd; if (!x.ten_en && rec.ten_en) x.ten_en = rec.ten_en; }
      d.phut_ai[today()] = (d.phut_ai[today()] || 0) + 1; }, `Nghiên cứu xong ${id}`);
  await aiRecord(env, 'admin', 'paid').catch(() => {});
  return rec;
}

async function trDoScript(env, id, b) {
  const it = (await trDs(env)).items[id];
  const nc = (await readJson(env, `truong/${id}/nghien_cuu.json`)).data;
  if (!it || !nc || !nc.muc) throw new Error('Thiếu hồ sơ nghiên cứu');
    const phut = Math.max(1, Math.min(10, Number(b.phut) || 3));
    const opt = { phut, phong_cach: ['tron', 'that', 've'].includes(b.phong_cach) ? b.phong_cach : 'tron', ty_le: parseInt(b.ty_le, 10) || 60 };
    const anh = await trAnh(env, id);
    const photos = opt.phong_cach === 've' ? [] : anh.map(x => x.ten);
    const sys = (await chatgptPrompt(env, lvPick(await lvAll(env), 'duhoc'))) + trScriptRules(it, opt, photos);
    const ho_so = { truong: { ten_vi: nc.ten_vi, ten_en: nc.ten_en, ten_bd: nc.ten_bd, website: it.web }, ngay_nghien_cuu: nc.ngay,
      muc: Object.fromEntries(Object.entries(nc.muc).filter(([, v]) => v.kiem_chung && v.gia_tri)
        .map(([k, v]) => [k, { gia_tri: trClean(v.gia_tri), nam_hoc: trClean(v.nam_hoc), nguon: v.nguon }])) };
    const user = `HỒ SƠ NGHIÊN CỨU (JSON, chỉ dùng các dữ kiện này):\n${JSON.stringify(ho_so, null, 1)}\n\nVideo: Tập ${String(it.tap || 1).padStart(3, '0')} series "Mỗi ngày một trường", dài khoảng ${phut} phút.`;
    let out;
    if (env.CLAUDE_KEY) {
      try { out = await aiClaude(env, sys, user, false, OFFICIAL, { maxTokens: 32000 }); }
      catch (e) {
        if (!/max_tokens/.test(e.message) || !env.GEMINI_KEY) throw e;
        out = { text: await aiGemini(env, sys, user), sources: [] };      // Claude nghĩ quá dài: chuyển sang Gemini
      }
    }
    else out = { text: await aiGemini(env, sys, user), sources: [] };
    const pr = parseAi(out.text);
    const urls = [...new Set([...(pr.srcTxt.match(/https?:\/\/[^\s)\]]+/g) || []), ...Object.values(nc.muc).map(v => v.nguon).filter(u => /^https?:/.test(u))])];
    const rec = { ngay: today(), ...opt, script: pr.script, caption: pr.caption, nguon: urls };
    await trSave(env, `truong/${id}/kich_ban.json`, rec, `Kịch bản ${id}`);
    await trDsEdit(env, d => { if (d.items[id]) d.items[id].kb = today(); }, `Kịch bản ${id}`);
  await aiRecord(env, 'admin', env.CLAUDE_KEY ? 'paid' : 'free').catch(() => {});
  return rec;
}

// ---- Việc chạy ngầm (nghiên cứu, viết kịch bản): giao cho Durable Object chạy bằng "alarm" (tối đa 15 phút),
// người dùng thoát trang / khoá máy vẫn chạy tiếp; trang hỏi trạng thái qua /api/truong/<mã>/viec
function trJobStub(env, id) { return env.AIPROXY.get(env.AIPROXY.idFromName('tr-job-' + id), { locationHint: env.AI_REGION || 'wnam' }); }
async function trStart(env, ctx, id, kind, b) {
  if (!env.AIPROXY) {                                       // chạy thử trên máy: làm luôn
    try { return json(await (kind === 'nghien_cuu' ? trDoResearch : trDoScript)(env, id, b)); } catch (e) { return err(e.message, 502); }
  }
  const r = await trJobStub(env, id).fetch('https://job/start', { method: 'POST', body: JSON.stringify({ kind, id, b }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return err(d.error || 'Không bắt đầu được', r.status);
  return json({ dang_chay: true, kind, ...d });
}
async function trJobStatus(env, id) {
  if (!env.AIPROXY) return { state: '' };
  const r = await trJobStub(env, id).fetch('https://job/status');
  return r.ok ? r.json() : { state: '' };
}
async function trJobRun(env, job) {
  return (job.kind === 'nghien_cuu' ? trDoResearch : trDoScript)(env, job.id, job.b || {});
}

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
        generationConfig: { maxOutputTokens: 32768 } }),
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
async function aiClaude(env, sys, user, search = true, domains = OFFICIAL, opt = {}) {
  const tool = { type: 'web_search_20250305', name: 'web_search', max_uses: opt.maxUses || 4, ...(domains ? { allowed_domains: domains } : {}) };
  let useDomains = !!domains, stop = '', diag = [];
  const blocks = [];                                   // toàn bộ nội dung trợ lý (kể cả các lượt tạm dừng)
  const call = async (messages, extra = {}) => {
    for (let k = 0; k < 2; k++) {
      const r = await aiFetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-api-key': env.CLAUDE_KEY, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model: 'claude-sonnet-5-5', max_tokens: opt.maxTokens || 16000, system: sys, messages,
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
      { role: 'user', content: opt.retry || 'Bạn đã tra đủ. Hãy viết NGAY kịch bản theo đúng PHẦN C (khối ``` kịch bản, CAPTION, NGUỒN), không tìm thêm.' }],
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
      tpl: info.tpl || '', ab: info.ab || '', lv: info.lv || '', abg: info.abg || '', fmt: info.fmt || '',
      missing: Array.isArray(info.thieu_hinh) ? info.thieu_hinh.slice(0, 30) : [], batch: info.batch || '',
      cover: (r.assets || []).some(a => a.name === 'bia.jpg'),
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

// ---- LĨNH VỰC (du học, ngói màu...): mỗi lĩnh vực có tên thương hiệu, logo, chữ trên bút, câu lệnh AI, kho hình riêng
const LV_FILE = 'engine/linhvuc.json';
const LV_ID = /^[a-z][a-z0-9]{1,15}$/;
const LV_KEYS = ['ten', 'slogan', 'nganh', 'khach', 'but', 'hotline', 'hashtag', 'luu_y', 've'];
async function lvAll(env) {
  const { data } = await readJson(env, LV_FILE);
  const d = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  if (!d.duhoc) d.duhoc = { ten: 'Du Học Hải Dương', slogan: 'Định Hướng Tương Lai', nganh: 'du học Đài Loan và Hàn Quốc', khach: 'học sinh và phụ huynh' };
  return d;
}
function lvPick(all, id) {
  const k = LV_ID.test(id || '') && all[id] ? id : 'duhoc';
  const c = all[k] || {};
  return { ...c, id: k, kho: k === 'duhoc' ? 'kho' : (/^kho_[a-z0-9]+$/.test(c.kho || '') ? c.kho : 'kho_' + k) };
}
async function lvOf(env, url, b) {
  return lvPick(await lvAll(env), (b && b.lv) || url.searchParams.get('lv') || 'duhoc');
}
// Câu lệnh chung (viết cho du học) -> đổi tên thương hiệu, bỏ chữ riêng của du học
function lvText(lv, s) {
  if (!lv || lv.id === 'duhoc') return s;
  return s.replace(/trung tâm tư vấn du học Du Học Hải Dương \(du học Đài Loan và Hàn Quốc\)/g, `${lv.ten} (${lv.nganh})`)
    .replace(/trung tâm Du Học Hải Dương \(du học Đài Loan, Hàn Quốc\)/g, `${lv.ten} (${lv.nganh})`)
    .replace(/học sinh và phụ huynh Việt Nam/g, lv.khach || 'khách hàng')
    .replace(/Du Học Hải Dương/g, lv.ten)
    .replace(/trang CHÍNH THỨC|trang chính thức/g, 'nguồn tin cậy (nhà sản xuất, tiêu chuẩn, cơ quan nhà nước)')
    .replace(/điều kiện visa/g, 'thông số kỹ thuật').replace(/"tùy trường"/g, '"tùy công trình"')
    .replace(/bao đậu visa, đi làm kiếm nhiều tiền/g, 'cam kết tuyệt đối, rẻ nhất thị trường')
    .replace(/của trung tâm/g, 'của chúng tôi').replace(/du học Đài Loan tháng 12/g, (lv.goi_y && lv.goi_y[0]) || lv.nganh || '');
}
// Ảnh trong kho của lĩnh vực: du học = kho chung; lĩnh vực khác = kho riêng + một số hình dùng chung
async function khoItems(env, lv) {
  const png = f => f.name.endsWith('.png') && !f.name.startsWith('_');
  const nm = f => f.name.slice(0, -4).replace(/_/g, ' ');
  if (!lv || lv.id === 'duhoc') return (await listDir(env, 'engine/assets/kho')).filter(png).map(f => ({ file: f.name, name: nm(f), url: '/img/kho/' + f.name }));
  const [own, chung] = await Promise.all([listDir(env, 'engine/assets/' + lv.kho), readJson(env, 'engine/assets/kho/_chung.json')]);
  const mine = own.filter(png).map(f => ({ file: f.name, name: nm(f), url: `/img/khod/${lv.kho}/${f.name}` }));
  const have = new Set(mine.map(x => x.name));
  const shared = (Array.isArray(chung.data) ? chung.data : []).map(f => ({ name: f }))
    .filter(f => /^[a-z0-9_]+\.png$/.test(f.name) && !have.has(nm(f))).map(f => ({ file: f.name, name: nm(f), url: '/img/kho/' + f.name, chung: true }));
  return mine.concat(shared);
}
function svgLogo(lv) {
  const e = x => String(x || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return new Response(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect x="16" y="16" width="480" height="480" rx="90" fill="#fff" stroke="#1946aa" stroke-width="20"/>
<text x="256" y="250" font-family="Arial,sans-serif" font-weight="700" font-size="64" text-anchor="middle" fill="#1946aa">${e((lv.ten || '').split(' ').slice(0, 2).join(' '))}</text>
<text x="256" y="330" font-family="Arial,sans-serif" font-weight="700" font-size="64" text-anchor="middle" fill="#c83c1e">${e((lv.ten || '').split(' ').slice(2).join(' '))}</text></svg>`,
    { headers: { 'content-type': 'image/svg+xml', 'cache-control': 'private, max-age=300' } });
}
async function lvLogo(req, env, ctx, url) {
  const id = url.searchParams.get('lv') || '';
  if (!id || id === 'duhoc' || !LV_ID.test(id)) return edgeCached(req, ctx, 3600, () => rawFile(env, 'engine/assets/logo.png', 'image/png'));
  const r = await gh(env, `/contents/engine/assets/lv/${id}/logo.png`, { headers: { accept: 'application/vnd.github.raw' } });
  if (r.ok) return new Response(r.body, { headers: { 'content-type': 'image/png', 'cache-control': 'private, max-age=600' } });
  return svgLogo(lvPick(await lvAll(env), id));
}

const LOGIN = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đăng nhập – Video Vẽ Tay</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f6fb;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d2433}
form{background:#fff;padding:28px 24px;border-radius:18px;box-shadow:0 8px 30px rgba(20,40,90,.10);width:min(340px,88vw)}
h1{font-size:20px;margin:0 0 4px;color:#1f46aa}p{margin:0 0 18px;color:#667;font-size:14px}
input,button{width:100%;box-sizing:border-box;font-size:17px;padding:13px 14px;border-radius:12px}
input{border:1.5px solid #d5dbe8;margin-bottom:12px}button{border:0;background:#1f46aa;color:#fff;font-weight:600}
.e{color:#d62632;font-size:14px;min-height:18px;margin-top:10px}</style></head><body>
<form id="f"><h1>Video Vẽ Tay</h1><p>Nhập mật khẩu</p>
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
      if (p === '/img/logo') return lvLogo(req, env, ctx, url);
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
        const lvj = await lvOf(env, url, b);
        const job = {
          lv: lvj.id,
          truong: admin && /^(tw|kr)_[a-z0-9_]{2,40}$/.test(b.truong || '') ? b.truong : '',
          name: (b.name || '').slice(0, 80), script, voice: b.voice || 'vieneu_nam', vieneu_voice: b.vieneu_voice || '',
          character: b.character || 'auto', label: (b.label || '').slice(0, 30), hotline: (b.hotline || '').slice(0, 40),
          auto: b.auto !== false, logo: b.logo !== false, rate: Math.max(-30, Math.min(30, parseInt(b.rate || 0, 10) || 0)),
          by: (b.by || '').slice(0, 40),
          who: slug(b.by || ''),
          pen: Math.max(0, Math.min(3, Number(b.pen ?? 1) || 0)),
          bg: /^[a-z_]{2,20}$/.test(b.bg || '') ? b.bg : 'trang',
          fmt: ['doc', 'ngang', 'vuong', 'doc45'].includes(b.fmt) ? b.fmt : 'doc',
          subs: b.subs === 'noibat' ? 'noibat' : !!b.subs,
          sfx: b.sfx !== false, punch: b.punch !== false, emph: b.emph !== false, pop: b.pop !== false,
          stroke: b.stroke !== false,
          trans: ['xoa', 'lia', 'xen', 'bang', 'bay'].includes(b.trans) ? b.trans : 'xen',
          tsnd: ['giay', 'vut', 'tat'].includes(b.tsnd) ? b.tsnd : 'giay',
          reveal: ['quet', 'loang'].includes(b.reveal) ? b.reveal : 'net',
          hook: b.hook !== false,
          cam: b.cam !== false,
          tpl: /^[a-z0-9_]{1,30}$/.test(b.tpl || '') ? b.tpl : '',
          ab: ['A', 'B'].includes(b.ab) ? b.ab : '',
          abg: /^[a-z0-9]{1,24}$/.test(b.abg || '') ? b.abg : '',
          preview: !!b.preview,
          batch: /^[a-z0-9]{1,24}$/.test(b.batch || '') ? b.batch : '',
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
      { const tr = await trRoute(req, env, ctx, url, p, admin); if (tr) return tr; }
      if (p === '/api/list') {
        const L = await listVideos(env), q = url.searchParams.get('lv') || 'duhoc';
        L.items = L.items.filter(x => (x.lv || 'duhoc') === q);
        return json(L);
      }
      if (p === '/api/linhvuc' && req.method === 'GET') {
        const all = await lvAll(env);
        return json({ items: Object.keys(all).map(id => { const c = lvPick(all, id); const o = { id, goi_y: c.goi_y || [] }; LV_KEYS.forEach(k => { o[k] = c[k] == null ? '' : c[k]; }); return o; }) });
      }
      if (p === '/api/linhvuc' && req.method === 'POST') {
        if (!admin) return err(ADMIN_ONLY, 403);
        const b = await req.json();
        const id = String(b.id || '').trim();
        if (!LV_ID.test(id)) return err('Mã lĩnh vực chỉ gồm chữ thường không dấu và số, 2–16 ký tự (ví dụ: noithat)');
        if (!String(b.ten || '').trim()) return err('Hãy nhập tên thương hiệu');
        for (let i = 0; i < 3; i++) {
          const { data, sha } = await readJson(env, LV_FILE);
          const all = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
          const cur = all[id] || (id === 'duhoc' ? {} : { kho: 'kho_' + id });
          for (const k of LV_KEYS) if (b[k] !== undefined) cur[k] = String(b[k]).slice(0, k === 'luu_y' || k === 've' ? 2000 : 200).trim();
          if (Array.isArray(b.goi_y)) cur.goi_y = b.goi_y.map(x => String(x).trim().slice(0, 120)).filter(Boolean).slice(0, 20);
          all[id] = cur;
          const bytes = new TextEncoder().encode(JSON.stringify(all, null, 1) + '\n');
          let bin = ''; bytes.forEach(x => { bin += String.fromCharCode(x); });
          const body = { message: `Lĩnh vực: ${cur.ten || id}`, content: btoa(bin), branch: 'main' };
          if (sha) body.sha = sha;
          const r = await gh(env, `/contents/${LV_FILE}`, { method: 'PUT', body: JSON.stringify(body) });
          if (r.ok) return json({ ok: true });
        }
        return err('Không lưu được, thử lại', 502);
      }
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
      if (m) return edgeCached(req, ctx, 86400, () => rawFile(env, `engine/assets/nen/${m[1]}.jpg`, 'image/jpeg'));
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
        const lv = await lvOf(env, url);
        const [items, moi] = await Promise.all([khoItems(env, lv), listDir(env, 'engine/assets/kho_moi')]);
        const pre = lv.kho + '__';
        const pend = moi.map(f => f.name).filter(n => !n.startsWith('.'));
        return json({
          items, lv: lv.id,
          pending: lv.id === 'duhoc' ? pend.filter(n => !/^kho_[a-z0-9]+__/.test(n)) : pend.filter(n => n.startsWith(pre)).map(n => n.slice(pre.length)),
        });
      }
      if (p === '/api/kho/keys') {        // tên + từ khoá của ảnh trong Kho (để ẩn 'hình còn thiếu' đã có hình)
        const lv = await lvOf(env, url);
        const [items, meta, meta2] = await Promise.all([khoItems(env, lv), readJson(env, 'engine/assets/kho/_tu_khoa.json'),
          lv.id === 'duhoc' ? { data: {} } : readJson(env, `engine/assets/${lv.kho}/_tu_khoa.json`)]);
        const names = items.map(x => x.name);
        const ok = new Set(items.map(x => x.file.slice(0, -4)));
        const keys = [];
        for (const [f, v] of Object.entries({ ...(meta.data || {}), ...(meta2.data || {}) })) {
          if (lv.id !== 'duhoc' && !ok.has(f)) continue;
          if (v.ten) keys.push(v.ten); (v.tu_khoa || []).forEach(k => keys.push(k));
        }
        return json({ names, keys });
      }
      if (p === '/api/kho' && req.method === 'POST') {
        const b = await req.json();
        const lv = await lvOf(env, url, b);
        const name = slug(b.name);
        if (!name) return err('Hãy đặt tên ảnh (ví dụ: ký túc xá)');
        if (!b.data) return err('Thiếu ảnh');
        await putFile(env, `engine/assets/kho_moi/${lv.id === 'duhoc' ? '' : lv.kho + '__'}${name}.png`, b.data, `Kho${lv.id === 'duhoc' ? '' : ' ' + lv.ten}: thêm ${name}`);
        return json({ ok: true, name });
      }
      m = p.match(/^\/api\/kho\/([a-z0-9_]+\.png)\/delete$/);
      if (m && req.method === 'POST') {
        const b = await req.json().catch(() => ({}));
        const lv = await lvOf(env, url, b);
        const cur = await ghJson(env, `/contents/engine/assets/${lv.kho}/${m[1]}`);
        if (cur) await gh(env, `/contents/engine/assets/${lv.kho}/${m[1]}`, { method: 'DELETE', body: JSON.stringify({ message: `Kho: xoá ${m[1]}`, sha: cur.sha, branch: 'main' }) });
        await caches.default.delete(new Request(new URL((lv.id === 'duhoc' ? '/img/kho/' : `/img/khod/${lv.kho}/`) + m[1], req.url).toString())).catch(() => {});
        return json({ ok: true });
      }
      m = p.match(/^\/img\/kho\/([a-z0-9_]+\.png)$/);
      if (m) return edgeCached(req, ctx, 21600, () => rawFile(env, `engine/assets/kho/${m[1]}`, 'image/png'));
      m = p.match(/^\/img\/khod\/(kho_[a-z0-9]+)\/([a-z0-9_]+\.png)$/);
      if (m) return edgeCached(req, ctx, 21600, () => rawFile(env, `engine/assets/${m[1]}/${m[2]}`, 'image/png'));

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
        const lvq = url.searchParams.get('lv') || '';
        if (lvq && lvq !== 'duhoc' && LV_ID.test(lvq)) {
          const r = await gh(env, `/contents/engine/assets/lv/${lvq}/nhanvat/${m[1]}`, { headers: { accept: 'application/vnd.github.raw' } });
          if (r.ok) return new Response(r.body, { headers: { 'content-type': 'image/png', 'cache-control': 'no-store' } });
        }
        const who = slug(url.searchParams.get('who') || '');
        if (who) {
          const r = await gh(env, `/contents/engine/assets/nhanvat_rieng/${who}/${m[1]}`, { headers: { accept: 'application/vnd.github.raw' } });
          if (r.ok) return new Response(r.body, { headers: { 'content-type': 'image/png', 'cache-control': 'no-store' } });
        }
        return rawFile(env, `engine/assets/nhanvat/${m[1]}`, 'image/png');
      }
      if (p === '/img/logo') return lvLogo(req, env, ctx, url);
      if (p === '/api/nhanvat' && req.method === 'GET') {
        const lvq = url.searchParams.get('lv') || '';
        if (lvq && lvq !== 'duhoc' && LV_ID.test(lvq)) {
          const mine = (await listDir(env, `engine/assets/lv/${lvq}/nhanvat`)).map(f => f.name).filter(n => NVF.test(n));
          const pending = (await listDir(env, 'engine/assets/nhanvat_moi')).map(f => f.name).filter(n => n.startsWith('lv_' + lvq + '__'));
          return json({ mine, pending, lv: lvq });
        }
        const who = slug(url.searchParams.get('who') || '');
        const mine = who ? (await listDir(env, `engine/assets/nhanvat_rieng/${who}`)).map(f => f.name).filter(n => NVF.test(n)) : [];
        const pending = (await listDir(env, 'engine/assets/nhanvat_moi')).map(f => f.name).filter(n => !n.startsWith('.'));
        return json({ mine, pending: pending.filter(n => who ? n.startsWith(who + '__') : !n.includes('__')) });
      }
      if (p === '/api/nhanvat' && req.method === 'POST') {
        const b = await req.json();
        if (!['anh', 'chi'].includes(b.gender) || !['chao', 'chi', 'like'].includes(b.pose) || !b.data) return err('Thiếu thông tin');
        if (b.lv && b.lv !== 'duhoc' && LV_ID.test(b.lv)) {
          if (!admin) return err(ADMIN_ONLY, 403);
          await putFile(env, `engine/assets/nhanvat_moi/lv_${b.lv}__${b.gender}_${b.pose}.png`, b.data, `Nhân vật ${b.lv}: thay ${b.gender}_${b.pose}`);
          return json({ ok: true });
        }
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
        const lv = await lvOf(env, url, b);
        if (lv.id !== 'duhoc') {
          await putFile(env, `engine/assets/lv/${lv.id}/logo.png`, b.data, `Đổi logo ${lv.ten}`);
          return json({ ok: true });
        }
        await putFile(env, 'engine/assets/logo.png', b.data, 'Đổi logo');
        await caches.default.delete(new Request(new URL('/img/logo', req.url).toString())).catch(() => {});
        return json({ ok: true });
      }

      // ---- AI viết kịch bản từ chủ đề
      if (p === '/api/ai/config' && req.method === 'GET') {
        const { data } = await readJson(env, AI_FILE);
        const cfg = { ...AI_DEF, ...(data.config || {}) };
        return json({ ...cfg, has_free: !!env.GEMINI_KEY, has_paid: !!env.CLAUDE_KEY, has_link: !!env.SUPADATA_KEY, admin, today: admin ? (data.use || {})[today()] || {} : undefined });
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
        const remix = b.task === 'remix';
        const convert = b.task === 'convert' || fix;
        const duration = fix ? 'full' : Object.prototype.hasOwnProperty.call(AI_LENGTHS, b.duration) ? b.duration : convert ? 'full' : 'quick';
        const content = String(b.content || '').trim();
        if (convert && content.length > 12000) return err('Nội dung dài hơn 12.000 ký tự. Hãy chia thành các phần để AI không bỏ sót nội dung.');
        const issues = (Array.isArray(b.issues) ? b.issues : []).slice(0, 12).map(x => String(x).slice(0, 200));
        if (remix && content.length > 12000) return err('Lời video dài quá, hãy dán đoạn ngắn hơn.');
        if (remix && content.length < 20) return err('Chưa có lời video. Dán link hoặc dán lời vào ô.');
        const topic = convert ? 'chuyển nội dung' : remix ? 'viết lại từ video tham khảo' : String(b.topic || '').trim().slice(0, 400);
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
        const lv = await lvOf(env, url, b);
        const sys = (await chatgptPrompt(env, lv)) + lvText(lv, common + (fix ? AI_FIX : convert ? (duration === 'full' ? AI_CONVERT : AI_CONVERT_TIMED)
          : remix ? AI_REMIX + (mode === 'paid' ? AI_REMIX_PAID : AI_REMIX_FREE) : mode === 'paid' ? AI_PAID : AI_FREE) + durationRule
          + (b.style === 'bay' ? AI_BAY : ''));
        const user = fix ? `KỊCH BẢN CẦN SỬA:\n\`\`\`\n${content}\n\`\`\`\n\nCÁC LỖI CẦN SỬA:\n${issues.map((x, i) => (i + 1) + '. ' + x).join('\n')}`
          : convert ? `NỘI DUNG CỦA TÔI (chuyển thành kịch bản, giữ nguyên ý và số liệu):\n${content}`
          : remix ? (b.focus ? `CHỈ VIẾT VỀ: ${String(b.focus).slice(0, 200)}\n\n` : '') + `LỜI VIDEO CỦA KÊNH KHÁC (chỉ học ý tưởng, viết mới hoàn toàn, không chép câu):\n${content}` + (extra ? `\n\nTHÔNG TIN THÊM (của trung tâm, dùng đúng như vậy):\n${extra}` : '')
          : `CHỦ ĐỀ: ${topic}` + (extra ? `\n\nTHÔNG TIN THÊM (của trung tâm, dùng đúng như vậy):\n${extra}` : '');
        let out, res, copy = null;
        try {
          out = mode === 'paid' ? await aiClaude(env, sys, user, !convert, lv.id === 'duhoc' ? OFFICIAL : null) : await aiGemini(env, sys, user);
          res = parseAi(out.text);
          if (remix && res.script) {
            copy = copyScore(content, res.script);
            if ((copy.pct > 8 || copy.longest >= 10) && env.GEMINI_KEY) try {   // còn giống bản gốc -> bắt viết lại 1 lần bằng Gemini
              const again = await aiGemini(env, sys, user + `\n\nBẢN TRƯỚC CÒN GIỐNG BÀI GỐC ${copy.pct}% (cụm giống dài ${copy.longest} chữ). VIẾT LẠI, dùng câu chữ của riêng bạn, giữ nguyên các số liệu đã kiểm chứng trong bản này:\n\`\`\`\n${res.script}\n\`\`\``);
              const r2 = parseAi(again.text), c2 = r2.script ? copyScore(content, r2.script) : null;
              if (c2 && c2.pct <= copy.pct) { res = { ...r2, srcTxt: res.srcTxt || r2.srcTxt }; copy = c2; }
            } catch (e) { /* giữ bản đầu */ }
          }
        } catch (e) { return err(String(e.message || e), 502); }
        if (res.script.length > 20000) return err('Kịch bản vượt giới hạn 20.000 ký tự của bộ dựng. Hãy chia bài thành các phần.', 422);
        if (!res.script) return err('AI chưa viết được kịch bản, hãy thử lại hoặc đổi cách nói chủ đề.', 502);
        const urls = [...res.srcTxt.matchAll(/https?:\/\/[^\s)\]]+/g)].map(x => ({ url: x[0], title: '' }));
        const sources = [...out.sources];
        for (const u of urls) if (!sources.some(x => x.url === u.url)) sources.push(u);
        if (!fix) {                                                    // vòng tự sửa không tính lượt
          const rec = aiRecord(env, admin ? 'admin' : who, mode);
          if (ctx && ctx.waitUntil) ctx.waitUntil(rec); else await rec;
        }
        return json({ script: res.script, caption: res.caption, sources: convert ? [] : sources.slice(0, 8), mode, convert, duration, copy,
          verified: !convert && mode === 'paid' && sources.length > 0, used: used + 1, limit: admin ? null : limit });
      }
      if (p === '/api/ai/split' && req.method === 'POST') {
        // Lời video dài -> tách thành nhiều chủ đề video ngắn (Gemini miễn phí, không tính lượt)
        const b = await req.json();
        const content = String(b.content || '').trim().slice(0, 12000);
        if (content.length < 200) return err('Lời video ngắn, không cần tách. Bấm VIẾT LẠI là được.');
        if (!env.GEMINI_KEY) return err('Chưa gắn khoá Gemini. Admin xem hướng dẫn trong mục Cài đặt.');
        const lv = await lvOf(env, url, b);
        const sys = lvText(lv, `Bạn lên kế hoạch video ngắn (30–60 giây) cho trung tâm Du Học Hải Dương (du học Đài Loan, Hàn Quốc), khán giả là học sinh và phụ huynh Việt Nam.
Tin nhắn là LỜI MỘT VIDEO DÀI CỦA KÊNH KHÁC (có thể là bản dịch máy, lộn xộn). Hãy tách thành 2 đến 8 chủ đề video ngắn, mỗi chủ đề đúng MỘT ý, viết bằng tiếng Việt, bằng lời của bạn (không chép câu gốc), hấp dẫn kiểu "sai lầm", "cảnh báo", "bạn có biết", "checklist".
Bỏ phần quảng cáo, tên trung tâm/kênh của họ, lời hứa kiểu môi giới. Ý nào trùng nhau thì gộp. Không đưa con số vào tên chủ đề.
CHỈ trả về JSON: [{"topic":"tên chủ đề video, dưới 15 chữ"}]`);
        let out;
        try { out = await aiGemini(env, sys, content); } catch (e) { return err(String(e.message || e), 502); }
        const txt = out.text.replace(/```(json)?/g, '');
        let arr = [];
        try { arr = JSON.parse(txt.slice(txt.indexOf('['), txt.lastIndexOf(']') + 1)); } catch (e) { arr = []; }
        const ideas = (Array.isArray(arr) ? arr : []).map(x => String((x && x.topic) || x || '').trim().slice(0, 160)).filter(x => x.length > 5).slice(0, 8);
        if (!ideas.length) return err('AI chưa tách được, hãy thử lại.', 502);
        return json({ ideas });
      }
      if (p === '/api/ai/transcript' && req.method === 'POST') {
        const b = await req.json();
        const link = String(b.url || '').trim();
        if (!/^https?:\/\/([a-z0-9-]+\.)*(tiktok\.com|facebook\.com|fb\.watch|youtube\.com|youtu\.be|instagram\.com|x\.com|twitter\.com)\//i.test(link))
          return err('Hãy dán link video TikTok, Facebook hoặc YouTube');
        if (!env.SUPADATA_KEY) return err('Chưa gắn khoá lấy lời video (Supadata). Hãy dán lời video vào ô bên dưới, hoặc nhờ admin gắn khoá.');
        try { return json(await getTranscript(env, link)); }
        catch (e) { return err(String(e.message || e), 502); }
      }
      if (p === '/api/phatam' && req.method === 'GET') {
        const { data } = await readJson(env, 'engine/phat_am.json');
        return json({ items: data || {} });
      }
      if (p === '/api/phatam' && req.method === 'POST') {
        if (!admin) return err(ADMIN_ONLY, 403);
        const b = await req.json();
        const out = {};
        for (const [k, v] of Object.entries(b.items || {}).slice(0, 300)) {
          const kk = String(k).trim().slice(0, 40), vv = String(v).trim().slice(0, 80);
          if (kk && vv) out[kk] = vv;
        }
        const txt = JSON.stringify(out, null, 2) + '\n';
        const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(txt)));
        await putFile(env, 'engine/phat_am.json', b64, 'Từ điển phát âm: cập nhật');
        return json({ ok: true, n: Object.keys(out).length });
      }
      m = p.match(/^\/bia\/([a-z0-9]+)$/);
      if (m) {
        const rel = await ghJson(env, `/releases/tags/job-${m[1]}`);
        const a = rel && (rel.assets || []).find(x => x.name === 'bia.jpg');
        if (!a) return new Response('Video này chưa có ảnh bìa', { status: 404 });
        const r = await gh(env, `/releases/assets/${a.id}`, { headers: { accept: 'application/octet-stream' } });
        const h = { 'content-type': 'image/jpeg', 'cache-control': 'private, max-age=86400' };
        if (url.searchParams.get('dl') === '1') h['content-disposition'] = `attachment; filename="anh_bia_${m[1]}.jpg"`;
        return new Response(r.body, { headers: h });
      }
      if (p === '/api/ai/ideas' && req.method === 'POST') {
        // Gợi ý danh sách chủ đề cho chế độ làm hàng loạt (Gemini miễn phí, không tính lượt)
        const b = await req.json();
        const theme = String(b.theme || '').trim().slice(0, 300);
        if (theme.length < 3) return err('Hãy nhập hướng chủ đề, ví dụ: du học Đài Loan tháng 12');
        if (!env.GEMINI_KEY) return err('Chưa gắn khoá Gemini. Admin xem hướng dẫn trong mục Cài đặt.');
        const n = Math.max(3, Math.min(30, parseInt(b.count || 10, 10) || 10));
        const done = (Array.isArray(b.done) ? b.done : []).slice(0, 80).map(x => String(x).slice(0, 80));
        const lv = await lvOf(env, url, b);
        const sys = lvText(lv, `Bạn là người lên lịch nội dung video ngắn (TikTok/Facebook Reels, 30–60 giây) cho trung tâm tư vấn du học Du Học Hải Dương (du học Đài Loan và Hàn Quốc), khán giả là học sinh và phụ huynh Việt Nam.
Hãy đề xuất đúng ${n} chủ đề video, mỗi chủ đề là MỘT ý cụ thể, hấp dẫn, dễ làm thành video vẽ tay.
Trộn đều các dạng: sai lầm thường gặp, cảnh báo, so sánh, checklist, quy trình từng bước, "bạn có biết", trả lời câu hỏi khách hay hỏi.
Không bịa con số, mức phí hay quy định cụ thể trong tên chủ đề. Không trùng các chủ đề đã làm.
CHỈ trả về JSON, dạng: [{"topic":"...","dang":"canh_bao|sai_lam|so_sanh|checklist|quy_trinh|ban_co_biet|hoi_dap"}]`);
        const user = `HƯỚNG CHỦ ĐỀ: ${theme}` + (done.length ? `\n\nCHỦ ĐỀ ĐÃ LÀM (không lặp lại):\n- ${done.join('\n- ')}` : '');
        let out;
        try { out = await aiGemini(env, sys, user); } catch (e) { return err(String(e.message || e), 502); }
        const txt = out.text.replace(/```(json)?/g, '');
        let arr = [];
        try { arr = JSON.parse(txt.slice(txt.indexOf('['), txt.lastIndexOf(']') + 1)); } catch (e) { arr = []; }
        const ideas = (Array.isArray(arr) ? arr : []).map(x => ({ topic: String((x && x.topic) || x || '').trim().slice(0, 160), dang: String((x && x.dang) || '').slice(0, 20) }))
          .filter(x => x.topic.length > 5).slice(0, n);
        if (!ideas.length) return err('AI chưa gợi ý được, hãy thử lại hoặc nói rõ hướng chủ đề hơn.', 502);
        return json({ ideas });
      }
      if (p === '/api/names') {
        const lv = await lvOf(env, url);
        const [hv, kho] = await Promise.all([
          gh(env, '/contents/engine/TEN_HINH.txt', { headers: { accept: 'application/vnd.github.raw' } }).then(r => r.ok ? r.text() : ''),
          khoItems(env, lv),
        ]);
        return json({ hv: hv.split('\n').map(s => s.trim()).filter(Boolean), kho: kho.map(x => x.name) });
      }
      if (p === '/api/text') {
        const f = { chatgpt: 'engine/LENH_CHATGPT.txt', anh: 'engine/KHO_HINH_CAU_LENH.txt', luoi: 'engine/KHO_HINH_LUOI.txt' }[url.searchParams.get('f')];
        if (!f) return err('Không có');
        if (url.searchParams.get('f') === 'chatgpt') {
          const txt = await chatgptPrompt(env, await lvOf(env, url));
          return new Response(txt, { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
        }
        return rawFile(env, f, 'text/plain; charset=utf-8');
      }
      return new Response('Không tìm thấy', { status: 404 });
    } catch (e) {
      return err(String(e && e.message || e), 500);
    }
  },
};
