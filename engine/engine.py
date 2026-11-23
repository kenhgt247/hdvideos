# -*- coding: utf-8 -*-
"""Bộ máy dựng video vẽ tay – Du Học Hải Dương."""
import json, math, os, random, re, shutil, subprocess, sys, tempfile, unicodedata, wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets')
W, H, FPS = 1080, 1920, 30
PAPER = (253, 252, 247)
INK = (34, 36, 48)
COLORS = {'den': INK, 'xanh': (32, 70, 170), 'do': (214, 38, 50), 'cam': (238, 128, 20),
          'xam': (100, 104, 118), 'xanh la': (30, 140, 70), 'tim': (130, 60, 170)}
BLUE, RED, ORANGE, GREY = COLORS['xanh'], COLORS['do'], COLORS['cam'], COLORS['xam']
CPS = 0.034          # giây cho mỗi ký tự khi viết
GAP, ENTER, EXIT = 0.16, 0.35, 0.45
TOP_AREA = 400       # dưới logo góc trái
BOTTOM_AREA = 1460   # phía dưới bị caption TikTok/Reels che
ERASE = 0.9          # thời gian lau bảng khi chuyển cảnh
LCX, LMAXW = W / 2, 960   # cột nội dung (đổi khi có nhân vật đứng bên trái)

VOICES = {
    'hoaimy': 'vi-VN-HoaiMyNeural',
    'namminh': 'vi-VN-NamMinhNeural',
}

NOWIN = 0x08000000 if os.name == 'nt' else 0


class VideoError(Exception):
    pass


# ------------------------------------------------------------------ tiện ích
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which('ffmpeg')
        if exe:
            return exe
    raise VideoError('Không tìm thấy ffmpeg. Hãy chạy lại CAI_DAT.bat.')


def run_ff(args):
    p = subprocess.run([ffmpeg_exe(), '-y', '-loglevel', 'error'] + args,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NOWIN)
    if p.returncode != 0:
        raise VideoError('ffmpeg báo lỗi:\n' + p.stderr.decode('utf-8', 'ignore')[-800:])


def norm(s):
    s = s.replace('đ', 'd').replace('Đ', 'D')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s.lower()).strip()


def clamp(x):
    return max(0.0, min(1.0, x))


def eio(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def eo(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


# ------------------------------------------------------------------ tài nguyên
_fc = {}


def font(size):
    size = max(20, int(size))
    if size not in _fc:
        _fc[size] = ImageFont.truetype(os.path.join(ASSETS, 'PatrickHand-Regular.ttf'), size)
    return _fc[size]


def line_h(size):
    a, d = font(size).getmetrics()
    return a + d


def fit(text, size, maxw):
    while size > 30 and font(size).getlength(text) > maxw:
        size -= 2
    return int(size)


def load_logo(path):
    im = Image.open(path)
    has_alpha = im.mode in ('RGBA', 'LA') or 'transparency' in im.info
    im = im.convert('RGBA')
    if not has_alpha or np.asarray(im)[:, :, 3].min() > 250:
        rgb = np.asarray(im.convert('RGB')).astype(np.int32)
        al = np.clip((252 - rgb.min(axis=2)) * 255 // 40, 0, 255).astype(np.uint8)
        im.putalpha(Image.fromarray(al))
    bb = im.getbbox()
    return im.crop(bb) if bb else im


def scaled(im, w):
    return im.resize((int(w), int(im.height * w / im.width)), Image.LANCZOS)


def with_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel('A').point(lambda v: int(v * a)))
    return im


def make_paper():
    rng = np.random.default_rng(3)
    n = rng.normal(0, 2.2, (H, W, 1))
    return Image.fromarray(np.clip(np.array(PAPER)[None, None, :] + n, 0, 255).astype(np.uint8))


# ------------------------------------------------------------------ nét vẽ
class Txt:
    PAD = 14

    def __init__(self, text, size, color, cy, cx=W / 2, left=None, segs=None):
        f = font(size)
        asc, desc = f.getmetrics()
        segs = segs or [(text, color)]
        text = ''.join(t for t, _ in segs)
        tw = int(f.getlength(text)) + 4
        im = Image.new('RGBA', (tw + 2 * self.PAD, asc + desc + 2 * self.PAD), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        done = ''
        for part, c in segs:
            d.text((self.PAD + f.getlength(done), self.PAD), part, font=f, fill=c,
                   stroke_width=max(1, size // 45), stroke_fill=c)
            done += part
        self.im, self.cy, self.size = im, cy, size
        self.x = int(left - self.PAD) if left is not None else int(cx - im.width / 2)
        self.y = int(cy - im.height / 2)
        self.dur = max(0.3, len(text) * CPS)

    @property
    def left(self):
        return self.x + self.PAD

    @property
    def right(self):
        return self.x + self.im.width - self.PAD

    def draw(self, f, r):
        if r <= 0:
            return
        if r >= 1:
            f.paste(self.im, (self.x, self.y), self.im)
            return
        wv = int(self.im.width * r)
        if wv > 0:
            c = self.im.crop((0, 0, wv, self.im.height))
            f.paste(c, (self.x, self.y), c)

    def pos(self, r, t):
        return (self.left + (self.right - self.left) * clamp(r), self.cy + 10 * math.sin(t * 38))


class CharItem:
    """Nhân vật dẫn chuyện: vẽ nét đen từ trên xuống, rồi tô màu."""
    _cache = {}

    def __init__(self, path, cx, feet_y, height):
        key = (path, int(height))
        if key not in CharItem._cache:
            im = Image.open(path).convert('RGBA')
            im = im.resize((int(im.width * height / im.height), int(height)), Image.LANCZOS)
            a = np.asarray(im).astype(np.int32)
            mx, mn = a[:, :, :3].max(axis=2), a[:, :, :3].min(axis=2)
            la = np.where((mx < 75) & (mx - mn < 30) & (a[:, :, 3] > 0), a[:, :, 3], 0).astype(np.uint8)
            lines = Image.new('RGBA', im.size, (30, 30, 36, 0))
            lines.putalpha(Image.fromarray(la))
            CharItem._cache[key] = (im, lines)
        self.im, self.lines = CharItem._cache[key]
        self.x = int(cx - self.im.width / 2)
        self.y = int(feet_y - self.im.height)
        self.dur = 1.6

    def draw(self, f, r):
        if r <= 0:
            return
        if r >= 1:
            f.paste(self.im, (self.x, self.y), self.im)
            return
        rl = clamp(r / 0.6)
        if r > 0.6:
            col = with_alpha(self.im, clamp((r - 0.6) / 0.4))
            f.paste(col, (self.x, self.y), col)
        hh = int(self.lines.height * rl)
        if hh > 0:
            c = self.lines.crop((0, 0, self.lines.width, hh))
            f.paste(c, (self.x, self.y), c)

    def pos(self, r, t):
        w, h = self.im.width, self.im.height
        if r < 0.6:
            rl = clamp(r / 0.6)
            return (self.x + w * (0.5 + 0.4 * math.sin(rl * 60)), self.y + h * rl)
        return (self.x + w * (0.5 + 0.3 * math.sin(t * 9)), self.y + h * (0.45 + 0.2 * math.cos(t * 7)))


NV_DIR = os.path.join(ASSETS, 'nhanvat')


def char_path(gender, pose):
    p = os.path.join(NV_DIR, '%s_%s.png' % (gender, pose))
    return p if os.path.exists(p) else None


POSES = [('chao', 'Chào'), ('chi', 'Chỉ tay'), ('like', 'Like')]
GENDERS = [('anh', 'Anh tư vấn'), ('chi', 'Chị tư vấn')]


def remove_bg(src, tol=40, max_h=1300):
    """Tách nền trơn (trắng hoặc một màu) bằng cách loang từ mép ảnh. Trả về ảnh RGBA đã cắt sát."""
    im = Image.open(src)
    if im.mode in ('RGBA', 'LA') or 'transparency' in im.info:
        rgba = im.convert('RGBA')
        if np.asarray(rgba)[:, :, 3].min() < 250:      # ảnh đã có nền trong suốt
            bb = rgba.getbbox()
            out = rgba.crop(bb) if bb else rgba
            return _fit_h(out, max_h)
    rgb = im.convert('RGB')
    w, h = rgb.size
    if max(w, h) > 2400:
        k = 2400 / max(w, h)
        rgb = rgb.resize((int(w * k), int(h * k)), Image.LANCZOS)
        w, h = rgb.size
    work = rgb.copy()
    SENT = (255, 0, 254)
    border = [(x, 0) for x in range(0, w, 12)] + [(x, h - 1) for x in range(0, w, 12)] + \
             [(0, y) for y in range(0, h, 12)] + [(w - 1, y) for y in range(0, h, 12)]
    arr = np.asarray(rgb).astype(int)
    edge = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    bgc = np.median(edge, axis=0)
    for pt in border:
        px = work.getpixel(pt)
        if px != SENT and np.abs(np.array(px) - bgc).max() < tol:
            ImageDraw.floodfill(work, pt, SENT, thresh=tol)
    a = np.asarray(work)
    bg = (a[:, :, 0] == SENT[0]) & (a[:, :, 1] == SENT[1]) & (a[:, :, 2] == SENT[2])
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    try:
        from PIL import ImageFilter
        alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    except Exception:
        pass
    out = rgb.convert('RGBA')
    out.putalpha(alpha)
    bb = out.getbbox()
    if bb:
        out = out.crop(bb)
    return _fit_h(out, max_h)


def _fit_h(im, max_h):
    if im.height > max_h:
        im = im.resize((int(im.width * max_h / im.height), max_h), Image.LANCZOS)
    return im


def set_character_image(gender, pose, src):
    """Tách nền ảnh src và lưu làm nhân vật (giữ bản gốc lần đầu để khôi phục)."""
    os.makedirs(NV_DIR, exist_ok=True)
    backup = os.path.join(NV_DIR, '_goc')
    os.makedirs(backup, exist_ok=True)
    dst = os.path.join(NV_DIR, '%s_%s.png' % (gender, pose))
    if os.path.exists(dst) and not os.path.exists(os.path.join(backup, os.path.basename(dst))):
        shutil.copy2(dst, os.path.join(backup, os.path.basename(dst)))
    out = remove_bg(src)
    out.save(dst)
    CharItem._cache.clear()
    return dst


def restore_characters():
    backup = os.path.join(NV_DIR, '_goc')
    n = 0
    if os.path.isdir(backup):
        for f in os.listdir(backup):
            shutil.copy2(os.path.join(backup, f), os.path.join(NV_DIR, f))
            n += 1
    CharItem._cache.clear()
    return n


PROMPT_FILE = os.path.join(ASSETS, 'lenh_mau.txt')
PROMPT_NAMES = ['học sinh suy nghĩ chọn nước', 'học sinh và địa cầu', 'sinh viên kéo vali sân bay', 'lộ trình du học',
                'bộ hồ sơ xếp chồng', 'checklist hồ sơ', 'hộ chiếu mở', 'visa trong hộ chiếu', 'ảnh thẻ hồ sơ',
                'học bạ bằng bảng điểm', 'chứng chỉ ngoại ngữ', 'laptop đăng ký online', 'phỏng vấn visa', 'dấu approved',
                'đại sứ quán', 'lịch hẹn phỏng vấn', 'tòa nhà đại học', 'biểu tượng các ngành', 'tiền', 'nhận học bổng',
                'học bổng toàn phần', 'ống tiết kiệm', 'bảng chi tiêu hàng tháng', 'học tiếng hàn', 'học tiếng trung',
                'thẻ từ vựng', 'chuẩn bị vali', 'vé máy bay', 'tạm biệt gia đình', 'ký túc xá', 'căng tin trường',
                'thư viện', 'xe bus tàu điện', 'lễ tốt nghiệp', 'làm thêm quán cà phê', 'thực tập văn phòng',
                'sinh viên nhận lương', 'nhớ nhà', 'sốc văn hóa', 'cảnh báo', 'khiên', 'tư vấn viên với phụ huynh',
                'kế hoạch học tập', 'quốc kỳ hàn quốc', 'quốc kỳ đài loan', 'bản đồ hàn quốc', 'bản đồ đài loan',
                'món ăn hàn quốc', 'món ăn đài loan', 'cơ hội việc làm', 'hỏi', 'x', 'tích']


def chatgpt_prompt():
    """Câu lệnh cho ChatGPT, tự thêm tên các ảnh trong Kho hình."""
    try:
        tpl = open(PROMPT_FILE, encoding='utf-8-sig').read()
    except OSError:
        raise VideoError('Thiếu file assets/lenh_mau.txt')
    kho = [os.path.splitext(os.path.basename(p))[0].replace('_', ' ') for p in kho_index().values()]
    names = ', '.join(kho + PROMPT_NAMES)
    return tpl.replace('{HINH}', names)


def important_scene(sc):
    for txt, tags in sc['lines']:
        if not txt:
            continue
        letters = [c for c in txt if c.isalpha()]
        if any(k == 'num' for _, _, k in key_spans(txt)) or (letters and all(c.isupper() for c in letters)) \
                or txt.rstrip().endswith('!'):
            return True
    return False


def resolve_gender(opts):
    ch = (opts or {}).get('character', 'auto') or 'auto'
    if ch in ('anh', 'chi', 'none'):
        return None if ch == 'none' else ch
    v = (opts or {}).get('voice', 'hoaimy')
    if v == 'hoaimy':
        return 'chi'
    if v == 'namminh':
        return 'anh'
    if v == 'vieneu':
        lab = norm((opts or {}).get('vieneu_voice') or '')
        tail = lab.split('—')[-1] if '—' in lab else lab
        if ' nu' in ' ' + tail.replace('-', ' ').replace('·', ' ') :
            return 'chi'
    return 'anh'


class Path:
    def __init__(self, pts, color, width=9):
        self.pts, self.color, self.width = pts, color, max(2, int(width))
        L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        self.dur = max(0.25, L / 1400)

    def draw(self, f, r):
        if r <= 0:
            return
        k = max(2, int(len(self.pts) * clamp(r)))
        d = ImageDraw.Draw(f)
        d.line(self.pts[:k], fill=self.color, width=self.width, joint='curve')
        rr = self.width / 2
        for (x, y) in (self.pts[0], self.pts[k - 1]):
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=self.color)

    def pos(self, r, t):
        return self.pts[min(len(self.pts) - 1, int((len(self.pts) - 1) * clamp(r)))]


def wobble(pts, amp=2.5, seed=0):
    ph = random.Random(seed).random() * 6
    return [(x + amp * math.sin(i * 0.21 + ph), y + amp * math.cos(i * 0.17 + ph * 1.3))
            for i, (x, y) in enumerate(pts)]


def seg(p0, p1, bow=6, seed=0):
    n = max(8, int(math.dist(p0, p1) / 6))
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    b = bow * (random.Random(seed).random() - 0.5) * 2
    return [(p0[0] + dx * i / n + nx * b * math.sin(math.pi * i / n),
             p0[1] + dy * i / n + ny * b * math.sin(math.pi * i / n)) for i in range(n + 1)]


def poly(points, seed=0, bow=6):
    pts = []
    for i in range(len(points) - 1):
        s = seg(points[i], points[i + 1], bow=bow, seed=seed + i)
        pts += s if i == 0 else s[1:]
    return pts


def ellipse(cx, cy, rx, ry, turns=1.1, start=-2.2, seed=0):
    n = int(90 * turns)
    pts = [(cx + rx * (1 + 0.04 * i / n) * math.cos(start + 2 * math.pi * turns * i / n),
            cy + ry * (1 + 0.04 * i / n) * math.sin(start + 2 * math.pi * turns * i / n)) for i in range(n + 1)]
    return wobble(pts, 3, seed)


def wavy(x0, x1, y, amp=7):
    n = max(10, int((x1 - x0) / 5))
    return [(x0 + (x1 - x0) * i / n, y + amp * math.sin(i / n * math.pi * 6)) for i in range(n + 1)]


class Fill:
    """Tô màu nhạt bên trong hình (hiện dần như đang tô)."""

    def __init__(self, pts, color, alpha=0.30):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        self.x0, self.y0 = int(min(xs)) - 2, int(min(ys)) - 2
        w, h = int(max(xs)) - self.x0 + 4, int(max(ys)) - self.y0 + 4
        im = Image.new('RGBA', (max(1, w), max(1, h)), (0, 0, 0, 0))
        ImageDraw.Draw(im).polygon([(x - self.x0, y - self.y0) for x, y in pts], fill=tuple(color) + (int(255 * alpha),))
        self.im = im
        self.c = (sum(xs) / len(xs), sum(ys) / len(ys))
        self.r = min(w, h) * 0.25
        self.dur = 0.3

    def draw(self, f, r):
        if r <= 0:
            return
        im = self.im if r >= 1 else with_alpha(self.im, clamp(r))
        f.paste(im, (self.x0, self.y0), im)

    def pos(self, r, t):
        return (self.c[0] + self.r * math.sin(t * 31), self.c[1] + self.r * 0.7 * math.cos(t * 23))


GREEN = (30, 140, 70)
PURPLE = (130, 60, 170)


KHO_DIR = os.path.join(ASSETS, 'kho')
_kho = {'mtime': None, 'idx': {}}
KHO_GENERIC = {'du hoc', 'han quoc', 'dai loan', 'hoc sinh', 'sinh vien', 'viet nam', 'truong hoc', 'dai hoc'}
KHO_STOP = {'va', 'cua', 'o', 'tai', 'voi', 'cho', 'la', 'cac', 'nhung', 'mot', 'trong', 'tren', 'duoi', 'anh', 'chi'}


def kho_index():
    """{tên chuẩn hóa: đường dẫn} của các ảnh trong Kho hình."""
    try:
        mt = os.path.getmtime(KHO_DIR)
    except OSError:
        return {}
    if _kho['mtime'] != mt:
        idx = {}
        for f in sorted(os.listdir(KHO_DIR)):
            if f.lower().endswith('.png') and not f.startswith('_'):
                idx[norm(re.sub(r'[_\-]+', ' ', f[:-4]))] = os.path.join(KHO_DIR, f)
        _kho.update(mtime=mt, idx=idx)
    return _kho['idx']


def kho_has(name):
    return norm(name) in kho_index()


def kho_keywords():
    out = {}
    for n in kho_index():
        w = [x for x in n.split() if x not in KHO_STOP]
        keys = {n}
        for i in range(len(w) - 1):
            bg = w[i] + ' ' + w[i + 1]
            if bg not in KHO_GENERIC:
                keys.add(bg)
        out[n] = list(keys)
    return out


def big_icon(name):
    return _hv.has(name) or kho_has(name)


def _kho_dst(name):
    os.makedirs(KHO_DIR, exist_ok=True)
    base = re.sub(r'[^a-z0-9]+', '_', norm(name)).strip('_') or 'hinh'
    dst = os.path.join(KHO_DIR, base + '.png')
    k = 2
    while os.path.exists(dst):
        dst = os.path.join(KHO_DIR, '%s_%d.png' % (base, k)); k += 1
    return dst


def kho_add(src, name=None):
    """Thêm ảnh vào Kho: tách nền, lưu PNG với tên (không dấu, nối bằng _)."""
    dst = _kho_dst(name or os.path.splitext(os.path.basename(src))[0])
    remove_bg(src, max_h=1100).save(dst)
    CharItem._cache.clear()
    return dst


def _best_cut(profile, center, span):
    """Tìm vị trí 'trắng nhất' gần center (khe giữa các hình)."""
    lo, hi = max(1, int(center - span)), min(len(profile) - 1, int(center + span))
    seg = profile[lo:hi]
    if len(seg) == 0:
        return int(center)
    m = seg.min()
    idx = np.where(seg <= m + 1e-6)[0]
    return lo + int(idx[len(idx) // 2])


def split_grid(src, rows, cols):
    """Cắt ảnh lưới (nhiều hình trên nền trắng) thành từng hình, cắt ở khe trắng gần đường chia đều."""
    im = Image.open(src).convert('RGB')
    a = np.asarray(im).astype(np.int32)
    ink = (a.min(axis=2) < 225).astype(np.float32)
    H_, W_ = ink.shape
    colp, rowp = ink.sum(axis=0), ink.sum(axis=1)
    xs = [0] + [_best_cut(colp, W_ * c / cols, W_ / cols * 0.22) for c in range(1, cols)] + [W_]
    ys = [0] + [_best_cut(rowp, H_ * r / rows, H_ / rows * 0.22) for r in range(1, rows)] + [H_]
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(im.crop((xs[c], ys[r], xs[c + 1], ys[r + 1])))
    return out


def kho_add_grid(src, rows, cols, names):
    """Cắt ảnh lưới rồi thêm từng hình vào Kho với tên tương ứng (trái→phải, trên→dưới)."""
    tmpd = tempfile.mkdtemp(prefix='luoi_')
    saved = []
    try:
        for i, cell in enumerate(split_grid(src, rows, cols)):
            name = names[i].strip() if i < len(names) and names[i].strip() else 'hinh luoi %d' % (i + 1)
            if name in ('-', 'bo', 'bỏ'):
                continue
            tp = os.path.join(tmpd, 'c%d.png' % i)
            cell.save(tp)
            dst = _kho_dst(name)
            remove_bg(tp, max_h=1100).save(dst)
            saved.append(dst)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    CharItem._cache.clear()
    return saved


def kho_rename(path, new_name):
    base = re.sub(r'[^a-z0-9]+', '_', norm(new_name)).strip('_')
    if not base:
        raise VideoError('Tên không hợp lệ.')
    dst = os.path.join(KHO_DIR, base + '.png')
    if os.path.exists(dst) and os.path.abspath(dst) != os.path.abspath(path):
        raise VideoError('Đã có ảnh tên "%s" trong kho.' % base)
    os.replace(path, dst)
    CharItem._cache.clear()
    return dst


def kho_item(name, cx, cy, h):
    path = kho_index()[norm(name)]
    with Image.open(path) as im:
        w0, h0 = im.size
    maxw = LMAXW * 0.95
    hh = min(h, maxw * h0 / w0)
    it = CharItem(path, cx, cy + hh / 2, hh)
    it.dur = 1.4
    return [it]


def icon_paths(name, cx, cy, h, color, seed):
    if kho_has(name):
        return kho_item(name, cx, cy, h)
    if _hv.has(name):
        return _hv.draw(name, cx, cy, h, color, seed)
    s = h / 300.0
    n = norm(name)
    n = ICON_ALIASES.get(n, n)
    w = 10 * s + 2
    sd = [seed]

    def P(pts):
        return [(cx + x * s, cy + y * s) for x, y in pts]

    def L(pts, c, width=None, bow=4):
        sd[0] += 3
        return Path(poly(P(pts), seed=sd[0], bow=bow * s), c, width or w)

    def R(x0, y0, x1, y1, c, width=None, fill=None):
        out = []
        if fill:
            out.append(Fill(P([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]), fill))
        out.append(L([(x0 + 3, y0), (x1, y0 - 2), (x1 + 2, y1), (x0, y1 + 2), (x0 + 4, y0 + 3)], c, width))
        return out

    def E(x, y, rx, ry, c, width=None, fill=None, turns=1.08):
        sd[0] += 3
        out = []
        if fill:
            out.append(Fill([(cx + (x + rx * math.cos(a)) * s, cy + (y + ry * math.sin(a)) * s)
                             for a in np.linspace(0, 2 * math.pi, 48)], fill))
        out.append(Path(ellipse(cx + x * s, cy + y * s, rx * s, ry * s, turns=turns, seed=sd[0]), c, width or w))
        return out

    def F(pts, c):
        return [Fill(P(pts), c)]

    c = color
    if n == 'tich':
        k = c or BLUE
        return E(0, 0, 140, 135, k, fill=(200, 215, 245)) + [L([(-75, 5), (-15, 65), (90, -70)], k, 20 * s + 2, 2)]
    if n == 'x':
        k = c or RED
        return E(0, 0, 140, 135, k, fill=(250, 210, 210)) + [L([(-65, -65), (65, 65)], k, 20 * s + 2, 2),
                                                             L([(65, -65), (-65, 65)], k, 20 * s + 2, 2)]
    if n == 'mu':
        return (F([(0, -130), (230, -40), (0, 50), (-230, -40)], (60, 64, 90)) +
                [L([(0, -130), (230, -40), (0, 50), (-230, -40), (0, -130)], c or INK)] +
                F([(-140, 5), (-130, 120), (0, 160), (130, 120), (140, 5)], (250, 200, 200)) +
                [L([(-140, 5), (-130, 120), (0, 160), (130, 120), (140, 5)], RED),
                 L([(0, -40), (180, -10), (180, 110)], ORANGE, None, 2)])
    if n == 'hoi':
        k = c or ORANGE
        arc = [(cx + 85 * s * math.cos(a), cy - 50 * s + 80 * s * math.sin(a))
               for a in np.linspace(-math.pi * 1.05, math.pi * 0.5, 40)]
        return [Path(wobble(arc + seg(arc[-1], (cx, cy + 70 * s))[1:], 2, seed), k, 22 * s + 2)] + \
            E(0, 125, 14, 14, k, 22 * s + 2, turns=1.2)
    if n == 'may bay':
        k = c or BLUE
        body = [(-220, 10), (-180, -25), (150, -25), (215, 0), (150, 25), (-180, 25), (-220, 10)]
        wing = [(-10, 20), (-90, 140), (-45, 140), (60, 20)]
        wing2 = [(-10, -20), (-70, -110), (-35, -110), (50, -20)]
        tail = [(-170, -22), (-210, -100), (-175, -100), (-125, -22)]
        return (F(body, (205, 220, 248)) + [L(body, k)] + F(wing, (205, 220, 248)) + [L(wing, k), L(wing2, k), L(tail, k)] +
                [L([(110, -12), (140, -12)], k, 6 * s + 2, 1), L([(40, -10), (60, -10)], GREY, 6 * s + 2, 1),
                 L([(0, -10), (20, -10)], GREY, 6 * s + 2, 1), L([(-40, -10), (-20, -10)], GREY, 6 * s + 2, 1)] +
                [L([(-240, 60), (-300, 60)], GREY, 5 * s + 2, 2), L([(-250, 90), (-330, 90)], GREY, 5 * s + 2, 2)])
    if n == 'may bay giay':
        k = c or BLUE
        return (F([(-200, 20), (200, -120), (40, 130), (0, 40)], (205, 220, 248)) +
                [L([(-200, 20), (200, -120), (40, 130), (0, 40), (-200, 20)], k), L([(0, 40), (200, -120)], k),
                 L([(0, 40), (-20, 120), (40, 130)], k)])
    if n == 'tien':
        k = c or GREEN
        out = []
        for i, (dx, dy) in enumerate([(-40, -50), (-20, -25), (0, 0)]):
            out += R(-190 + dx, -90 + dy, 150 + dx, 100 + dy, k, fill=(205, 235, 210) if i == 2 else None)
        out += E(-20, 5, 52, 52, k)
        out += [L([(5, -25), (-35, -25), (-40, 5), (0, 8), (5, 35), (-40, 35)], k, 9 * s + 2, 1),
                L([(-20, -45), (-20, 55)], k, 7 * s + 2, 1)]
        out += E(-150, -55, 14, 14, k, 7 * s + 2) + E(110, 65, 14, 14, k, 7 * s + 2)
        for i, y in enumerate([110, 85, 60]):
            out += E(185, y, 55, 18, ORANGE, fill=(253, 225, 180) if i == 0 else None)
        return out
    if n == 'dong xu':
        out = []
        for i, y in enumerate([110, 70, 30, -10]):
            out += E(-60, y, 110, 32, ORANGE, fill=(253, 225, 180))
        out += E(120, 40, 80, 80, ORANGE, fill=(253, 225, 180)) + [L([(120, 0), (120, 80)], ORANGE, None, 2)]
        return out
    if n == 'so tiet kiem':
        k = c or GREEN
        return (R(-150, -130, 150, 140, k, fill=(205, 235, 210)) + [L([(-120, -130), (-120, 140)], k)] +
                [L([(-80, -70), (110, -70)], GREY, 7 * s + 2, 2), L([(-80, -20), (110, -20)], GREY, 7 * s + 2, 2),
                 L([(-80, 30), (60, 30)], GREY, 7 * s + 2, 2)] + E(70, 90, 32, 32, ORANGE, fill=(253, 225, 180)))
    if n == 'ho chieu':
        k = c or (110, 40, 60)
        return (R(-120, -150, 120, 150, k, fill=(240, 200, 210)) + E(0, -20, 60, 60, ORANGE) +
                [L([(-60, -20), (60, -20)], ORANGE, 6 * s + 2, 1), L([(0, -80), (0, 40)], ORANGE, 6 * s + 2, 1),
                 L([(-60, 90), (60, 90)], k, 8 * s + 2, 2)])
    if n == 'con dau':
        k = c or RED
        return E(0, 0, 150, 115, k, 12 * s + 2) + E(0, 0, 120, 88, k, 6 * s + 2) + \
            [L([(-60, 0), (-15, 40), (65, -40)], k, 18 * s + 2, 2)]
    if n == 'vali':
        k = c or ORANGE
        return (R(-150, -80, 150, 150, k, fill=(253, 225, 180)) + [L([(-55, -80), (-50, -140), (50, -140), (55, -80)], INK)] +
                [L([(-70, -80), (-70, 150)], k), L([(70, -80), (70, 150)], k)] +
                E(-110, 160, 14, 14, INK, 7 * s + 2) + E(110, 160, 14, 14, INK, 7 * s + 2))
    if n == 'sach':
        k = c or BLUE
        return (F([(0, -80), (-200, -110), (-200, 100), (0, 130)], (205, 220, 248)) +
                F([(0, -80), (200, -110), (200, 100), (0, 130)], (205, 220, 248)) +
                [L([(0, -80), (-200, -110), (-200, 100), (0, 130), (0, -80)], k), L([(0, -80), (200, -110), (200, 100), (0, 130)], k)] +
                [L([(-160, -50), (-40, -35)], GREY, 6 * s + 2, 2), L([(-160, 0), (-40, 15)], GREY, 6 * s + 2, 2),
                 L([(40, -35), (160, -50)], GREY, 6 * s + 2, 2), L([(40, 15), (160, 0)], GREY, 6 * s + 2, 2)])
    if n == 'but':
        k = c or ORANGE
        body = [(-200, 60), (120, -100), (160, -20), (-160, 140)]
        return (F(body, (253, 225, 180)) + [L(body + [(-200, 60)], k)] +
                [L([(-200, 60), (-240, 160), (-160, 140)], INK), L([(120, -100), (150, -115), (190, -35), (160, -20)], RED)])
    if n == 'truong':
        k = c or RED
        return (F([(-200, -10), (200, -10), (200, 150), (-200, 150)], (250, 215, 205)) +
                [L([(-230, -10), (0, -120), (230, -10)], k)] + R(-200, -10, 200, 150, k) +
                R(-35, 60, 35, 150, INK) + R(-160, 20, -90, 80, BLUE) + R(90, 20, 160, 80, BLUE) +
                [L([(0, -120), (0, -200)], INK, 6 * s + 2, 1)] + F([(0, -200), (70, -180), (0, -160)], RED) +
                [L([(0, -200), (70, -180), (0, -160)], RED, 6 * s + 2, 1)])
    if n == 'nha':
        k = c or ORANGE
        return (F([(-150, -10), (150, -10), (150, 150), (-150, 150)], (253, 230, 200)) +
                [L([(-190, -10), (0, -150), (190, -10)], RED)] + R(-150, -10, 150, 150, k) + R(-30, 60, 30, 150, INK) +
                R(-120, 20, -60, 70, BLUE) + R(60, 20, 120, 70, BLUE))
    if n == 'hoc sinh':
        k = c or INK
        return (E(0, -90, 50, 55, k, fill=(253, 230, 210)) +
                F([(0, -165), (85, -135), (0, -105), (-85, -135)], (60, 64, 90)) +
                [L([(0, -165), (85, -135), (0, -105), (-85, -135), (0, -165)], k, 7 * s + 2, 2)] +
                F([(-90, 150), (-70, 0), (70, 0), (90, 150)], (205, 220, 248)) +
                [L([(-90, 150), (-70, 0), (70, 0), (90, 150)], BLUE)] + R(30, 30, 150, 110, RED, 7 * s + 2, (250, 210, 210)))
    if n == 'bang':
        k = c or ORANGE
        return (F([(-200, -70), (200, -70), (200, 70), (-200, 70)], (253, 240, 215)) + R(-200, -70, 200, 70, k) +
                E(-200, 0, 22, 70, k) + E(200, 0, 22, 70, k) +
                E(60, 100, 40, 40, RED, fill=(250, 210, 210)) + [L([(40, 135), (25, 190)], RED), L([(80, 135), (95, 190)], RED)] +
                [L([(-140, -20), (120, -20)], GREY, 6 * s + 2, 2), L([(-140, 20), (40, 20)], GREY, 6 * s + 2, 2)])
    if n == 'lich':
        k = c or RED
        out = (F([(-150, -110), (150, -110), (150, -50), (-150, -50)], (250, 210, 210)) + R(-150, -110, 150, 150, k) +
               [L([(-150, -50), (150, -50)], k), L([(-80, -140), (-80, -85)], INK), L([(80, -140), (80, -85)], INK)])
        for j in range(3):
            for i in range(4):
                out += E(-105 + i * 70, -5 + j * 55, 8, 8, GREY, 6 * s + 2, turns=1.0)
        out += E(35, 105, 32, 28, ORANGE, 8 * s + 2)
        return out
    if n == 'dong ho':
        k = c or ORANGE
        return (E(0, 0, 140, 140, k, fill=(253, 230, 200)) + [L([(0, 0), (0, -95)], INK, 14 * s + 2, 2),
                                                              L([(0, 0), (70, 35)], INK, 14 * s + 2, 2)])
    if n == 'dien thoai':
        k = c or BLUE
        return (R(-90, -150, 90, 150, INK, fill=(225, 230, 240)) + E(0, 128, 12, 10, INK, 6 * s + 2) +
                F([(30, -130), (230, -130), (230, -30), (110, -30), (80, 10), (85, -30), (30, -30)], (205, 220, 248)) +
                [L([(30, -130), (230, -130), (230, -30), (110, -30), (80, 10), (85, -30), (30, -30), (30, -130)], k)] +
                E(80, -80, 9, 9, k, 7 * s + 2) + E(130, -80, 9, 9, k, 7 * s + 2) + E(180, -80, 9, 9, k, 7 * s + 2))
    if n == 'tin nhan':
        k = c or BLUE
        pts = [(-200, -120), (200, -120), (200, 60), (-40, 60), (-110, 140), (-100, 60), (-200, 60), (-200, -120)]
        return F(pts, (205, 220, 248)) + [L(pts, k)] + E(-90, -30, 14, 14, k) + E(0, -30, 14, 14, k) + E(90, -30, 14, 14, k)
    if n == 'dia cau':
        k = c or BLUE
        return (E(0, 0, 140, 140, k, fill=(205, 225, 248)) + E(0, 0, 60, 140, k, 7 * s + 2) +
                [L([(-140, 0), (140, 0)], k, 7 * s + 2, 2), L([(-120, -70), (120, -70)], k, 7 * s + 2, 2),
                 L([(-120, 70), (120, 70)], k, 7 * s + 2, 2)] +
                F([(-60, -60), (10, -90), (40, -30), (-20, 20), (-70, 0)], (150, 205, 160)))
    if n == 'bong den':
        k = c or ORANGE
        bulb = [(cx + 100 * s * math.cos(a), cy - 40 * s + 100 * s * math.sin(a)) for a in np.linspace(0.75 * math.pi, 2.25 * math.pi, 40)]
        return ([Fill(bulb, (253, 235, 170))] + [Path(wobble(bulb, 2, seed), k, w)] +
                [L([(-60, 35), (-50, 100), (50, 100), (60, 35)], k)] + R(-50, 100, 50, 145, INK) +
                [L([(-150, -150), (-120, -120)], ORANGE, None, 1), L([(150, -150), (120, -120)], ORANGE, None, 1),
                 L([(0, -190), (0, -160)], ORANGE, None, 1), L([(-30, -40), (0, 10), (30, -40)], k, 7 * s + 2, 1)])
    if n == 'bieu do':
        k = c or GREEN
        out = [L([(-200, -140), (-200, 140), (210, 140)], INK)]
        for i, hh in enumerate([60, 110, 170, 230]):
            x = -160 + i * 95
            out += R(x, 140 - hh, x + 60, 140, k, fill=(205, 235, 210))
        out += [L([(-170, 40), (-60, -10), (40, -60), (170, -150)], RED, None, 3),
                L([(120, -150), (175, -155), (165, -100)], RED, None, 2)]
        return out
    if n == 'cap':
        k = c or (120, 80, 40)
        return (R(-180, -60, 180, 140, k, fill=(235, 215, 190)) + [L([(-60, -60), (-55, -120), (55, -120), (60, -60)], k)] +
                [L([(-180, 20), (180, 20)], k)] + R(-25, 5, 25, 40, ORANGE))
    if n == 'kinh lup':
        k = c or BLUE
        return E(-40, -40, 110, 110, k, 14 * s + 2, fill=(215, 230, 250)) + [L([(40, 40), (170, 170)], INK, 26 * s + 2, 2)]
    if n == 'canh bao':
        k = c or ORANGE
        tri = [(0, -160), (180, 140), (-180, 140), (0, -160)]
        return F(tri[:-1], (253, 230, 170)) + [L(tri, k)] + [L([(0, -70), (0, 50)], RED, 22 * s + 2, 2)] + \
            E(0, 95, 13, 13, RED, 22 * s + 2)
    if n == 'huy chuong':
        k = c or ORANGE
        return (F([(-70, -170), (-10, -60), (10, -60), (70, -170), (30, -170), (0, -110), (-30, -170)], (205, 220, 248)) +
                [L([(-70, -170), (-15, -60)], BLUE), L([(70, -170), (15, -60)], BLUE)] +
                E(0, 30, 100, 100, k, fill=(253, 225, 160)) + icon_star(cx, cy + 30 * s, 50 * s, RED, seed))
    if n == 'khien':
        k = c or BLUE
        pts = [(0, -160), (150, -110), (140, 40), (0, 160), (-140, 40), (-150, -110), (0, -160)]
        return F(pts[:-1], (205, 220, 248)) + [L(pts, k)] + [L([(-60, 0), (-15, 50), (70, -50)], GREEN, 18 * s + 2, 2)]
    if n == 'danh sach':
        k = c or INK
        out = R(-140, -140, 140, 160, k, fill=(240, 240, 235)) + R(-50, -165, 50, -120, ORANGE)
        for i in range(3):
            y = -70 + i * 75
            out += [L([(-100, y), (-80, y + 20), (-50, y - 20)], GREEN, 9 * s + 2, 1),
                    L([(-20, y), (100, y)], GREY, 7 * s + 2, 2)]
        return out
    if n == 'tim':
        k = c or RED
        pts = [(cx + 9 * s * 16 * math.sin(t) ** 3,
                cy - 9 * s * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))
               for t in np.linspace(0, 2 * math.pi, 120)]
        return [Fill(pts, (250, 205, 210)), Path(wobble(pts, 2, seed), k, w)]
    if n == 'sao':
        return icon_star(cx, cy, 140 * s, c or ORANGE, seed, fill=(253, 230, 160))
    if n == 'mui ten':
        k = c or RED
        return [L([(-200, 40), (180, -20)], k, w + 2, 14), L([(100, -80), (185, -20), (110, 60)], k, w + 2, 3)]
    if n == 'nguoi':
        out = []
        for dx, col, fil in [(-90, BLUE, (205, 220, 248)), (90, RED, (250, 210, 210))]:
            out += E(dx, -80, 45, 48, INK, fill=(253, 230, 210))
            out += F([(dx - 75, 150), (dx - 60, 0), (dx + 60, 0), (dx + 75, 150)], fil)
            out += [L([(dx - 75, 150), (dx - 60, 0), (dx + 60, 0), (dx + 75, 150)], col)]
        return out
    return []


def icon_star(cx, cy, r, color, seed, fill=None):
    pts = []
    for i in range(11):
        rr = r if i % 2 == 0 else r * 0.42
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    out = [Fill(pts[:-1], fill)] if fill else []
    return out + [Path(poly(pts, seed=seed, bow=3), color, max(4, r / 14))]


ICON_ALIASES = {
    'dung': 'tich', 'check': 'tich', 'dau tich': 'tich', 'sai': 'x', 'dau x': 'x', 'mu tot nghiep': 'mu',
    'tot nghiep': 'bang', 'dau hoi': 'hoi', '?': 'hoi', 'maybay': 'may bay', 'thoi gian': 'dong ho',
    'quyen sach': 'sach', 'trai tim': 'tim', 'ngoi sao': 'sao', 'muiten': 'mui ten', '->': 'mui ten',
    'tien mat': 'tien', 'xu': 'dong xu', 'passport': 'ho chieu', 'visa': 'con dau', 'hanh ly': 'vali',
    'but chi': 'but', 'truong hoc': 'truong', 'ky tuc xa': 'nha', 'bang tot nghiep': 'bang',
    'dt': 'dien thoai', 'chat': 'tin nhan', 'trai dat': 'dia cau', 'y tuong': 'bong den',
    'viec lam': 'cap', 'kiem tra': 'kinh lup', 'can than': 'canh bao', 'hoc bong': 'huy chuong',
    'an toan': 'khien', 'giay to': 'danh sach', 'ho so': 'danh sach', 'ban be': 'nguoi',
}

ICON_NAMES = ('tiền, đồng xu, sổ tiết kiệm, hộ chiếu, con dấu, máy bay, máy bay giấy, vali, sách, bút, trường, '
              'nhà, học sinh, bằng, lịch, đồng hồ, điện thoại, tin nhắn, địa cầu, bóng đèn, biểu đồ, cặp, '
              'kính lúp, cảnh báo, huy chương, khiên, danh sách, người, mũ, tích, x, hỏi, tim, sao, mũi tên')

# Từ khóa → hình (so khớp trên chữ màn hình ×2 và lời đọc ×1)
ICON_KEYWORDS = {
    'tien': ['tien', 'chi phi', 'hoc phi', 'bao nhieu tien', 'trieu', 'tai chinh', 'kinh phi', 'usd', 'dong tien',
             'kha gia', 'tra gop', 'phi '],
    'so tiet kiem': ['so tiet kiem', 'chung minh tai chinh', 'tiet kiem'],
    'ho chieu': ['ho chieu', 'passport', 'lanh su', 'dai su quan'],
    'con dau': ['dau visa', 'cap visa', 'visa', 'duyet ho so', 'phong van visa'],
    'may bay': ['may bay', 'bay sang', 'san bay', 'xuat canh', 'nhap canh', 'sang han', 'sang dai loan', 'bay '],
    'vali': ['vali', 'hanh ly', 'mang gi', 'do dung', 'chuan bi do'],
    'sach': ['hoc tieng', 'sach', 'giao trinh', 'topik', 'tocfl', 'tieng han', 'tieng hoa', 'tieng trung', 'on thi',
             'ngon ngu', 'tu vung'],
    'but': ['hoc ba', 'diem', 'bai thi', 'viet ', 'ke hoach hoc tap'],
    'truong': ['truong', 'dai hoc', 'cao dang', 'nhap hoc', 'chon truong'],
    'nha': ['ky tuc xa', 'thue nha', 'cho o', 'nha o', 'phong tro'],
    'hoc sinh': ['hoc sinh', 'du hoc sinh', 'sinh vien', 'lop 12'],
    'bang': ['tot nghiep', 'bang cap', 'bang dai hoc', 'ra truong', 'van bang'],
    'lich': ['lich', 'ky nhap hoc', 'han nop', 'han chot', 'thang ', 'khi nao', 'bao lau', 'nam sinh', 'tuoi'],
    'dong ho': ['phut', 'gio ', 'thoi gian', 'nhanh', 'ngay lap tuc', 'trong 5'],
    'dien thoai': ['inbox', 'in-boc', 'nhan tin', 'lien he', 'goi ', 'hotline', 'zalo'],
    'tin nhan': ['hoi ', 'thac mac', 'cau hoi', 'binh luan', 'comment'],
    'dia cau': ['nuoc ngoai', 'the gioi', 'chon nuoc', 'han hay dai loan', 'quoc te'],
    'bong den': ['meo', 'bi quyet', 'y tuong', 'luu y', 'kinh nghiem', 'cach '],
    'bieu do': ['co hoi', 'tuong lai', 'phat trien', 'thang tien', 'thu nhap', 'tang'],
    'cap': ['vua hoc vua lam', 'viec lam', 'lam them', 'di lam', 'cong viec', 'lam viec', 'cong ty', 'thuc tap', 'nghe '],
    'kinh lup': ['kiem tra', 'check', 'tim hieu', 'xem xet', 'xet ', 'giai trinh'],
    'canh bao': ['sai lam', 'can than', 'canh giac', 'lua dao', 'bat hop phap', 'rui ro', 'tranh '],
    'huy chuong': ['hoc bong', 'xuat sac', 'hoc gioi', 'giai thuong'],
    'khien': ['an toan', 'uy tin', 'bao ve', 'yen tam'],
    'danh sach': ['giay to', 'ho so', 'can chuan bi', 'quy trinh', 'buoc', 'dieu kien', 'yeu cau'],
    'mu': ['muc dich hoc tap', 'hoc tap', 'chuyen nganh'],
    'tich': ['van di duoc', 'co the', 'duoc nhe', 'dung vay', 'chac chan'],
    'x': ['khong duoc', 'bi tu choi', 'truot'],
    'nguoi': ['phu huynh', 'gia dinh', 'ban be', 'nguoi than'],
}


def _words(t):
    return ' ' + re.sub(r'[^a-z0-9%+]+', ' ', norm(t)) + ' '


def pick_icon(screen, say, avoid=()):
    a, b = _words(screen), _words(say)
    best, best_score = None, 0
    allkeys = dict(ICON_KEYWORDS)
    allkeys.update(_hv.keywords())
    allkeys.update(kho_keywords())
    for icon, keys in allkeys.items():
        sc = 0
        for k in keys:
            kk = ' %s ' % k.strip()
            wk = 1 + len(k) / 8.0 + (1.2 if kho_has(icon) else 0.6 if _hv.has(icon) else 0)
            if kk in a:
                sc += 2 * wk
            if kk in b:
                sc += wk
        if icon in avoid:
            sc *= 0.25
        if sc > best_score:
            best, best_score = icon, sc
    if best is None and screen.strip().endswith('?'):
        return 'hoi'
    return best


# ------------------------------------------------------------------ đọc kịch bản
TAG = re.compile(r'\[([^\]]*)\]')
SAY = re.compile(r'^(đọc|doc|lời đọc|loi doc|giọng|giong)\s*:\s*(.*)$', re.I)


BIGRAMS = set("""du hoc|hoc sinh|sinh vien|giai trinh|hop ly|thoi gian|muc dich|hoc tap|ro rang|chung minh|han quoc|dai loan
|ho so|nam sinh|tra loi|cau tra|binh thuong|nghia vu|quan su|quan trong|tieng han|tieng trung|tieng hoa|tieng anh|chi phi
|hoc phi|hoc bong|ky tuc|tuc xa|phong van|dai su|su quan|xuat canh|nhap canh|may bay|san bay|viec lam|lam them|thong tin
|tu van|trung tam|gia dinh|phu huynh|tot nghiep|dai hoc|cao dang|ngoai ngu|ngon ngu|tai chinh|tiet kiem|so tiet|cong ty
|di lam|quay lai|ra truong|truong hop|ket qua|co the|can thiet|chuan bi|dang ky|nhap hoc|hoc tieng|hoc nghe|ky nang
|cuoc song|van hoa|thu tuc|giay to|ho chieu|kinh nghiem|co hoi|tuong lai|nhan vien|cua hang|thuc tap|dinh cu|lao dong
|khoang thoi|trong nam|bao nhieu|bao lau|the nao|tai sao|vi sao|nhu the|nhu nao|hai duong|hai phong|ha noi|viet nam
|xin chao|cam on|mien phi|uu dai|giam gia|toan phan|ban phan|hang thang|moi ngay|moi thang|hoc ba|bang diem|bang cap
|tham khao|lien he|nhan tin|goi dien|check truong|truong nhan|tu tin|yen tam|an toan|lo lang|nho nha|sinh hoat|phi sinh
|hoc vien|giao vien|giang vien|lop hoc|thu vien|ky thi|bai thi|chung chi|trinh do|so cap|trung cap|cao cap|visa du|gian trong|hoc han|sinh nam|xin duoc|duoc khong|di duoc|khong ta|nha ban|cac ban""".replace('\n', '').split('|'))


def _wrap_words(words, maxc=22):
    """Chia danh sách chữ thành các dòng ≤ maxc ký tự, không tách từ ghép, độ dài cân nhau."""
    n = len(words)
    nw = [norm(w).strip(',.;:!?…') for w in words]
    L = [len(w) for w in words]
    INF = float('inf')
    best = [INF] * (n + 1); prev = [0] * (n + 1); best[0] = 0
    target = min(maxc, max(10, (sum(L) + n) / max(1, math.ceil((sum(L) + n) / maxc))))
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            width = sum(L[i:j]) + (j - i - 1)
            if width > maxc and j - i > 1:
                break
            cost = best[i] + (width - target) ** 2
            if j < n and (nw[j - 1] + ' ' + nw[j]) in BIGRAMS:
                cost += 400
            if j - i == 1 and n > 1:
                cost += 250
            elif width < 8 and n > 2:
                cost += 120
            if cost < best[j]:
                best[j], prev[j] = cost, i
    out, j = [], n
    while j > 0:
        i = prev[j]
        out.append(' '.join(words[i:j])); j = i
    return out[::-1]


def split_display(sentence, maxc=22, maxlines=4):
    """Cắt 1 câu nói thành vài dòng chữ ngắn để hiện trên màn hình."""
    s = sentence.strip()
    parts = [x.strip() for x in re.findall(r'[^,.;:!?…]+[,.;:!?…]*', s)] or [s]
    # gộp mẩu quá ngắn vào mẩu kế tiếp
    chunks = []
    for part in parts:
        if chunks and len(chunks[-1]) < 9:
            chunks[-1] = chunks[-1] + ' ' + part
        else:
            chunks.append(part)
    lines = []
    for ch in chunks:
        lines += _wrap_words(ch.split(), maxc)
    lines = [ln.rstrip(',;…').strip() for ln in lines if ln.strip(' ,;…')]
    if len(lines) > maxlines:
        scored = sorted(range(1, len(lines)), key=lambda i: -len(key_spans(lines[i])))
        keep = sorted([0] + scored[:maxlines - 1])
        lines = [lines[i] for i in keep]
    return lines


def parse_simple(text):
    """Kiểu viết đơn giản: mỗi dòng = 1 cảnh, app đọc nguyên câu và tự cắt chữ hiện lên màn hình.
    Dòng bắt đầu bằng '- ' thuộc cảnh ngay trên (gạch đầu dòng).
    Muốn chữ trên màn hình khác lời đọc: 'chữ trên màn hình || lời đọc'."""
    scenes = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tags = [norm(t) for t in TAG.findall(line)]
        body = TAG.sub('', line).strip()
        icon_tags = [t for t in tags if t.startswith('ve:') or t.startswith('ve :')]
        tags = [t for t in tags if t not in icon_tags]
        icon_tags = [t for t in icon_tags if icon_known(t.split(':', 1)[1].strip())]
        if body[:2] in ('- ', '+ ') and scenes:
            item = body[2:].strip()
            scenes[-1]['lines'].append(('- ' + item, tags))
            scenes[-1]['say'].append(item + ',')
            continue
        if not body and tags:
            if scenes:
                scenes[-1]['lines'].append(('', tags))
            continue
        if '||' in body:
            show, say = [x.strip() for x in body.split('||', 1)]
            shown = [x.strip() for x in re.split(r'\s+/\s+', show) if x.strip()]
        else:
            say = body
            shown = split_display(body)
        sc = {'title': '', 'lines': [('', [t]) for t in icon_tags], 'say': [say]}
        for i, t in enumerate(shown):
            sc['lines'].append((t, tags if i == len(shown) - 1 else []))
        scenes.append(sc)
    return scenes


def is_simple(text):
    return not any(l.strip().startswith('===') or SAY.match(l.strip()) for l in text.splitlines())


def clean_pasted(text):
    """Dọn kịch bản dán từ ChatGPT/Gemini: bỏ ```, **, tiêu đề #, hashtag, 'Cảnh 1:', dấu ngoặc kép bao ngoài."""
    out = []
    lines = text.splitlines()
    if sum(1 for l in lines if l.strip().startswith('```')) >= 2:
        inside, keep = False, []
        for l in lines:
            if l.strip().startswith('```'):
                inside = not inside
                continue
            if inside:
                keep.append(l)
        lines = keep
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('```') or line.startswith('#') or line.startswith('==') and not line.startswith('==='):
            continue
        line = line.replace('**', '').replace('__', '')
        line = re.sub(r'^>\s*', '', line)
        line = re.sub(r'^(cảnh|canh|dòng|dong|scene)\s*\d+\s*[:.\-–)]\s*', '', line, flags=re.I)
        line = re.sub(r'^[•*]\s+', '- ', line)
        if line[:1] in '"“':
            line = line[1:]
            k = max(line.rfind('"'), line.rfind('”'))
            if k >= 0:
                line = (line[:k] + line[k + 1:]).strip()
        low = norm(line)
        if re.match(r'^(caption|hashtag|ghi chu|luu y|kich ban)\s*[:：]', low):
            continue
        if line:
            out.append(line)
    return '\n'.join(out)


def icon_known(name):
    n = ICON_ALIASES.get(norm(name), norm(name))
    return kho_has(name) or _hv.has(name) or n in ICON_KEYWORDS or n in ('hoi', 'sao', 'tim', 'mui ten', 'may bay giay', 'dong xu', 'x', 'tich', 'mu')


def parse_script(text):
    if is_simple(text):
        scenes = parse_simple(clean_pasted(text))
        if not scenes:
            raise VideoError('Kịch bản đang trống. Hãy viết ít nhất một dòng.')
        return scenes
    scenes, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('===') or line.startswith('#'):
            cur = {'title': line.strip('=# ').strip(), 'lines': [], 'say': []}
            scenes.append(cur)
            continue
        if cur is None:
            cur = {'title': '', 'lines': [], 'say': []}
            scenes.append(cur)
        m = SAY.match(line)
        if m:
            if m.group(2).strip():
                cur['say'].append(m.group(2).strip())
            continue
        tags = [norm(t) for t in TAG.findall(line)]
        cur['lines'].append((TAG.sub('', line).strip(), tags))
    scenes = [s for s in scenes if s['lines'] or s['say']]
    if not scenes:
        raise VideoError('Kịch bản đang trống. Hãy viết ít nhất một cảnh.')
    return scenes


def tag_color(tags, default=None):
    for t in tags:
        if t in COLORS:
            return COLORS[t]
    return default


def tag_icon(tags):
    for t in tags:
        if t.startswith('ve:') or t.startswith('ve :'):
            return t.split(':', 1)[1].strip()
    return None


# ------------------------------------------------------------------ từ khóa
KEYWORDS = [
    'du hoc', 'visa', 'hoc bong', 'mien phi', 'khong mat phi', 'van di duoc', 'di duoc', 'khong can',
    'bat buoc', 'quan trong', 'giai trinh', 'chung minh', 'muc dich', 'nam sinh', 'trong nam',
    'tieng han', 'tieng trung', 'topik', 'tocfl', 'ky tuc xa', 'lam them', 'viec lam', 'chi phi',
    'tai chinh', 'so tiet kiem', 'ho so', 'phong van', 'dai hoc', 'cao dang', 'he tieng', '1+4',
    'vua hoc vua lam', 'inbox', 'quan trong nhat', 'muc dich hoc tap', 'thoi gian trong', 'ngay', 'han quoc', 'dai loan', 'thu nhap', 'luong', 'tot nghiep',
    'dinh cu', 'co hoi', 'uu dai', 'dang ky', 'tu van', 'mien', 'ro rang', 'hop ly', 'truot', 'do',
]
KEYWORDS = sorted(set(KEYWORDS) - {'do', 'mien', 'ngay'}, key=len, reverse=True)
NUM_RE = re.compile(r'\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+)?(?:\+\d+)?'
                    r'(?:\s*(?:năm|tháng|tuổi|phút|triệu|tr|%|giờ|ngày|điểm|kỳ|cấp|người|trường|USD|\$))?', re.I)


def _charnorm(txt):
    out = []
    for ch in txt:
        if ch in 'đĐ':
            out.append('d')
            continue
        b = unicodedata.normalize('NFD', ch)[0].lower()
        out.append(b if len(b) == 1 else ch)
    return ''.join(out)


def key_spans(txt):
    """Trả về [(start, end, kind)] cho số và từ khóa trong câu."""
    spans = [(m.start(), m.end(), 'num') for m in NUM_RE.finditer(txt) if m.group().strip()]
    low = _charnorm(txt)
    for k in KEYWORDS:
        for m in re.finditer(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', low):
            if all(m.end() <= a or m.start() >= b for a, b, _ in spans):
                spans.append((m.start(), m.end(), 'kw'))
    return sorted(spans)


def make_segs(txt, color, auto):
    """*chữ* = tô nổi bật thủ công. Tự trang trí: số màu đỏ, từ khóa màu xanh (chỉ dòng chữ đen)."""
    hl = RED if color != RED else BLUE
    if '*' in txt:
        parts = txt.split('*')
        return [(p, color if i % 2 == 0 else hl) for i, p in enumerate(parts) if p]
    if not auto or color != INK:
        return [(txt, color)]
    segs, pos = [], 0
    for a, b, kind in key_spans(txt):
        if a > pos:
            segs.append((txt[pos:a], color))
        segs.append((txt[a:b], RED if kind == 'num' else BLUE))
        pos = b
    if pos < len(txt):
        segs.append((txt[pos:], color))
    return segs or [(txt, color)]


# ------------------------------------------------------------------ tự trang trí
STYLE_TAGS = {'den', 'xanh', 'do', 'cam', 'xam', 'xanh la', 'tim', 'to', 'nho', 'khung', 'gach', 'tron', 'logo'}


def auto_style(scenes):
    """Tự trang trí những dòng chưa có thẻ: tô màu từ khóa, gạch chân ý chính, khung, hình vẽ."""
    n = len(scenes)
    last_icon = None
    for si, sc in enumerate(scenes):
        sc['auto'] = True
        lines = sc['lines']
        has_icon = any(tag_icon(t) for _, t in lines)
        text_idx = [i for i, (txt, tg) in enumerate(lines)
                    if txt and txt[:2] not in ('- ', '+ ') and not tag_icon(tg)]
        plain = []
        for pos, i in enumerate(text_idx):
            txt, tags = lines[i]
            if any(t in STYLE_TAGS for t in tags) or '*' in txt:
                continue
            letters = [c for c in txt if c.isalpha()]
            is_caps = bool(letters) and all(c.isupper() for c in letters) and len(txt) <= 26
            last, first = pos == len(text_idx) - 1, pos == 0
            new = []
            if '|' in txt:
                new = ['tron']
            elif first and txt.endswith(':'):
                new = ['xam', 'nho']
            elif txt.startswith(('...', '…', '(')):
                new = ['xam', 'nho']
            elif is_caps:
                new = ['do', 'khung']
            elif last and si == 0:
                new = ['cam', 'to', 'gach']
            elif last and si == n - 1 and n > 1:
                new = ['cam', 'gach']
            elif txt.endswith('!') and len(txt) <= 24:
                new = ['xanh', 'to']
            elif last and txt.endswith('?'):
                new = ['cam']
            else:
                plain.append(i)
            lines[i] = (txt, tags + new)
        # gạch chân câu có nhiều ý chính nhất (nếu cảnh chưa có gạch chân)
        if plain and not any('gach' in lines[i][1] for i in text_idx):
            best = max(plain, key=lambda i: (len(key_spans(lines[i][0])), -abs(len(lines[i][0]) - 18)))
            if key_spans(lines[best][0]) and len(lines[best][0]) <= 32:
                lines[best] = (lines[best][0], lines[best][1] + ['gach'])
        # hình vẽ minh họa theo ngữ cảnh (vẽ trước, chữ sau)
        if not has_icon and len(text_idx) <= 4 and not (si == n - 1 and n > 1):
            screen = ' '.join(t for t, _ in lines)
            icon = pick_icon(screen, ' '.join(sc['say']), avoid=(last_icon,) if last_icon else ())
            if icon:
                at = 1 if text_idx and lines[text_idx[0]][0].endswith(':') else 0
                lines.insert(at, ('', ['ve: ' + icon]))
                last_icon = icon
            else:
                last_icon = None
        elif has_icon:
            last_icon = next((tag_icon(t) for _, t in lines if tag_icon(t)), None)
        if si == n - 1 and n > 1 and not any('logo' in t for _, t in lines):
            lines.append(('', ['logo']))
    return scenes


# ------------------------------------------------------------------ dàn trang
def build_blocks(scene, scale):
    base = 118 * scale
    blocks, lines, i = [], scene['lines'], 0
    while i < len(lines):
        txt, tags = lines[i]
        icon = tag_icon(tags)
        if icon and not icon_known(icon):
            i += 1
            continue
        if icon:
            blocks.append({'k': 'icon', 'name': icon, 'color': tag_color(tags),
                           'h': (560 if kho_has(icon) else 540 if _hv.has(icon) else 380) * scale * min(1.0, LMAXW / 900)})
            i += 1
            continue
        if not txt:
            i += 1
            continue
        if txt[:2] in ('- ', '+ '):
            group = []
            while i < len(lines) and lines[i][0][:2] in ('- ', '+ '):
                group.append((lines[i][0][2:].strip().replace('*', ''), lines[i][1]))
                i += 1
            size = int(min(fit(t, base * 0.95, LMAXW - 110) for t, _ in group))
            blocks.append({'k': 'bullets', 'items': group, 'size': size,
                           'h': len(group) * (line_h(size) * 0.92 + 14)})
            continue
        mult = 1.35 if 'to' in tags else 0.72 if 'nho' in tags else 1.0
        size = base * mult
        color = tag_color(tags, INK)
        if '|' in txt:
            cols = [c.strip().replace('*', '') for c in txt.split('|') if c.strip()]
            colw = LMAXW / len(cols)
            size = min(fit(c, size, colw - (90 if 'tron' in tags else 20)) for c in cols)
            blocks.append({'k': 'row', 'cols': cols, 'size': size, 'color': color, 'tags': tags,
                           'h': line_h(size) * 0.9 + (60 if 'tron' in tags else 0)})
        else:
            extra = 50 if ('khung' in tags or 'tron' in tags) else 0
            segs = make_segs(txt, color, scene.get('auto'))
            txt = ''.join(t for t, _ in segs)
            size = fit(txt, size, LMAXW - (90 if extra else 0))
            blocks.append({'k': 'text', 'text': txt, 'segs': segs, 'size': size, 'color': color, 'tags': tags,
                           'h': line_h(size) * 0.9 + extra + (24 if 'gach' in tags else 0)})
        i += 1
    return blocks


def layout_scene(scene, idx, has_logo_end):
    top = 900 if has_logo_end else TOP_AREA
    bottom = BOTTOM_AREA
    scale = 1.0
    while True:
        blocks = build_blocks(scene, scale)
        gap = 30 * scale
        total = sum(b['h'] for b in blocks) + gap * max(0, len(blocks) - 1)
        if total <= bottom - top or scale < 0.45:
            break
        scale *= 0.92
    y = top + max(0, (bottom - top - total) / 2)
    items, seed = [], idx * 100
    bullet_colors = [BLUE, ORANGE, RED, (30, 140, 70)]
    for b in blocks:
        h = b['h']
        if b['k'] == 'icon':
            parts = icon_paths(b['name'], LCX, y + h / 2, h * (0.95 if big_icon(b['name']) else 0.88), b['color'], seed)
            budget = 2.6 if big_icon(b['name']) else 2.0
            tot = sum(it.dur for it in parts) or 1
            for it in parts:
                it.gap = 0.015 if len(parts) > 6 else 0.08
                if tot > budget:
                    it.dur = max(0.04, it.dur * budget / tot)
            items += parts
        elif b['k'] == 'text':
            tg = b['tags']
            cy = y + (h - (24 if 'gach' in tg else 0)) / 2
            t = Txt(b['text'], b['size'], b['color'], cy, cx=LCX, segs=b['segs'])
            items.append(t)
            sz = b['size']
            if 'khung' in tg:
                x0, x1 = t.left - 34, t.right + 34
                y0, y1 = cy - sz * 0.6, cy + sz * 0.6
                items.append(Path(poly([(x0 + 4, y0), (x1, y0 - 4), (x1 + 4, y1), (x0, y1 + 3), (x0 + 6, y0 + 2)],
                                       seed=seed, bow=8), b['color'], 8))
            if 'tron' in tg:
                items.append(Path(ellipse(LCX, cy + 4, (t.right - t.left) / 2 + 45, sz * 0.68, seed=seed),
                                  b['color'], 8))
            if 'gach' in tg:
                items.append(Path(wavy(t.left + 10, t.right - 10, cy + sz * 0.55), ORANGE if b['color'] != ORANGE else RED, 8))
        elif b['k'] == 'row':
            n = len(b['cols'])
            colw = LMAXW / n
            cy = y + h / 2
            for j, c in enumerate(b['cols']):
                x = LCX + (j - (n - 1) / 2) * colw
                col_color = b['color'] if tag_color(b['tags']) else [BLUE, RED, ORANGE, (30, 140, 70)][j % 4]
                t = Txt(c, b['size'], col_color, cy, cx=x)
                items.append(t)
                if 'tron' in b['tags']:
                    items.append(Path(ellipse(x, cy + 4, (t.right - t.left) / 2 + 28, b['size'] * 0.72,
                                              seed=seed + j), col_color, 8))
        elif b['k'] == 'bullets':
            sz = b['size']
            rh = line_h(sz) * 0.92 + 14
            maxw = max(font(sz).getlength(t) for t, _ in b['items'])
            x0 = LCX - (100 + maxw) / 2
            for j, (t, tg) in enumerate(b['items']):
                cy = y + rh * j + rh / 2
                c = tag_color(tg, None)
                mark = c or bullet_colors[j % len(bullet_colors)]
                items.append(Path(poly([(x0, cy + 2), (x0 + 28, cy + 30), (x0 + 72, cy - 32)], seed=seed + j, bow=3),
                                  mark, 12))
                items.append(Txt(t, sz, c or INK, cy, left=x0 + 100))
        y += h + gap
        seed += 7
    return items


# ------------------------------------------------------------------ giọng đọc
def tts_edge(text, voice, rate, out):
    try:
        import asyncio
        import edge_tts
    except ImportError:
        raise VideoError('Chưa cài thư viện giọng đọc. Hãy chạy lại CAI_DAT.bat.')

    import time as _time
    text = clean_say(text)

    async def go():
        await edge_tts.Communicate(text, voice, rate='%+d%%' % rate).save(out)

    errors = []
    for attempt in range(4):
        try:
            if os.name == 'nt':
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                except Exception:
                    pass
            asyncio.run(go())
            if os.path.exists(out) and os.path.getsize(out) > 500:
                return
            errors.append('Không nhận được âm thanh')
        except Exception as e:
            errors.append('%s: %s' % (type(e).__name__, e))
            low = repr(e).lower()
            if attempt == 0 and ('ssl' in low or 'certificate' in low):
                _use_system_certs()
        _time.sleep(1.5 * (attempt + 1))
    detail = errors[-1]
    low = detail.lower()
    if 'ssl' in low or 'certificate' in low:
        hint = ('Máy tính đang chặn kết nối bảo mật (thường do phần mềm diệt virus quét HTTPS, '
                'hoặc VPN/proxy). Thử tắt tạm tính năng quét web của phần mềm diệt virus rồi tạo lại.')
    elif '403' in low or 'forbidden' in low:
        hint = ('Microsoft từ chối kết nối. Hãy: 1) chạy lại CAI_DAT.bat để cập nhật thư viện; '
                '2) kiểm tra ngày giờ máy tính đúng chưa (Cài đặt → Thời gian → Đặt giờ tự động).')
    elif 'cannot connect' in low or 'timeout' in low or 'getaddrinfo' in low or 'connect' in low:
        hint = 'Không kết nối được máy chủ giọng đọc. Kiểm tra mạng, tắt VPN nếu có, rồi thử lại.'
    else:
        hint = 'Hãy chạy lại CAI_DAT.bat để cập nhật thư viện giọng đọc rồi thử lại.'
    try:
        ver = __import__('importlib.metadata', fromlist=['version']).version('edge-tts')
    except Exception:
        ver = '?'
    raise VideoError('Không tạo được giọng đọc Microsoft.\n\n%s\n\nChi tiết kỹ thuật (edge-tts %s):\n%s'
                     % (hint, ver, detail[:600]))


def clean_say(text):
    t = re.sub(r'(\d)\s*[–-]\s*(\d)', r'\1 đến \2', text)
    t = t.replace('…', ', ').replace('...', ', ').replace('–', ', ').replace('&', ' và ').replace('*', '')
    t = re.sub(r'[\[\]{}<>&#|_~^]', ' ', t)
    t = re.sub(r'\s*,\s*,+', ', ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _use_system_certs():
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass


def test_voice(voice, rate, out_mp3, eleven=None, vieneu=None, progress=None):
    text = 'Xin chào, đây là giọng đọc thử của Du học Hải Dương.'
    if voice == 'vieneu':
        raw = out_mp3[:-4] + '_raw.wav'
        vieneu_run({'texts': [text], 'outs': [raw], 'voice': (vieneu or {}).get('voice'),
                    'ref_audio': (vieneu or {}).get('ref')}, progress)
        to_wav(raw, out_mp3[:-4] + '.wav', 1 + rate / 100.0)
        try:
            os.remove(raw)
        except OSError:
            pass
        return out_mp3[:-4] + '.wav'
    if voice == 'eleven':
        tts_eleven(text, *eleven, out_mp3)
    else:
        tts_edge(text, VOICES.get(voice, VOICES['hoaimy']), rate, out_mp3)
    return out_mp3


def tts_eleven(text, key, voice_id, model, out):
    import urllib.request, urllib.error
    if not key or not voice_id:
        raise VideoError('Chọn ElevenLabs thì cần nhập API key và Voice ID.')
    req = urllib.request.Request(
        'https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128' % voice_id.strip(),
        data=json.dumps({'text': text, 'model_id': model.strip() or 'eleven_v3'}).encode('utf-8'),
        headers={'xi-api-key': key.strip(), 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(out, 'wb') as fh:
            fh.write(r.read())
    except urllib.error.HTTPError as e:
        raise VideoError('ElevenLabs báo lỗi %s: %s' % (e.code, e.read().decode('utf-8', 'ignore')[:400]))
    except Exception as e:
        raise VideoError('Không kết nối được ElevenLabs: %s' % e)


def to_wav(src, dst, tempo=1.0):
    af = ['-filter:a', 'atempo=%.3f' % max(0.5, min(2.0, tempo))] if abs(tempo - 1) > 0.005 else []
    run_ff(['-i', src] + af + ['-ar', '44100', '-ac', '2', '-sample_fmt', 's16', dst])


# ------------------------------------------------------------------ VieNeu-TTS (offline)
def _python_exe():
    exe = sys.executable or 'python'
    base = os.path.basename(exe).lower()
    if base.startswith('pythonw'):
        alt = os.path.join(os.path.dirname(exe), 'python.exe')
        if os.path.exists(alt):
            return alt
    return exe


LAST_VIENEU = {}


def vieneu_run(job, progress=None):
    """Chạy vieneu_worker.py; trả về list dòng VOICE (nếu liệt kê giọng)."""
    tmp = tempfile.mkdtemp(prefix='vieneu_')
    jf = os.path.join(tmp, 'job.json')
    with open(jf, 'w', encoding='utf-8') as fh:
        json.dump(job, fh, ensure_ascii=False)
    errf = os.path.join(tmp, 'err.txt')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    voices = []
    try:
        with open(errf, 'w', encoding='utf-8') as ef:
            p = subprocess.Popen([_python_exe(), os.path.join(HERE, 'vieneu_worker.py'), jf],
                                 stdout=subprocess.PIPE, stderr=ef, env=env, creationflags=NOWIN,
                                 text=True, encoding='utf-8', errors='replace')
            for line in p.stdout:
                line = line.rstrip('\n')
                if line.startswith('VOICE\t'):
                    voices.append(line.split('\t', 1)[1])
                elif line.startswith('PICKED\t'):
                    LAST_VIENEU['picked'] = line.split('\t', 1)[1]
                elif line.startswith('STAGE load') and progress:
                    progress('VieNeu: đang nạp mô hình (lần đầu sẽ tải vài trăm MB, có thể mất vài phút)...', None)
                elif line.startswith('STAGE say') and progress:
                    _, _, a, b = line.split()
                    progress('VieNeu: đang đọc cảnh %s/%s (máy yếu sẽ hơi lâu)...' % (a, b), (int(a) - 1) / int(b))
            rc = p.wait()
        err = open(errf, encoding='utf-8', errors='replace').read()
    finally:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    LAST_VIENEU['voices'] = voices
    if rc == 0:
        return voices
    if rc == 3 or 'ERR_IMPORT' in err:
        raise VideoError('Chưa cài VieNeu-TTS.\nHãy bấm đúp CAI_VIENEU.bat (cần mạng, tải khoảng vài trăm MB) rồi thử lại.')
    if rc in (3221225501, -4, 132, 0xC000001D) or 'illegal instruction' in err.lower():
        raise VideoError('Máy tính này không chạy được VieNeu-TTS: bộ vi xử lý (CPU) thiếu tập lệnh mà thư viện AI cần '
                         '(thường là AVX).\nHãy dùng giọng Microsoft hoặc ElevenLabs, hoặc chạy app trên máy mạnh hơn.')
    if 'memory' in err.lower() or rc in (3221225477, -9, 137):
        tail = err.strip()[-500:]
        raise VideoError('VieNeu bị dừng – có thể do thiếu RAM. Hãy tắt bớt Chrome/Zalo rồi thử lại.\n\nChi tiết:\n' + tail)
    if rc < 0 or rc >= 0xC0000000 or not err.strip():
        raise VideoError('VieNeu-TTS bị tắt đột ngột (mã %s).\nNguyên nhân thường gặp: bộ vi xử lý (CPU) đời cũ thiếu tập '
                         'lệnh AVX, hoặc máy thiếu RAM (hãy tắt bớt Chrome/Zalo rồi thử lại).\nNếu vẫn lỗi, máy này '
                         'không hợp với VieNeu – hãy dùng giọng Microsoft hoặc ElevenLabs.\n\n%s' % (rc, err.strip()[-500:]))
    raise VideoError('VieNeu-TTS báo lỗi (mã %s):\n%s' % (rc, err.strip()[-900:]))


def vieneu_voices(progress=None):
    return vieneu_run({'list': True}, progress)


def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


# ------------------------------------------------------------------ dựng
class Renderer:
    def __init__(self, logo_path=None, label=None):
        hj = json.load(open(os.path.join(ASSETS, 'hand.json')))
        self.hand = Image.open(os.path.join(ASSETS, 'hand.png')).convert('RGBA')
        self.tip = hj['tip']
        lg = load_logo(logo_path if logo_path and os.path.exists(logo_path) else os.path.join(ASSETS, 'logo.png'))
        self.logo_small = scaled(lg, 170)
        if self.logo_small.height > 170:
            self.logo_small = lg.resize((int(lg.width * 170 / lg.height), 170), Image.LANCZOS)
        self.logo_big = scaled(lg, 440)
        if self.logo_big.height > 460:
            self.logo_big = lg.resize((int(lg.width * 460 / lg.height), 460), Image.LANCZOS)
        self.paper = make_paper()
        self.label = None
        if label and label.strip():
            t = Txt(label.strip().upper(), 40, (255, 255, 255), 0, cx=0)
            w = t.im.width + 30
            im = Image.new('RGBA', (w, 70), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, 69), 35, fill=BLUE)
            im.alpha_composite(t.im, ((w - t.im.width) // 2, (70 - t.im.height) // 2))
            self.label = im
        self.eraser = self._make_eraser()

    def _make_eraser(self):
        im = Image.new('RGBA', (340, 170), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((10, 20, 330, 100), 26, fill=(176, 120, 70), outline=(120, 80, 40), width=5)
        d.rounded_rectangle((30, 35, 310, 60), 12, fill=(200, 150, 100))
        d.rectangle((14, 96, 326, 150), fill=(70, 72, 82))
        for x in range(24, 320, 14):
            d.line((x, 100, x, 148), fill=(90, 92, 104), width=3)
        return im.resize((int(im.width * 1.2), int(im.height * 1.35)), Image.LANCZOS)

    def erase(self, f, e):
        top, bot, rows = 390, 1500, 6
        rh = (bot - top) / rows
        pos = clamp(e) * rows
        r = min(rows - 1, int(pos))
        frac = pos - r if e < 1 else 1.0
        for i in range(r if e < 1 else rows):
            y0, y1 = int(top + i * rh), int(top + (i + 1) * rh) + 2
            f.paste(self.paper.crop((0, y0, W, y1)), (0, y0))
        ltr = r % 2 == 0
        xw = int((W + 120) * frac)
        y0, y1 = int(top + r * rh), int(top + (r + 1) * rh) + 2
        if xw > 0 and e < 1:
            x0, x1 = (0, min(W, xw)) if ltr else (max(0, W - xw), W)
            f.paste(self.paper.crop((x0, y0, x1, y1)), (x0, y0))
        if e < 1:
            cx = (xw - 60) if ltr else (W - xw + 60)
            cy = (y0 + y1) / 2 + 12 * math.sin(e * 40)
            er = self.eraser.rotate(8 if ltr else -8, expand=True, resample=Image.BICUBIC)
            f.paste(er, (int(cx - er.width / 2), int(cy - er.height / 2)), er)

    def plan(self, scenes, audio_durs, gender=None):
        global LCX, LMAXW
        plans = []
        n = len(scenes)
        poses = [None] * n
        if gender and char_path(gender, 'chao'):
            poses[0] = 'chao'
            if n > 1:
                poses[-1] = 'like'
            budget = max(1, int((n - 2) * 0.4))
            for i in range(1, n - 1):
                if budget and poses[i - 1] is None and important_scene(scenes[i]):
                    poses[i] = 'chi'
                    budget -= 1
        for i, sc in enumerate(scenes):
            logo_end = any('logo' in tags for _, tags in sc['lines'])
            pose = poses[i]
            if pose == 'like':
                LCX, LMAXW = W / 2 + 165, 640
            elif pose:
                LCX, LMAXW = W / 2 + 170, 640
            else:
                LCX, LMAXW = W / 2, 960
            items = layout_scene(sc, i, logo_end)
            if pose:
                hgt = {'chao': 760, 'chi': 640, 'like': 700}[pose]
                ch = CharItem(char_path(gender, pose), 215, 1462, hgt)
                ch.gap = 0.1
                items = [ch] + items
            lcx = LCX
            LCX, LMAXW = W / 2, 960
            natural = ENTER + sum(it.dur + getattr(it, 'gap', GAP) for it in items)
            A = audio_durs[i] if audio_durs else None
            k = 1.0
            if A:
                k = max(0.45, min(1.5, (A * 0.88) / max(natural, 0.1)))
            t, sch = ENTER * k, []
            for it in items:
                d = it.dur * k
                sch.append((it, t, t + d))
                t += d + getattr(it, 'gap', GAP) * k
            ed = (sch[-1][2]) if sch else 0.3
            hold = 2.0 if logo_end else (0.3 if A else 1.2)
            dur = max(ed + EXIT + hold, (A + 0.45) if A else 0)
            last = i == len(scenes) - 1
            if not last:
                dur += ERASE
            nfr = int(math.ceil(dur * FPS))
            plans.append({'sch': sch, 'ed': ed, 'n': nfr, 'dur': nfr / FPS, 'logo_end': logo_end, 'last': last,
                          'lcx': lcx})
        return plans

    def hand_pos(self, pl, t):
        sch, ed = pl['sch'], pl['ed']
        OFF = (1250, 2150)
        if not sch:
            return None
        lerp = lambda a, b, k: (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        if t < sch[0][1]:
            return lerp(OFF, sch[0][0].pos(0, t), eio(t / max(sch[0][1], 0.01)))
        for i, (it, s, e) in enumerate(sch):
            if s <= t <= e:
                return it.pos((t - s) / max(e - s, 1e-3), t)
            if i + 1 < len(sch) and e < t < sch[i + 1][1]:
                return lerp(it.pos(1, t), sch[i + 1][0].pos(0, t), eio((t - e) / max(sch[i + 1][1] - e, 1e-3)))
        k = (t - ed) / EXIT
        if k >= 1:
            return None
        return lerp(sch[-1][0].pos(1, t), OFF, eio(k))

    def frame(self, pl, t, first, prog=None):
        f = self.paper.copy()
        if not pl['logo_end']:
            lg = with_alpha(self.logo_small, eo(t / 0.4) if first else 1.0)
            f.paste(lg, (70, 215), lg)
        if self.label is not None:
            f.paste(self.label, (W - 150 - self.label.width, 230), self.label)
        if pl['logo_end']:
            k = eo((t - 0.1) / 0.6)
            if k > 0:
                lg = with_alpha(self.logo_big, k)
                f.paste(lg, (int(pl.get('lcx', W / 2) - lg.width / 2), int(420 + (1 - k) * 30)), lg)
        for it, s, e in pl['sch']:
            if isinstance(it, Fill):
                it.draw(f, (t - s) / max(e - s, 1e-3))
        for it, s, e in pl['sch']:
            if not isinstance(it, Fill):
                it.draw(f, (t - s) / max(e - s, 1e-3))
        if prog is not None:
            d = ImageDraw.Draw(f)
            d.rounded_rectangle((70, 1478, 900, 1490), 6, fill=(232, 232, 228))
            d.rounded_rectangle((70, 1478, 70 + max(12, int(830 * clamp(prog))), 1490), 6, fill=ORANGE)
        hp = self.hand_pos(pl, t)
        if hp:
            f.paste(self.hand, (int(hp[0] - self.tip[0]), int(hp[1] - self.tip[1])), self.hand)
        if not pl['last'] and t > pl['dur'] - ERASE:
            self.erase(f, (t - (pl['dur'] - ERASE)) / ERASE)
        return f


def add_hotline(scenes, hotline):
    if hotline and hotline.strip() and scenes:
        scenes[-1]['lines'].append(('Hotline: ' + hotline.strip(), ['xanh', 'nho']))
        if not any('logo' in t for _, t in scenes[-1]['lines']):
            scenes[-1]['lines'].append(('', ['logo']))


def preview(script_text, logo_path, out_png, auto=True, label=None, hotline=None, gender=None):
    scenes = parse_script(script_text)
    if auto:
        auto_style(scenes)
    add_hotline(scenes, hotline)
    r = Renderer(logo_path, label)
    plans = r.plan(scenes, None, gender)
    thumbs = [r.frame(pl, pl['ed'] + EXIT + 0.05, False).resize((360, 640)) for pl in plans]
    cols = min(len(thumbs), 4)
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new('RGB', (cols * 370 + 10, rows * 650 + 10), (70, 70, 70))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (10 + (i % cols) * 370, 10 + (i // cols) * 650))
    sheet.save(out_png)
    return out_png


def render(script_text, opts, progress=lambda msg, frac: None):
    """opts: voice ('hoaimy'|'namminh'|'eleven'|'none'), rate, eleven_key, eleven_voice, eleven_model,
    music, music_vol (0-100), logo, out_path"""
    scenes = parse_script(script_text)
    if opts.get('auto', True):
        auto_style(scenes)
    add_hotline(scenes, opts.get('hotline'))
    out_path = opts['out_path']
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='vevideo_')
    try:
        voice = opts.get('voice', 'hoaimy')
        durs, wavs = [], []
        if voice == 'vieneu':
            idx = [i for i, sc in enumerate(scenes) if ' '.join(sc['say']).strip()]
            raws = [os.path.join(tmp, 'r%d.wav' % i) for i in idx]
            vieneu_run({'texts': [clean_say(' '.join(scenes[i]['say'])) for i in idx], 'outs': raws,
                        'voice': opts.get('vieneu_voice') or None, 'ref_audio': opts.get('vieneu_ref') or None},
                       lambda m, f: progress(m, 0.02 + 0.25 * (f if f is not None else 0)))
            tempo = 1 + int(opts.get('rate', 0)) / 100.0
            got = {}
            for i, rw in zip(idx, raws):
                wv = os.path.join(tmp, 'v%d.wav' % i)
                to_wav(rw, wv, tempo)
                got[i] = wv
            for i in range(len(scenes)):
                wavs.append(got.get(i))
                durs.append(wav_dur(got[i]) if i in got else None)
            voice = '_done'
        for i, sc in enumerate(scenes):
            if voice == '_done':
                break
            say = ' '.join(sc['say']).strip()
            if voice == 'none' or not say:
                durs.append(None); wavs.append(None)
                continue
            progress('Đang tạo giọng đọc cảnh %d/%d...' % (i + 1, len(scenes)), 0.02 + 0.25 * i / len(scenes))
            mp3 = os.path.join(tmp, 'v%d.mp3' % i)
            if voice == 'eleven':
                tts_eleven(say, opts.get('eleven_key'), opts.get('eleven_voice'), opts.get('eleven_model', ''), mp3)
            elif voice == '_test':
                run_ff(['-f', 'lavfi', '-i', 'sine=frequency=330:duration=%.2f' % (len(say) * 0.065), mp3])
            else:
                if i > 0:
                    import time as _t
                    _t.sleep(0.8)
                tts_edge(say, VOICES.get(voice, VOICES['hoaimy']), int(opts.get('rate', 0)), mp3)
            wv = os.path.join(tmp, 'v%d.wav' % i)
            to_wav(mp3, wv)
            durs.append(wav_dur(wv)); wavs.append(wv)

        progress('Đang dàn trang...', 0.28)
        r = Renderer(opts.get('logo'), opts.get('label'))
        plans = r.plan(scenes, durs, resolve_gender(opts))
        total_frames = sum(p['n'] for p in plans)
        done = 0
        files = []
        for i, pl in enumerate(plans):
            part = os.path.join(tmp, 's%d.mp4' % i)
            proc = subprocess.Popen([ffmpeg_exe(), '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                                     '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-', '-c:v', 'libx264',
                                     '-crf', '19', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', part],
                                    stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NOWIN)
            try:
                for k in range(pl['n']):
                    proc.stdin.write(r.frame(pl, k / FPS, i == 0, (done + 1) / total_frames).tobytes())
                    done += 1
                    if done % 15 == 0:
                        progress('Đang vẽ cảnh %d/%d...' % (i + 1, len(plans)), 0.3 + 0.62 * done / total_frames)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            if proc.wait() != 0:
                raise VideoError('Lỗi khi ghi video: ' + proc.stderr.read().decode('utf-8', 'ignore')[-500:])
            files.append(part)

        progress('Đang ghép video và âm thanh...', 0.93)
        lst = os.path.join(tmp, 'list.txt')
        with open(lst, 'w', encoding='utf-8') as fh:
            fh.writelines("file '%s'\n" % p.replace('\\', '/') for p in files)
        joined = os.path.join(tmp, 'joined.mp4')
        run_ff(['-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', joined])

        narr = os.path.join(tmp, 'narr.wav')
        rate_hz, lead = 44100, 0.12
        with wave.open(narr, 'wb') as out:
            out.setnchannels(2); out.setsampwidth(2); out.setframerate(rate_hz)
            for pl, wv in zip(plans, wavs):
                total = int(round(pl['n'] / FPS * rate_hz))
                data = b''
                if wv:
                    with wave.open(wv) as w_in:
                        data = w_in.readframes(w_in.getnframes())
                    data = b'\x00' * 4 * int(lead * rate_hz) + data
                data = data[:total * 4]
                out.writeframes(data + b'\x00' * (total * 4 - len(data)))

        tmp_out = out_path + '.dang-tao.mp4'
        music = opts.get('music')
        if music and os.path.exists(music):
            vol = max(0, min(100, int(opts.get('music_vol', 12)))) / 100.0
            fade_st = max(0, wav_dur(narr) - 1.5)
            run_ff(['-i', joined, '-i', narr, '-stream_loop', '-1', '-i', music, '-filter_complex',
                    '[1:a]asplit=2[n1][n2];'
                    '[2:a]volume=%.3f,afade=t=out:st=%.2f:d=1.5[m];'
                    '[m][n1]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[md];'
                    '[n2][md]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]' % (vol * 1.6, fade_st),
                    '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', tmp_out])
        else:
            run_ff(['-i', joined, '-i', narr, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac',
                    '-b:a', '192k', '-shortest', '-movflags', '+faststart', tmp_out])
        os.replace(tmp_out, out_path)
        progress('Xong!', 1.0)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


import hinhve as _hv  # noqa: E402
_hv.E = sys.modules[__name__]
ICON_NAMES = ICON_NAMES + ', ' + ', '.join(_hv.NAMES)
