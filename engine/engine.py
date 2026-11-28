# -*- coding: utf-8 -*-
"""Bộ máy dựng video vẽ tay – Du Học Hải Dương."""
import json, math, os, random, re, shutil, subprocess, sys, tempfile, unicodedata, wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import stroke as _stroke
except Exception:                     # chạy từ thư mục khác
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stroke as _stroke
STROKE = True        # True = vẽ từng nét như người thật; False = quét nhanh (kiểu cũ)

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
SUB_Y = 1366         # đỉnh dòng phụ đề karaoke (khi bật phụ đề, nội dung dồn lên trên một chút)
SUB_MAXW = 960
SUB_ON, SUB_OFF = (238, 128, 20), (34, 36, 48)
ERASE = 0.5          # thời gian lau bảng khi chuyển cảnh
LCX, LMAXW = W / 2, 960   # cột nội dung (đổi khi có nhân vật đứng bên trái)

# ------------------------------------------------------------------ khung hình (dọc / ngang / vuông / 4:5)
FORMATS = {
    # TikTok, Reels, Shorts: phía dưới bị chữ của app che -> nội dung dừng ở 1460
    'doc': dict(W=1080, H=1920, top=400, bottom=1460, logo_xy=(70, 215), logo_w=170, label_y=230, label_r=150,
                bar=(70, 1478, 900), erase=(390, 1500), char=(215, 1462, 1.0), col_char=(W / 2 + 170, 640),
                col_like=(W / 2 + 165, 640), col_full=(W / 2, 960), end_top=900, big_logo=(440, 460), big_logo_y=420,
                sub_y=1366, sub_w=960, hand_off=(1250, 2150), wide=False, ruled_top=330, thumb=(432, 768)),
    # YouTube, Facebook thường
    'ngang': dict(W=1920, H=1080, top=150, bottom=985, logo_xy=(50, 30), logo_w=140, label_y=42, label_r=60,
                  bar=(60, 1048, 1860), erase=(120, 1040), char=(270, 1040, 1.02), col_char=(1235, 1180),
                  col_like=(1235, 1180), col_full=(960, 1560), end_top=520, big_logo=(380, 360), big_logo_y=130,
                  sub_y=930, sub_w=1600, hand_off=(2150, 1500), wide=True, ruled_top=110, thumb=(640, 360)),
    # bài Facebook / Instagram vuông
    'vuong': dict(W=1080, H=1080, top=165, bottom=1000, logo_xy=(45, 30), logo_w=130, label_y=40, label_r=50,
                  bar=(50, 1046, 1030), erase=(140, 1040), char=(190, 1040, 0.98), col_char=(W / 2 + 150, 660),
                  col_like=(W / 2 + 150, 660), col_full=(W / 2, 960), end_top=560, big_logo=(340, 330), big_logo_y=150,
                  sub_y=950, sub_w=960, hand_off=(1250, 1500), wide=False, ruled_top=120, thumb=(480, 480)),
    # bài Facebook / Instagram dọc 4:5
    'doc45': dict(W=1080, H=1350, top=210, bottom=1270, logo_xy=(55, 45), logo_w=150, label_y=55, label_r=55,
                  bar=(55, 1310, 1025), erase=(190, 1300), char=(205, 1290, 1.0), col_char=(W / 2 + 165, 650),
                  col_like=(W / 2 + 165, 650), col_full=(W / 2, 960), end_top=700, big_logo=(400, 400), big_logo_y=170,
                  sub_y=1185, sub_w=960, hand_off=(1250, 1800), wide=False, ruled_top=170, thumb=(432, 540)),
}
FORMAT_NAMES = [('doc', 'Dọc 9:16 – TikTok, Reels, Shorts'), ('ngang', 'Ngang 16:9 – YouTube, Facebook'),
                ('vuong', 'Vuông 1:1 – bài đăng Facebook/Instagram'), ('doc45', 'Dọc 4:5 – bài đăng Facebook/Instagram')]
LAY = dict(FORMATS['doc'])


def set_format(name):
    """Đổi khung hình cho cả bộ máy (gọi trước khi dựng)."""
    global W, H, LAY, TOP_AREA, BOTTOM_AREA, SUB_Y, SUB_MAXW, LCX, LMAXW
    LAY = dict(FORMATS.get(name) or FORMATS['doc'])
    W, H = LAY['W'], LAY['H']
    TOP_AREA, BOTTOM_AREA = LAY['top'], LAY['bottom']
    SUB_Y, SUB_MAXW = LAY['sub_y'], LAY['sub_w']
    LCX, LMAXW = LAY['col_full']
    CharItem._cache.clear()
    Txt._plans.clear()
    return LAY

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


BG_STYLES = [('trang', 'Bảng trắng'), ('o_vuong', 'Giấy kẻ ô'), ('ke_dong', 'Giấy vở kẻ dòng'),
             ('cham_bi', 'Giấy chấm bi'), ('giay_vang', 'Giấy vàng ấm'), ('khung_bang', 'Bảng trắng có khung'),
             ('xanh_nhat', 'Nền xanh dịu')]


def make_paper(style='trang'):
    rng = np.random.default_rng(3)
    base = {'giay_vang': (250, 243, 222), 'xanh_nhat': (236, 245, 252)}.get(style, PAPER)
    n = rng.normal(0, 2.2, (H, W, 1))
    im = Image.fromarray(np.clip(np.array(base)[None, None, :] + n, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    if style == 'o_vuong':
        for x in range(0, W, 54):
            d.line((x, 0, x, H), fill=(214, 226, 242), width=2)
        for y in range(18, H, 54):
            d.line((0, y, W, y), fill=(214, 226, 242), width=2)
    elif style == 'ke_dong':
        for y in range(LAY.get('ruled_top', 330), H, 66):
            d.line((0, y, W, y), fill=(200, 218, 240), width=3)
        d.line((92, 0, 92, H), fill=(240, 170, 170), width=3)
        d.line((100, 0, 100, H), fill=(240, 170, 170), width=2)
    elif style == 'cham_bi':
        for y in range(30, H, 48):
            for x in range(30 if (y // 48) % 2 == 0 else 54, W, 48):
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(192, 201, 218))
    elif style == 'khung_bang':
        for i, c in enumerate([(150, 156, 168), (200, 205, 214), (175, 181, 192)]):
            d.rectangle((i * 7, i * 7, W - 1 - i * 7, H - 1 - i * 7), outline=c, width=7)
        d.rounded_rectangle((W / 2 - 170, H - 62, W / 2 + 170, H - 30), 8, fill=(190, 195, 205))
    return im


# ------------------------------------------------------------------ nét vẽ
class Txt:
    PAD = 14

    def __init__(self, text, size, color, cy, cx=None, left=None, segs=None):
        cx = W / 2 if cx is None else cx
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
        self.sp = None
        if STROKE:
            try:
                key = (text, int(size), tuple(c for _, c in segs))
                if key not in Txt._plans:
                    a = np.asarray(im)
                    Txt._plans[key] = _stroke.plan(a[:, :, 3] > 90, 'text', size)
                self.sp = Txt._plans[key]
                if self.sp is not None:
                    self._arr = np.asarray(im).copy()
                    self.dur = max(0.4, len(text) * CPS * 1.25)
            except Exception:
                self.sp = None

    _plans = {}

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
        if self.sp is not None:
            rev = self.sp[0]
            a = self._arr.copy()
            a[:, :, 3] = np.where(rev <= r, a[:, :, 3], 0)
            c = Image.fromarray(a)
            f.paste(c, (self.x, self.y), c)
            return
        wv = int(self.im.width * r)
        if wv > 0:
            c = self.im.crop((0, 0, wv, self.im.height))
            f.paste(c, (self.x, self.y), c)

    def pos(self, r, t):
        if self.sp is not None:
            q = _stroke.pen_at(self.sp[1], clamp(r))
            if q:
                return (self.x + q[0], self.y + q[1])
        return (self.left + (self.right - self.left) * clamp(r), self.cy + 10 * math.sin(t * 38))


REVEAL = 'net'      # 'net': vẽ từng nét rồi tô bằng cọ | 'quet': quét 3 bước | 'loang': nét đen rồi màu loang theo nét


def clean_specks(la, thr=40):
    """Bỏ các chấm đen nhỏ lẻ (vụn, nhiễu) khỏi bản nét; giữ nét thật."""
    try:
        from scipy import ndimage
    except Exception:
        return la
    m = la > thr
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return la
    sizes = np.bincount(lab.ravel())
    min_px = max(6, int(la.shape[0] * la.shape[1] * 0.00004))
    small = sizes < min_px
    small[0] = False
    return np.where(small[lab], 0, la).astype(np.uint8)


def loang_map(ink, alpha):
    """Bản đồ thời điểm tô màu kiểu 'loang': mép màu tràn từ trên xuống, gợn sóng như nước,
    gặp nét viền thì khựng lại rồi mới tràn qua. Trả về float32 HxW trong khoảng 0..1."""
    h, w = ink.shape
    spread = int(np.clip(min(w, h) // 64, 3, 17)) | 1
    ink_im = Image.fromarray((ink > 40).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(spread))
    ink_im = ink_im.filter(ImageFilter.GaussianBlur(max(1.0, min(w, h) / 220.0)))
    res = np.asarray(ink_im).astype(np.float32)
    res /= max(1e-6, float(res.max()))
    for row in range(1, h):                                  # mỗi nét viền đổ 'bóng cản' nhạt dần xuống dưới
        np.maximum(res[row], res[row - 1] * 0.94, out=res[row])
    xs = np.arange(w, dtype=np.float32)
    wave = np.sin(xs / max(24.0, w / 20.0)) + 0.35 * np.sin(xs / max(8.0, w / 72.0) + 1.7)
    delay = float(np.clip(h * 0.06, 12, 52))
    ys = np.arange(h, dtype=np.float32)[:, None]
    lead = ys - wave[None, :] * delay * 0.45 + res * delay  # mép màu phải đi tới 'lead' thì điểm này mới hiện
    lo, hi = -delay, h + 1.6 * delay
    return np.clip((lead - lo) / (hi - lo), 0, 1).astype(np.float32)


class CharItem:
    """Hình (nhân vật, ảnh trong kho): vẽ nét đen trước, rồi tô màu bằng nét cọ theo từng nhóm màu."""
    _cache = {}

    def __init__(self, path, cx, feet_y, height):
        key = (path, int(height), REVEAL)
        if key not in CharItem._cache:
            im = Image.open(path).convert('RGBA')
            im = im.resize((int(im.width * height / im.height), int(height)), Image.LANCZOS)
            a = np.asarray(im).astype(np.int32)
            mx, mn = a[:, :, :3].max(axis=2), a[:, :, :3].min(axis=2)
            la = np.where((mx < 75) & (mx - mn < 30) & (a[:, :, 3] > 0), a[:, :, 3], 0).astype(np.uint8)
            la = clean_specks(la)                  # bỏ chấm vụn lấm tấm để nét vẽ ra sạch
            if REVEAL == 'quet':                   # nét chì xám: lấy độ tối của toàn ảnh
                gray = 255 - a[:, :, :3].mean(axis=2)
                shade = np.clip(np.where(a[:, :, 3] > 0, gray * 0.45, 0), 0, 95)
                la = np.maximum(la.astype(np.float32), shade).astype(np.uint8)
            lines = Image.new('RGBA', im.size, (30, 30, 36, 0) if REVEAL != 'quet' else (90, 90, 96, 0))
            lines.putalpha(Image.fromarray(la))
            sp = bp = None
            if STROKE and REVEAL != 'quet':
                try:
                    sp = _stroke.plan(la > 40, 'img', 40)
                except Exception:
                    sp = None
                try:
                    arr8 = np.asarray(im)
                    bp = _stroke.brush(arr8, arr8[:, :, 3] > 40, seed=int(height) % 97)
                except Exception:
                    bp = None
            if REVEAL == 'loang':
                try:
                    bp = (loang_map(la, np.asarray(im)[:, :, 3]), None)
                except Exception:
                    pass
            CharItem._cache[key] = (im, lines, sp, np.asarray(lines).copy(), bp, np.asarray(im).copy())
        self.im, self.lines, self.sp, self._larr, self.bp, self._carr = CharItem._cache[key]
        self.x = int(cx - self.im.width / 2)
        self.y = int(feet_y - self.im.height)
        self.dur = 2.4 if self.sp is not None else 1.6
        self.LE = 0.5 if self.bp is not None else (0.72 if self.sp is not None else 0.6)

    def draw(self, f, r):
        if r <= 0:
            return
        if r >= 1:
            f.paste(self.im, (self.x, self.y), self.im)
            return
        LE = self.LE
        rl = clamp(r / LE)
        if REVEAL == 'quet':                       # quét ngang: nét chì trước, màu sau
            wl = int(self.im.width * eio(rl))
            if r > LE:
                wc = int(self.im.width * eio((r - LE) / (1 - LE)))
                f.paste(self.lines, (self.x, self.y), self.lines)
                if wc > 0:
                    c = self.im.crop((0, 0, wc, self.im.height))
                    f.paste(c, (self.x, self.y), c)
            elif wl > 0:
                c = self.lines.crop((0, 0, wl, self.im.height))
                f.paste(c, (self.x, self.y), c)
            return
        if self.sp is not None:
            a = self._larr if rl >= 1 else self._larr.copy()
            if rl < 1:
                a[:, :, 3] = np.where(self.sp[0] <= rl, a[:, :, 3], 0)
            c = Image.fromarray(a)
            f.paste(c, (self.x, self.y), c)
        else:
            hh = int(self.lines.height * rl)
            if hh > 0:
                c = self.lines.crop((0, 0, self.lines.width, hh))
                f.paste(c, (self.x, self.y), c)
        if r > LE:
            rc = (r - LE) / (1 - LE)
            if self.bp is not None:
                a = self._carr.copy()
                a[:, :, 3] = np.where(self.bp[0] <= (eio(rc) if self.bp[1] is None else rc), a[:, :, 3], 0)
                col = Image.fromarray(a)
            else:
                col = with_alpha(self.im, clamp(rc))
            f.paste(col, (self.x, self.y), col)

    def pos(self, r, t):
        w, h = self.im.width, self.im.height
        LE = self.LE
        if REVEAL == 'quet':
            k = eio(clamp(r / LE)) if r < LE else eio(clamp((r - LE) / (1 - LE)))
            return (self.x + w * k, self.y + h * (0.5 + 0.38 * math.sin(t * 11)))
        if r < LE and self.sp is not None:
            q = _stroke.pen_at(self.sp[1], clamp(r / LE))
            if q:
                return (self.x + q[0], self.y + q[1])
        if r < LE and self.sp is None:
            rl = clamp(r / LE)
            return (self.x + w * (0.5 + 0.4 * math.sin(rl * 60)), self.y + h * rl)
        if self.bp is not None and self.bp[1] is None and r >= LE:   # loang: tay quét qua lại dọc theo mép màu
            rc = eio(clamp((r - LE) / (1 - LE)))
            d = 0.06 * h
            fy = -d + rc * (h + 1.6 * d) - d * 0.6
            lane = (rc * 7.0) % 2.0
            lane = lane if lane <= 1 else 2 - lane
            return (self.x + w * (0.12 + 0.76 * eio(lane)), self.y + clamp(fy / h) * h)
        if self.bp is not None and self.bp[1] is not None:
            q = _stroke.pen_at(self.bp[1], clamp((r - LE) / (1 - LE)))
            if q:
                return (self.x + q[0], self.y + q[1])
        return (self.x + w * (0.5 + 0.3 * math.sin(t * 9)), self.y + h * (0.45 + 0.2 * math.cos(t * 7)))


class PhotoItem(CharItem):
    """Ảnh THẬT (ảnh trường): không vẽ nét/tô màu. Khung viền như ảnh dán lên bảng, hiện dần kèm
    phóng/lia nhẹ (Ken Burns). Chỉ phóng đều hai chiều nên ảnh không bao giờ bị méo."""
    _pcache = {}

    def __init__(self, path, cx, feet_y, height):
        key = (path, int(height))
        if key not in PhotoItem._pcache:
            src = Image.open(path).convert('RGB')
            B = max(6, int(height * 0.022))                  # viền trắng
            ih = int(height) - 2 * B
            iw = max(40, int(src.width * ih / src.height))
            src = src.resize((int(iw * 1.12), int(ih * 1.12)), Image.LANCZOS)   # dư 12% để lia/phóng
            PhotoItem._pcache[key] = (src, iw, ih, B)
        self.src, self.iw, self.ih, self.B = PhotoItem._pcache[key]
        W0, H0 = self.iw + 2 * self.B, self.ih + 2 * self.B
        self.im = self._frame(1.0)
        self.x = int(cx - W0 / 2)
        self.y = int(feet_y - H0)
        self.sp = self.bp = None
        self.lines = None
        self.dur = 1.5
        self.LE = 1.0
        self.nohand = True

    def _frame(self, z):
        """Ảnh trong khung; z = độ phóng nội dung (1.0 = cỡ cuối)."""
        B, iw, ih = self.B, self.iw, self.ih
        sw, sh = self.src.size
        cw, ch = sw / (1.12 * z), sh / (1.12 * z)         # vùng cắt cùng tỉ lệ khung -> không méo
        ox, oy = (sw - cw) * 0.5, (sh - ch) * 0.42
        inner = self.src.crop((int(ox), int(oy), int(ox + cw), int(oy + ch))).resize((iw, ih), Image.BILINEAR)
        out = Image.new('RGBA', (iw + 2 * B, ih + 2 * B), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        d.rounded_rectangle((0, 0, out.width - 1, out.height - 1), B * 2, fill=(255, 255, 255, 255),
                            outline=(40, 40, 46, 255), width=max(3, B // 3))
        m = Image.new('L', (iw, ih), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, iw - 1, ih - 1), B, fill=255)
        out.paste(inner, (B, B), m)
        return out

    def draw(self, f, r):
        if r <= 0:
            return
        if r >= 1:
            f.paste(self.im, (self.x, self.y), self.im)
            return
        e = eio(clamp(r))
        fr = self._frame(1.0 + 0.10 * (1 - e))             # nội dung lùi dần từ cận về toàn cảnh
        k = 0.93 + 0.07 * e                                 # cả khung lớn dần (đều hai chiều)
        w, h = max(1, int(fr.width * k)), max(1, int(fr.height * k))
        fr = with_alpha(fr.resize((w, h), Image.BILINEAR), clamp(r * 2.2))
        cx, cy = self.x + self.im.width / 2, self.y + self.im.height / 2
        f.paste(fr, (int(cx - w / 2), int(cy - h / 2)), fr)

    def pos(self, r, t):
        return (self.x + self.im.width / 2, self.y + self.im.height / 2)


def is_photo(path):
    """Ảnh thật = file .jpg (kho ảnh trường lưu ảnh chụp dạng .jpg; logo, hình vẽ dạng .png)."""
    return path.lower().endswith(('.jpg', '.jpeg'))


NV_DIR = os.path.join(ASSETS, 'nhanvat')


CHAR_OVERRIDE = None   # thư mục nhân vật riêng của từng nhân viên (bản web)
CHAR_LV = None         # thư mục nhân vật của lĩnh vực (vd assets/lv/ngoi/nhanvat): ưu tiên hơn nhân vật du học


def char_path(gender, pose):
    for d in ((CHAR_LV, CHAR_OVERRIDE, NV_DIR) if CHAR_LV else (CHAR_OVERRIDE, NV_DIR)):
        if d:
            p = os.path.join(d, '%s_%s.png' % (gender, pose))
            if os.path.exists(p):
                return p
    return None


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


class Hachure(Fill):
    """Tô nền bằng các nét gạch chéo như Excalidraw (hiện dần theo đường chéo)."""

    def __init__(self, x0, y0, x1, y1, color, seed=0, alpha=0.28, gapx=18, width=4):
        self.x0, self.y0 = int(x0), int(y0)
        w, h = max(2, int(x1 - x0)), max(2, int(y1 - y0))
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rnd = random.Random(seed)
        c = tuple(color) + (int(255 * alpha),)
        k = -h
        while k < w:
            j = rnd.uniform(-3, 3)
            d.line([(k + j, h + 2), (k + h + j + rnd.uniform(-4, 4), -2)], fill=c, width=width)
            k += gapx + rnd.uniform(-3, 3)
        m = Image.new('L', (w, h), 0)                                   # góc hơi bo cho giống vẽ tay
        ImageDraw.Draw(m).rounded_rectangle((3, 3, w - 4, h - 4), 14, fill=255)
        im.putalpha(Image.fromarray(np.minimum(np.asarray(im)[:, :, 3], np.asarray(m))))
        self.im = im
        self._diag = (np.add.outer(np.arange(h), np.arange(w)) / float(w + h)).astype(np.float32)
        self._arr = np.asarray(im).copy()
        self.c = (x0 + w / 2, y0 + h / 2)
        self.r = min(w, h) * 0.3
        self.w, self.h = w, h
        self.dur = 0.35

    def draw(self, f, r):
        if r <= 0:
            return
        if r >= 1:
            f.paste(self.im, (self.x0, self.y0), self.im)
            return
        a = self._arr.copy()
        a[:, :, 3] = np.where(self._diag <= r, a[:, :, 3], 0)
        c = Image.fromarray(a)
        f.paste(c, (self.x0, self.y0), c)

    def pos(self, r, t):
        k = clamp(r) * (self.w + self.h)
        x = min(self.w, k)
        return (self.x0 + x, self.y0 + (k - x) + 0 * t)


def rough_box(x0, y0, x1, y1, color, seed=0, width=7, fill=True):
    """Khung vẽ tay kiểu Excalidraw: nền gạch chéo + viền 2 lượt hơi lệch, đầu nét chờm qua góc."""
    rnd = random.Random(seed)
    out = []
    if fill:
        out.append(Hachure(x0 + 4, y0 + 4, x1 - 4, y1 - 4, color, seed=seed))
    for k in range(2):
        j = lambda: rnd.uniform(-5, 5)
        o = 6 + 4 * k
        pts = [(x0 + j() - o * 0.5, y0 + j()), (x1 + j() + o, y0 + j()), (x1 + j(), y1 + j() + o * 0.4),
               (x0 + j() - o * 0.3, y1 + j()), (x0 + j(), y0 + j() - o)]
        pa = Path(poly(pts, seed=seed + 11 * k, bow=6 + 3 * k), color, width if k == 0 else max(3, width - 3))
        pa.dur *= 0.55 if k else 1.0
        if k:
            pa.gap = 0.02
        out.append(pa)
    return out


def curved_arrow(x0, y0, x1, y1, color, seed=0, width=7, head=28, bend=0.18):
    """Mũi tên cong vẽ tay (đầu mũi tên 2 nét riêng như người vẽ)."""
    rnd = random.Random(seed)
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    b = L * bend * (1 if rnd.random() > 0.5 else -1)
    n = max(10, int(L / 7))
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append((x0 + dx * u + nx * b * math.sin(math.pi * u) * (1 - 0.3 * u),
                    y0 + dy * u + ny * b * math.sin(math.pi * u) * (1 - 0.3 * u)))
    pts = wobble(pts, 1.6, seed)
    ex, ey = pts[-1]
    px, py = pts[-4]
    ang = math.atan2(ey - py, ex - px)
    shaft = Path(pts, color, width)
    h1 = Path(seg((ex - head * math.cos(ang - 0.45), ey - head * math.sin(ang - 0.45)), (ex, ey), bow=2, seed=seed + 1), color, width)
    h2 = Path(seg((ex, ey), (ex - head * math.cos(ang + 0.45), ey - head * math.sin(ang + 0.45)), bow=2, seed=seed + 2), color, width)
    h1.gap = h2.gap = 0.02
    h1.dur = h2.dur = 0.12
    return [shaft, h1, h2]


class Marker(Fill):
    """Bút dạ vàng tô ngang chữ nổi bật đúng lúc giọng đọc nhắc tới."""

    def __init__(self, x0, x1, cy, size, color=(255, 210, 40), seed=0):
        h = int(size * 0.62)
        w = max(10, int(x1 - x0 + 24))
        im = Image.new('RGBA', (w, h + 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rnd = random.Random(seed)
        pts = []
        for i in range(0, w + 1, 6):
            pts.append((i, 8 + rnd.uniform(-2.5, 2.5)))
        for i in range(w, -1, -6):
            pts.append((i, 8 + h + rnd.uniform(-2.5, 2.5)))
        d.polygon(pts, fill=tuple(color) + (125,))
        self.im = im
        self.x0, self.y0 = int(x0 - 12), int(cy - h / 2 + size * 0.08 - 8)
        self.w = w
        self.c = (self.x0 + w / 2, cy)
        self.r = 4
        self.dur = max(0.25, w / 1800)

    def draw(self, f, r):
        if r <= 0:
            return
        wv = self.w if r >= 1 else int(self.w * eio(r))
        if wv > 0:
            c = self.im.crop((0, 0, wv, self.im.height))
            f.paste(c, (self.x0, self.y0), c)

    def pos(self, r, t):
        return (self.x0 + self.w * eio(clamp(r)), self.y0 + self.im.height * 0.75)


class Badge:
    """Huy hiệu tiến độ "1/3" ở góc phải trên: vòng tròn vẽ tay + số."""

    def __init__(self, text, seed=0):
        s = 1.0 if LAY['H'] > LAY['W'] else 0.78
        self.cx, self.cy = W - 120 * s - (40 if LAY.get('wide') else 0), TOP_AREA - 70 * s
        if LAY['H'] > LAY['W'] and LAY['label_y'] + 80 > self.cy - 60 * s:
            self.cy = LAY['label_y'] + 150
        self.ring = Path(ellipse(self.cx, self.cy, 78 * s, 56 * s, seed=seed), ORANGE, 7)
        self.txt = Txt(text, int(62 * s), ORANGE, self.cy, cx=self.cx)
        self.dur = self.ring.dur + self.txt.dur

    def draw(self, f, r):
        k = self.ring.dur / self.dur
        self.ring.draw(f, r / k if k else 1)
        if r > k:
            self.txt.draw(f, (r - k) / (1 - k))

    def pos(self, r, t):
        k = self.ring.dur / self.dur
        return self.ring.pos(r / k, t) if r < k else self.txt.pos((r - k) / (1 - k), t)


GREEN = (30, 140, 70)
PURPLE = (130, 60, 170)


KHO_DIR = os.path.join(ASSETS, 'kho')
_kho = {'mtime': None, 'idx': {}}
KHO_GENERIC = {'du hoc', 'han quoc', 'dai loan', 'hoc sinh', 'sinh vien', 'viet nam', 'truong hoc', 'dai hoc'}
KHO_STOP = {'va', 'cua', 'o', 'tai', 'voi', 'cho', 'la', 'cac', 'nhung', 'mot', 'trong', 'tren', 'duoi', 'anh', 'chi'}


KHO_TRUONG = None   # thư mục ảnh thật của trường đang làm video (assets/truong/<mã>): ưu tiên trước kho chung
KHO_LV = None   # thư mục kho riêng của lĩnh vực khác (vd assets/kho_ngoi); None = kho du học như cũ


def _kho_chung():
    """Tên file trong kho du học dùng chung được cho mọi lĩnh vực (assets/kho/_chung.json)."""
    try:
        with open(os.path.join(KHO_DIR, '_chung.json'), encoding='utf-8') as f:
            return set(json.load(f))
    except Exception:
        return set()


def kho_index():
    """{tên chuẩn hóa: đường dẫn} của các ảnh trong Kho hình (lĩnh vực khác: kho riêng + hình dùng chung)."""
    try:
        mt = (KHO_LV, KHO_TRUONG, os.path.getmtime(KHO_DIR), os.path.getmtime(KHO_LV) if KHO_LV and os.path.isdir(KHO_LV) else 0,
              os.path.getmtime(KHO_TRUONG) if KHO_TRUONG and os.path.isdir(KHO_TRUONG) else 0)
    except OSError:
        return {}
    if _kho['mtime'] != mt:
        idx = {}
        chung = _kho_chung() if KHO_LV else None
        dirs = [KHO_DIR] + ([KHO_LV] if KHO_LV and os.path.isdir(KHO_LV) else []) + \
            ([KHO_TRUONG] if KHO_TRUONG and os.path.isdir(KHO_TRUONG) else [])
        for d in dirs:
            for f in sorted(os.listdir(d)):
                ext = os.path.splitext(f)[1].lower()
                if (ext == '.png' or (d == KHO_TRUONG and ext in ('.jpg', '.jpeg'))) and not f.startswith('_'):
                    if d == KHO_DIR and chung is not None and f not in chung:
                        continue
                    idx[norm(re.sub(r'[_\-]+', ' ', os.path.splitext(f)[0]))] = os.path.join(d, f)
        _kho.update(mtime=mt, idx=idx)
    return _kho['idx']


def kho_has(name):
    return norm(name) in kho_index()


KHO_TUKHOA = os.path.join(KHO_DIR, '_tu_khoa.json')   # {ten_file_khong_duoi: {"ten": "...", "tu_khoa": [...]}}


def kho_meta():
    out = {}
    for p in [KHO_TUKHOA] + ([os.path.join(KHO_LV, '_tu_khoa.json')] if KHO_LV else []) + \
            ([os.path.join(KHO_TRUONG, '_anh.json')] if KHO_TRUONG else []):
        try:
            with open(p, encoding='utf-8') as f:
                out.update(json.load(f))
        except Exception:
            pass
    return out


def kho_keywords():
    out = {}
    meta = {norm(k.replace('_', ' ')): v for k, v in kho_meta().items()}
    for n in kho_index():
        extra = meta.get(n, {})
        for kw0 in [extra.get('ten', '')] + list(extra.get('tu_khoa', [])):
            kw = norm(kw0)
            acronym = kw0.strip().isupper() and len(kw0.strip()) >= 4      # TOPIK, TOCFL, VISA: giữ dù chỉ 1 chữ
            if kw and (len(kw.split()) >= 2 or acronym) and kw not in KHO_GENERIC:   # bỏ từ lẻ 1 chữ để tránh gắn nhầm
                # có dấu -> so khớp CÓ DẤU (để 'trúng tâm' không khớp 'trung tâm')
                acc = _acc_words(kw0).strip()
                out.setdefault(n, set()).add(('~' + acc) if acc != kw else kw)
    # từ khoá dùng chung cho >=4 hình là quá chung chung -> bỏ
    cnt = {}
    for ks in out.values():
        for k in ks:
            cnt[k] = cnt.get(k, 0) + 1
    for n in list(out):
        out[n] = {k for k in out[n] if cnt[k] < 4}
    for n in kho_index():
        w = [x for x in n.split() if x not in KHO_STOP]
        keys = {n}
        if n in meta:          # hình đã có tên + từ khoá chuẩn: không cắt tên file thành cặp chữ (tránh 'trúng tâm' = 'trung tâm')
            out[n] = list(keys | set(out.get(n, set())))
            continue
        for i in range(len(w) - 1):
            bg = w[i] + ' ' + w[i + 1]
            if bg not in KHO_GENERIC:
                keys.add(bg)
        out[n] = list(keys | set(out.get(n, set())))
    return out


def big_icon(name):
    return _hv.has(name) or kho_has(name)


def _kho_dst(name, folder=None):
    folder = folder or KHO_DIR
    os.makedirs(folder, exist_ok=True)
    base = re.sub(r'[^a-z0-9]+', '_', norm(name)).strip('_') or 'hinh'
    dst = os.path.join(folder, base + '.png')
    k = 2
    while os.path.exists(dst):
        dst = os.path.join(folder, '%s_%d.png' % (base, k)); k += 1
    return dst


def kho_add(src, name=None, folder=None):
    """Thêm ảnh vào Kho (hoặc kho riêng folder): tách nền, lưu PNG với tên (không dấu, nối bằng _)."""
    dst = _kho_dst(name or os.path.splitext(os.path.basename(src))[0], folder)
    _save_small(remove_bg(src, max_h=1100), dst)
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


def _save_small(im, dst, max_side=900):
    """Lưu PNG gọn nhẹ: thu về cạnh dài tối đa 900px, giảm còn 256 màu (hình vẽ màu phẳng nên gần như không đổi)."""
    im = im.convert('RGBA')
    if max(im.size) > max_side:
        k = max_side / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    try:
        im.quantize(256, method=Image.Quantize.FASTOCTREE).save(dst, optimize=True)
    except Exception:
        im.save(dst, optimize=True)


def _drop_edge_bits(im, frac=0.02):
    """Xoá mẩu nhỏ của hình bên cạnh dính ở mép ô khi cắt lưới, rồi cắt sát phần còn lại."""
    try:
        from scipy import ndimage
    except Exception:
        return im
    a = np.asarray(im.convert('RGBA')).copy()
    m = a[:, :, 3] > 20
    lab, n = ndimage.label(m)
    if n <= 1:
        return im
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    big = sizes.max()
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    for k in edge:
        if sizes[k - 1] < big * frac * 10 and sizes[k - 1] < m.sum() * frac:
            a[lab == k, 3] = 0
    out = Image.fromarray(a)
    bb = out.getbbox()
    return out.crop(bb) if bb else out


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
            _save_small(_drop_edge_bits(remove_bg(tp, max_h=1100)), dst)
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


FX = {'sfx': True, 'punch': True, 'emph': True, 'pop': True}   # hiệu ứng bật/tắt (render.py đặt theo lựa chọn)
TRANS_SND = 'giay'   # tiếng chuyển cảnh: 'giay' (lật giấy êm), 'vut' (gió vút), 'tat' (im lặng, không cả tiếng lau bảng)
EMPH_RUNG = ('canh bao', 'lua dao', 'bi tu choi', 'truot', 'phat', 'cam ', 'sai', 'gia', 'mat tien', 'bo hoc',
             'lo lang', 'that bai', 'nguy hiem', 'loi')
EMPH_NAY = ('cup', 'chien thang', 'nhan visa', 'do visa', 'hoc bong', 'vui mung', 'thanh cong', 've dich',
            'giay khen', 'tot nghiep', 'diem cao', 'tich', 'dung')


def emph_of(name):
    n = ' ' + norm(name or '') + ' '
    if any((' ' + k.strip() + ' ') in n for k in EMPH_RUNG):
        return 'rung'
    if any((' ' + k.strip() + ' ') in n for k in EMPH_NAY):
        return 'nay'
    return None


def kho_item(name, cx, cy, h):
    path = kho_index()[norm(name)]
    with Image.open(path) as im:
        w0, h0 = im.size
    maxw = LMAXW * 0.95
    if is_photo(path):                                   # ảnh thật: cho to hơn hình vẽ một chút
        hh = min(h * 1.15, maxw * 1.02 * h0 / w0)
        it = PhotoItem(path, cx, cy + hh / 2, hh)
        it.kname = name
        it.emph = None
        return [it]
    hh = min(h, maxw * h0 / w0)
    it = CharItem(path, cx, cy + hh / 2, hh)
    it.dur = 2.8 if it.bp is not None else 2.4 if it.sp is not None else 1.4
    it.kname = name
    it.emph = emph_of(name)
    return [it]


def make_pop(parts):
    """Hình nhỏ (trong danh sách, thẻ) nảy vào nhanh, không cần tay vẽ."""
    if FX.get('pop') and len(parts) == 1 and isinstance(parts[0], CharItem):
        parts[0].pop = True
        parts[0].nohand = True
        parts[0].dur = 0.42
        parts[0].sfx = 'bup'
    return parts


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


def _acc_words(t):
    import unicodedata
    t = unicodedata.normalize('NFC', t or '').lower()
    return ' ' + re.sub(r'[^\w%+]+', ' ', t).replace('_', ' ') + ' '


def pick_icon(screen, say, avoid=(), with_score=False):
    a, b = _words(screen), _words(say)
    a2, b2 = _acc_words(screen), _acc_words(say)
    best, best_score = None, 0
    allkeys = dict(ICON_KEYWORDS)
    allkeys.update(_hv.keywords())
    allkeys.update(kho_keywords())
    for icon, keys in allkeys.items():
        sc = 0
        for k in keys:
            if k.startswith('~'):
                k = k[1:]; ta, tb = a2, b2
            else:
                ta, tb = a, b
            kk = ' %s ' % k.strip()
            wk = 1 + len(k) / 8.0 + (1.2 if kho_has(icon) else 0.6 if _hv.has(icon) else 0)
            if kk in ta:
                sc += 2 * wk
            if kk in tb:
                sc += wk
        if icon in avoid:
            sc *= 0.25
        if sc > best_score:
            best, best_score = icon, sc
    if with_score:
        return best, best_score
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
    parts = [x.strip() for x in re.findall(r'(?:\d[.,:]\d|[^,.;:!?…])+[,.;:!?…]*', s)] or [s]
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


COUNT_RE = re.compile(r'^\s*\d{1,2}\s*/\s*\d{1,2}\s*$')
PLACEHOLDER_RE = re.compile(r'^(so lieu|can kiem tra|chua kiem chung|dien|\.\.\.|x+|\?+)\b')
KEEP_TAGS = ('tiep', 'giu bang', 'giu', 'tiep bang', 'noi tiep')
FLOW_RE = re.compile(r'\s*(?:→|->|=>|⇒)\s*')


def flow_say(steps):
    if len(steps) == 1:
        return steps[0]
    out = []
    for i, s_ in enumerate(steps):
        lead = 'Đầu tiên' if i == 0 else ('Cuối cùng' if i == len(steps) - 1 else 'Tiếp theo')
        out.append('%s, %s.' % (lead, s_[:1].lower() + s_[1:] if not s_[:2].isupper() else s_))
    return ' '.join(out)


AUTO_LIST_RE = re.compile(r'^\s*([^:]*[^\W\d_][^:]{0,40}?)\s*:\s+(.+?)\s*[.!]?\s*$')


def auto_list(show):
    """'Lead: a, b và c' (2–5 mục ngắn) -> (lead, [A, B, C]); không khớp thì None."""
    m = AUTO_LIST_RE.match(show)
    if not m or ' / ' in show:
        return None
    parts = [x.strip(' .') for x in re.split(r'\s*,\s*|\s+(?:và|hoặc|với)\s+', m.group(2)) if x.strip(' .')]
    if not 2 <= len(parts) <= 5 or len(m.group(1).split()) > 6 or any(
            len(x.split()) > 4 or len(x) > 22 or re.search(r'\d', x) for x in parts):
        return None
    return m.group(1).strip(), [x[:1].upper() + x[1:] for x in parts]


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
        bad = [t for t in tags if PLACEHOLDER_RE.match(t)]
        if bad:
            raise VideoError('Kịch bản còn chỗ chưa điền: [%s] ở dòng "%s". Hãy thay bằng thông tin đã kiểm chứng '
                             'hoặc xoá câu đó.' % (TAG.findall(line)[tags.index(bad[0])], line[:60]))
        noicon = any(t in ('khong hinh', 've: khong', 've:khong', 've: -') for t in tags)
        body = TAG.sub('', line).strip()
        icon_tags = [t for t in tags if t.startswith('ve:') or t.startswith('ve :')]
        tags = [t for t in tags if t not in icon_tags]
        icon_tags = [t for t in icon_tags if icon_known(t.split(':', 1)[1].strip())]
        if body[:2] in ('- ', '+ ') and scenes:
            item = body[2:].strip().rstrip('.,;')
            scenes[-1]['lines'].append(('- ' + item, tags + icon_tags))
            if not scenes[-1].get('own_say'):      # dòng dẫn đã có '|| lời đọc' thì không đọc lặp lại từng mục
                scenes[-1]['say'].append(item + ',')
            scenes[-1]['src'].append(line)
            continue
        if not body and tags:
            if scenes:
                scenes[-1]['lines'].append(('', tags))
                scenes[-1]['src'].append(line)
            continue
        keep = any(t in KEEP_TAGS for t in tags)  # [tiếp]: cảnh trước thu nhỏ lên trên, vẽ tiếp bên dưới
        tags = [t for t in tags if t not in KEEP_TAGS]
        count = next((t.replace(' ', '') for t in tags if COUNT_RE.match(t)), None)   # [1/3]: huy hiệu tiến độ
        tags = [t for t in tags if not COUNT_RE.match(t)]
        show_part = body.split('||', 1)[0]
        auto = auto_list(show_part)
        if auto and not FLOW_RE.search(show_part):   # 'Hồ sơ gồm: hộ chiếu, học bạ, ảnh thẻ' -> danh sách có hình
            lead, items = auto
            say = body.split('||', 1)[1].strip() if '||' in body else (lead + ' ' + ', '.join(i[:1].lower() + i[1:] for i in items[:-1]) + ' và ' + items[-1][:1].lower() + items[-1][1:] + '.')
            sc = {'title': '', 'lines': [('', [t]) for t in icon_tags] + [(lead + ':', tags)], 'say': [say], 'src': [line],
                  'noicon': noicon, 'keep': keep, 'own_say': True, 'count': count}
            for it in items:
                sc['lines'].append(('- ' + it, []))
            scenes.append(sc)
            continue
        if FLOW_RE.search(show_part):             # sơ đồ: A → B → C
            steps = [x.strip() for x in FLOW_RE.split(show_part) if x.strip()]
            say = body.split('||', 1)[1].strip() if '||' in body else flow_say(steps)
            sc = {'title': '', 'lines': [('\u00bb' + '\t'.join(steps), tags)], 'say': [say], 'src': [line],
                  'noicon': True, 'flow': True, 'keep': keep, 'count': count}
            scenes.append(sc)
            continue
        if '||' in body:
            show, say = [x.strip() for x in body.split('||', 1)]
            shown = [x.strip() for x in re.split(r'\s+/\s+', show) if x.strip()]
        else:
            say = body
            shown = split_display(body)
        sc = {'title': '', 'lines': [('', [t]) for t in icon_tags], 'say': [say], 'src': [line], 'noicon': noicon,
              'keep': keep, 'own_say': '||' in body, 'count': count}
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
        if re.match(r'^(caption|hashtag|nguon|kich ban)\s*[:：]', low) and '||' not in line:
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



MISSING = []          # câu trên màn hình không tìm được hình trong Kho (để báo 'hình còn thiếu')

def auto_style(scenes):
    """Tự trang trí những dòng chưa có thẻ: tô màu từ khóa, gạch chân ý chính, khung, hình vẽ."""
    MISSING.clear()
    n = len(scenes)
    last_icon = None
    for si, sc in enumerate(scenes):
        sc['auto'] = True
        lines = sc['lines']
        if sc.get('flow'):
            if si == n - 1 and n > 1 and not any('logo' in t for _, t in lines):
                lines.append(('', ['logo']))
            continue
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
        n_bul = sum(1 for txt, _ in lines if txt[:2] in ('- ', '+ '))
        if sc.get('flow'):
            pass
        elif not has_icon and not sc.get('noicon') and n_bul < 2 and len(text_idx) <= 4 and not (si == n - 1 and n > 1) \
                and not scene_kind(dict(sc, lines=lines)):
            screen = ' '.join(t for t, _ in lines)
            icon = pick_icon(screen, ' '.join(sc['say']), avoid=(last_icon,) if last_icon else ())
            if (not icon or not kho_has(icon)) and len(screen) > 3:
                MISSING.append(screen)
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
def _bullet_icons(group, scene):
    """Hình cho từng gạch đầu dòng: [vẽ: x] trên dòng đó, hoặc máy tự chọn theo chữ (đủ chắc mới lấy)."""
    names, used = [], set()
    for t, tg in group:
        name = tag_icon(tg)
        if name and icon_known(name):
            names.append(name); used.add(name); continue
        name = None
        if scene.get('auto') and not scene.get('noicon'):
            cand, sc_ = pick_icon(t, t, avoid=tuple(used), with_score=True)
            if cand and sc_ >= 2.4 and cand not in used:
                name = cand
            if (not name or not kho_has(name)) and len(t.strip('-+ ')) > 3:
                MISSING.append(t.strip('-+ '))
        names.append(name)
        if name:
            used.add(name)
    return names


def bullet_block(group, scene, scale, base):
    names = _bullet_icons(group, scene)
    n = len(group)
    got = sum(1 for x in names if x)
    short = all(len(t) <= 26 for t, _ in group)
    if 2 <= n <= 4 and got == n and short and not LAY.get('wide') and LAY['H'] > LAY['W']:
        # khung dọc: mỗi ý một hàng, hình lớn bên trái, chữ bên phải
        ih = min(330 * scale, (BOTTOM_AREA - TOP_AREA) * 0.9 / n)
        lsize = min(fit(t, base * 0.8, LMAXW * 0.5) for t, _ in group)
        return {'k': 'irows', 'items': group, 'names': names, 'ih': ih, 'size': lsize,
                'h': n * ih + (n - 1) * 22 * scale, 'gapr': 22 * scale}
    if 2 <= n <= 4 and got == n and short:
        # thẻ hình: mỗi ý một hình lớn, chữ ở dưới
        per_row = n if (n <= 3 or LAY.get('wide')) else 2
        rows = math.ceil(n / per_row)
        colw = LMAXW / per_row
        ih = min(colw * 0.9, (400 if rows == 1 else 290) * scale * (1.2 if LAY.get('wide') else 1))
        lsize = min(fit(t, base * 0.62, colw - 24) for t, _ in group)
        lh = line_h(lsize) * 0.9
        return {'k': 'cards', 'items': group, 'names': names, 'per_row': per_row, 'ih': ih, 'size': lsize,
                'rowh': ih + lh + 18, 'h': rows * (ih + lh + 18) + (rows - 1) * 16}
    if got < n:                     # thiếu hình cho vài ý -> dùng dấu tích cho tất cả, nhìn đồng đều
        names, got = [None] * n, 0
    size = int(min(fit(t, base * 0.95, LMAXW - (190 if got else 110)) for t, _ in group))
    return {'k': 'bullets', 'items': group, 'names': names, 'size': size,
            'h': n * (max(line_h(size) * 0.92, (line_h(size) * 1.15) if got else 0) + 14)}


def flow_block(steps, scale):
    n = len(steps)
    if LAY.get('wide') and n <= 4 and all(len(s_) <= 12 for s_ in steps):
        colw = LMAXW / n
        size = min(fit(s_, 96 * scale, colw - 130) for s_ in steps)
        bh = line_h(size) * 0.9 + 70
        return {'k': 'flow', 'steps': steps, 'dir': 'h', 'size': size, 'bh': bh, 'colw': colw, 'h': bh + 20}
    size = min(fit(s_, 100 * scale, LMAXW - 190) for s_ in steps)
    bh = line_h(size) * 0.9 + 54
    gap = 92 * scale
    return {'k': 'flow', 'steps': steps, 'dir': 'v', 'size': size, 'bh': bh, 'gapv': gap,
            'h': n * bh + (n - 1) * gap}


def arrow_path(x0, y0, x1, y1, seed=0, head=26):
    ang = math.atan2(y1 - y0, x1 - x0)
    a1 = (x1 - head * math.cos(ang - 0.5), y1 - head * math.sin(ang - 0.5))
    a2 = (x1 - head * math.cos(ang + 0.5), y1 - head * math.sin(ang + 0.5))
    return seg((x0, y0), (x1, y1), bow=5, seed=seed) + [a1, (x1, y1), a2]


VS_RE = re.compile(r'^\s*(.{1,28}?)\s+(?:vs\.?|VS\.?|Vs\.?)\s+(.{1,28}?)\s*$')
BIG_RE = re.compile(r'^[~≈>+<-]?\s*\d[\d.,]*\s*(?:%|\+|k|K)?\s*[^\d\s/]{0,7}(?:\s?[^\d\s/]{1,6})?(?:\s*/\s*[^\s/]{1,6})?$')


def is_two_col(txt):
    return txt.count('|') == 1 and '||' not in txt and all(c.strip() for c in txt.split('|'))


def is_big_number(txt, tags=()):
    plain = txt.replace('*', '').strip()
    if any(norm(t) in ('so lon', 'so') for t in tags):
        return bool(plain)
    return len(plain) <= 14 and bool(re.search(r'\d', plain)) and bool(BIG_RE.match(plain)) and '|' not in plain


def scene_kind(scene):
    """'vs' (so sánh 2 cột), 'big' (số liệu lớn) hoặc ''."""
    texts = [(t, tg) for t, tg in scene['lines'] if t and not tag_icon(tg) and 'logo' not in tg]
    if not texts:
        return ''
    if any(VS_RE.match(t.replace('*', '')) for t, _ in texts) or sum(1 for t, _ in texts if is_two_col(t)) >= 2:
        return 'vs'
    t0, tg0 = texts[0]
    if len(texts) <= 3 and not any(t[:2] in ('- ', '+ ') or t.startswith('\u00bb') for t, _ in texts) \
            and is_big_number(t0, tg0):
        return 'big'
    return ''


def vs_block(lines, scale):
    """Bảng so sánh 2 cột: tiêu đề 'A vs B' (tuỳ chọn) + các dòng 'Tiêu chí: trái | phải'."""
    head, rows, rest = None, [], []
    for t, tg in lines:
        p_ = t.replace('*', '').strip()
        m = VS_RE.match(p_)
        if m and head is None and not rows:
            head = (m.group(1).strip(), m.group(2).strip())
        elif is_two_col(p_):
            a, b = [x.strip() for x in p_.split('|')]
            lab = ''
            if ':' in a and len(a.split(':', 1)[0]) <= 22:
                lab, a = [x.strip() for x in a.split(':', 1)]
            rows.append((lab, a, b))
        else:
            rest.append((t, tg))
    colw = LMAXW / 2
    hs = min([fit(x, 96 * scale, colw * 0.64) for x in head] if head else [96 * scale])
    rs = min([fit(x, 92 * scale, colw * 0.86) for _, a, b in rows for x in (a, b)] or [92 * scale])
    ls = min([fit(l_, 58 * scale, LMAXW * 0.9) for l_, _, _ in rows if l_] or [58 * scale])
    hh = (line_h(hs) * 0.9 + 70) if head else 0
    rh = [(line_h(ls) * 0.85 if l_ else 0) + line_h(rs) * 0.9 + 30 * scale for l_, _, _ in rows]
    return {'k': 'vs', 'head': head, 'rows': rows, 'hs': hs, 'rs': rs, 'ls': ls, 'hh': hh, 'rh': rh,
            'h': hh + sum(rh) + 20}, rest


def build_blocks(scene, scale):
    base = 118 * scale
    blocks, lines, i = [], scene['lines'], 0
    kind = '' if scene.get('_novs') else scene_kind(scene)
    if kind == 'vs':
        vb, rest = vs_block(lines, scale)
        other = build_blocks(dict(scene, lines=rest, _novs=True), scale) if rest else []
        first_txt = next((t for t, tg in lines if t and not tag_icon(tg)), '')
        lead = [b for b in other if b['k'] == 'text' and b['text'].strip() and b['text'] in first_txt]
        return lead + [vb] + [b for b in other if b not in lead]
    big_done = False
    while i < len(lines):
        txt, tags = lines[i]
        if kind == 'big' and not big_done and txt and not tag_icon(tags):
            big_done = True
            plain = txt.replace('*', '').strip()
            size = fit(plain, base * 2.7, LMAXW * 0.92)
            blocks.append({'k': 'big', 'text': plain, 'size': size, 'color': tag_color(tags, None) or RED,
                           'h': line_h(size) * 0.92 + 40 * scale})
            i += 1
            continue
        if txt.startswith('\u00bb'):                              # sơ đồ quy trình
            steps = txt[1:].split('\t')
            blocks.append(flow_block(steps, scale))
            i += 1
            continue
        if txt[:2] in ('- ', '+ '):
            group = []
            while i < len(lines) and lines[i][0][:2] in ('- ', '+ '):
                group.append((lines[i][0][2:].strip().replace('*', ''), lines[i][1]))
                i += 1
            blocks.append(bullet_block(group, scene, scale, base))
            continue
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
            raw_parts = txt.split('*')
            marks = [i for i, p_ in enumerate(txt.split('*')) if i % 2 == 1 and p_.strip()] if txt.count('*') >= 2 else []
            segs = make_segs(txt, color, scene.get('auto'))
            txt = ''.join(t for t, _ in segs)
            size = fit(txt, size, LMAXW - (90 if extra else 0))
            blocks.append({'k': 'text', 'text': txt, 'segs': segs, 'size': size, 'color': color, 'tags': tags,
                           'marks': [p_ for i, p_ in enumerate(raw_parts) if i in marks] if marks else [],
                           'h': line_h(size) * 0.9 + extra + (24 if 'gach' in tags else 0)})
        i += 1
    return blocks


def layout_scene(scene, idx, has_logo_end):
    global LCX, LMAXW
    # Khung ngang, không có nhân vật: hình bên trái, chữ bên phải
    if LAY.get('wide') and not has_logo_end and abs(LCX - LAY['col_full'][0]) < 1:
        icons = [(t, tg) for t, tg in scene['lines'] if tag_icon(tg) and icon_known(tag_icon(tg))]
        texts = [(t, tg) for t, tg in scene['lines'] if not tag_icon(tg)]
        if icons and any(t for t, _ in texts):
            save = (LCX, LMAXW)
            LCX, LMAXW = W * 0.735, W * 0.44
            try:
                items = layout_scene(dict(scene, lines=texts), idx, has_logo_end)
            finally:
                LCX, LMAXW = save
            name = tag_icon(icons[0][1])
            h = min(BOTTOM_AREA - TOP_AREA, 600)
            parts = icon_paths(name, W * 0.27, (TOP_AREA + BOTTOM_AREA) / 2, h * (0.95 if big_icon(name) else 0.88),
                               tag_color(icons[0][1]), idx * 100)
            budget = (3.0 if kho_has(name) else 2.6) if big_icon(name) else 2.0
            tot = sum(it.dur for it in parts) or 1
            for it in parts:
                it.gap = 0.015 if len(parts) > 6 else 0.08
                if tot > budget:
                    it.dur = max(0.04, it.dur * budget / tot)
            return parts + items
    top = LAY['end_top'] if has_logo_end else TOP_AREA
    bottom = BOTTOM_AREA
    scale = 1.0
    while True:
        blocks = build_blocks(scene, scale)
        if has_logo_end and any(b['k'] != 'icon' for b in blocks):   # cảnh cuối có logo to: bỏ hình để chữ đủ to
            blocks = [b for b in blocks if b['k'] != 'icon']
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
            budget = (3.0 if kho_has(b['name']) else 2.6) if big_icon(b['name']) else 2.0
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
            if b.get('marks'):                                   # *chữ*: bút dạ tô đúng lúc đọc tới
                fnt, done = font(sz), ''
                for part, _c in b['segs']:
                    if part in b['marks']:
                        x0m = t.left + fnt.getlength(done)
                        mk = Marker(x0m, x0m + fnt.getlength(part), cy, sz, seed=seed + len(done))
                        mk.sync = part
                        items.append(mk)
                    done += part
            if 'khung' in tg:
                x0, x1 = t.left - 34, t.right + 34
                y0, y1 = cy - sz * 0.6, cy + sz * 0.6
                items += rough_box(x0, y0, x1, y1, b['color'] if b['color'] != INK else BLUE, seed=seed, width=8)
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
            rh = h / len(b['items'])
            has_ic = any(b['names'])
            ind = 170 if has_ic else 100
            maxw = max(font(sz).getlength(t) for t, _ in b['items'])
            x0 = LCX - (ind + maxw) / 2
            for j, ((t, tg), name) in enumerate(zip(b['items'], b['names'])):
                cy = y + rh * j + rh / 2
                c = tag_color(tg, None)
                mark = c or bullet_colors[j % len(bullet_colors)]
                first = len(items)
                if name:
                    ih = min(rh * 0.95, 150)
                    parts = icon_paths(name, x0 + 64, cy, ih, mark, seed + j)
                    _squeeze(parts, 0.9)
                    items += make_pop(parts)
                else:
                    items.append(Path(poly([(x0, cy + 2), (x0 + 28, cy + 30), (x0 + 72, cy - 32)], seed=seed + j, bow=3),
                                      mark, 12))
                    items[-1].sfx = 'tick'
                items.append(Txt(t, sz, c or INK, cy, left=x0 + ind))
                items[first].sync = t
        elif b['k'] == 'cards':
            pr, ih, sz = b['per_row'], b['ih'], b['size']
            colw = LMAXW / pr
            for j, ((t, tg), name) in enumerate(zip(b['items'], b['names'])):
                r_, c_ = divmod(j, pr)
                n_in_row = min(pr, len(b['items']) - r_ * pr)
                x = LCX + (c_ - (n_in_row - 1) / 2) * colw
                top_ = y + r_ * (b['rowh'] + 16)
                col = tag_color(tg, None) or bullet_colors[j % len(bullet_colors)]
                first = len(items)
                save_w = LMAXW
                LMAXW = colw * 0.96 / 0.95          # hình trong Kho không lấn sang ô bên cạnh
                try:
                    parts = icon_paths(name, x, top_ + ih / 2, ih * (0.98 if big_icon(name) else 0.9), col, seed + j * 3)
                finally:
                    LMAXW = save_w
                _squeeze(parts, 1.5)
                items += make_pop(parts)
                items.append(Txt(t, sz, col, top_ + ih + 10 + line_h(sz) * 0.45, cx=x))
                items[first].sync = t
        elif b['k'] == 'irows':
            ih, sz = b['ih'], b['size']
            for j, ((t, tg), name) in enumerate(zip(b['items'], b['names'])):
                cy = y + j * (ih + b['gapr']) + ih / 2
                col = tag_color(tg, None) or bullet_colors[j % len(bullet_colors)]
                first = len(items)
                save_w = LMAXW
                LMAXW = save_w * 0.46 / 0.95
                try:
                    parts = icon_paths(name, LCX - save_w * 0.25, cy,
                                       ih * (0.98 if kho_has(name) else 1.3 if _hv.has(name) else 0.9), col, seed + j * 3)
                finally:
                    LMAXW = save_w
                _squeeze(parts, 1.4)
                items += make_pop(parts)
                items.append(Txt(t, sz, col, cy, left=LCX + LMAXW * 0.02))
                items[first].sync = t
        elif b['k'] == 'big':                                    # số liệu lớn: con số to + nét vẽ nhấn
            sz = b['size']
            cy = y + line_h(sz) * 0.46
            t = Txt(b['text'], sz, b['color'], cy, cx=LCX)
            t.emph, t.sfx = 'phinh', 'ting'
            items.append(t)
            items.append(Path(wavy(t.left + 20, t.right - 20, cy + sz * 0.5, amp=10), ORANGE, 12))
            for j, ang in enumerate((-2.5, -1.95, -1.4)):          # 3 tia sáng góc trên phải
                r0, r1 = sz * 0.25, sz * 0.48
                ox, oy = t.right - 6, cy - sz * 0.32
                items.append(Path(poly([(ox + r0 * math.cos(ang + 1.6), oy + r0 * math.sin(ang + 1.6)),
                                        (ox + r1 * math.cos(ang + 1.6), oy + r1 * math.sin(ang + 1.6))],
                                       seed=seed + j, bow=2), ORANGE, 9))
        elif b['k'] == 'vs':                                     # so sánh 2 cột
            colw = LMAXW / 2
            xl, xr = LCX - colw / 2, LCX + colw / 2
            yy = y
            if b['head']:
                hs = b['hs']
                cy = yy + b['hh'] / 2 - 10
                for j, (txt_, col) in enumerate(zip(b['head'], (BLUE, RED))):
                    cx = xl if j == 0 else xr
                    t = Txt(txt_, hs, col, cy, cx=cx)
                    first = len(items)
                    half = min(colw * 0.36, font(hs).getlength(txt_) / 2 + 30)
                    items += rough_box(cx - half, cy - line_h(hs) * 0.5, cx + half, cy + line_h(hs) * 0.5,
                                       col, seed=seed + j * 5)
                    items.append(t)
                    items[first].sync = txt_
                vs = Txt('VS', int(hs * 0.62), ORANGE, cy, cx=LCX)
                items.append(Path(ellipse(LCX, cy + 3, hs * 0.5, hs * 0.42, seed=seed + 3), ORANGE, 8))
                items.append(vs)
                yy += b['hh']
            top_line = yy
            for j, ((lab, a, b_), rh) in enumerate(zip(b['rows'], b['rh'])):
                ry = yy
                if lab:
                    lt = Txt(lab, b['ls'], GREY, ry + line_h(b['ls']) * 0.42, cx=LCX)
                    items.append(lt)
                    lt.sync = lab
                    ry += line_h(b['ls']) * 0.85
                cy = ry + line_h(b['rs']) * 0.45
                ta = Txt(a, b['rs'], INK, cy, cx=xl)
                tb = Txt(b_, b['rs'], INK, cy, cx=xr)
                if not lab:
                    ta.sync = a
                items += [ta, tb]
                hv = line_h(b['rs']) * 0.42                      # vạch chia ngắn giữa 2 giá trị
                items.append(Path(poly([(LCX, cy - hv), (LCX + 2, cy + hv)], seed=seed + j + 20, bow=3), (190, 190, 185), 5))
                yy += rh
                if j < len(b['rows']) - 1:                       # gạch ngang mảnh giữa các dòng
                    items.append(Path(poly([(LCX - LMAXW * 0.46, yy - 14 * scale), (LCX + LMAXW * 0.46, yy - 12 * scale)],
                                           seed=seed + j, bow=3), (205, 205, 200), 4))
        elif b['k'] == 'flow':
            st, sz, bh = b['steps'], b['size'], b['bh']
            n = len(st)
            for j, t in enumerate(st):
                col = bullet_colors[j % len(bullet_colors)]
                if b['dir'] == 'h':
                    cx = LCX + (j - (n - 1) / 2) * b['colw']
                    cy = y + bh / 2
                    bw = b['colw'] - 70
                else:
                    cx = LCX
                    cy = y + j * (bh + b['gapv']) + bh / 2
                    bw = min(LMAXW - 20, max(font(sz).getlength(s_) for s_ in st) + 190)
                first = len(items)
                if j > 0:                                        # mũi tên cong vẽ tay từ ô trước
                    if b['dir'] == 'h':
                        px = LCX + (j - 1 - (n - 1) / 2) * b['colw']
                        items += curved_arrow(px + (b['colw'] - 70) / 2 + 10, cy - 6, cx - bw / 2 - 14, cy - 4,
                                              GREY, seed + j, bend=0.28)
                    else:
                        items += curved_arrow(cx - 40, cy - bh / 2 - b['gapv'] + 12, cx - 34, cy - bh / 2 - 10,
                                              GREY, seed + j, bend=0.32)
                x0_, x1_ = cx - bw / 2, cx + bw / 2
                y0_, y1_ = cy - bh / 2, cy + bh / 2
                items += rough_box(x0_, y0_, x1_, y1_, col, seed=seed + j * 5)
                num = Txt(str(j + 1), int(sz * 0.8), col, cy, cx=x0_ + 48)
                items.append(num)
                items.append(Txt(t, sz, INK, cy, cx=cx + 30))
                items[first].sync = t
        y += h + gap
        seed += 7
    return items


def _squeeze(parts, budget):
    tot = sum(it.dur for it in parts) or 1
    for it in parts:
        it.gap = 0.01 if len(parts) > 6 else 0.05
        if tot > budget:
            it.dur = max(0.03, it.dur * budget / tot)


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


PHAT_AM_FILE = os.path.join(HERE, 'phat_am.json')
_pa = {'mtime': None, 'rx': None, 'map': {}}


def phat_am():
    """Từ điển phát âm do admin duyệt: {'TOPIK': 'tô pích', ...} (chỉ đổi lời đọc, chữ trên màn hình giữ nguyên)."""
    try:
        mt = os.path.getmtime(PHAT_AM_FILE)
    except OSError:
        return None, {}
    if _pa['mtime'] != mt:
        try:
            with open(PHAT_AM_FILE, encoding='utf-8') as fh:
                d = json.load(fh)
            mp = {str(k).strip().lower(): str(v).strip() for k, v in d.items() if str(k).strip() and str(v).strip()}
        except Exception:
            mp = {}
        keys = sorted(mp, key=len, reverse=True)
        rx = re.compile(r'(?<![\w])(' + '|'.join(re.escape(k) for k in keys) + r')(?![\w])', re.I) if keys else None
        _pa.update(mtime=mt, rx=rx, map=mp)
    return _pa['rx'], _pa['map']


def apply_phat_am(text):
    rx, mp = phat_am()
    if not rx or not text:
        return text
    return rx.sub(lambda m: mp.get(m.group(1).lower(), m.group(1)), text)


def clean_say(text):
    text = apply_phat_am(text)
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


# ------------------------------------------------------------------ tiếng bút / tiếng lau bảng
def _smooth(x, k):
    return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode='same')


def _norm_noise(x):
    sd = float(x.std()) or 1.0
    return (x / sd).astype(np.float32)


def sfx_track(plans, rate=44100, pen_vol=0.05, seed=7):
    """Tiếng sột soạt nhỏ khi tay đang vẽ + tiếng lau bảng khi chuyển cảnh (mảng float, đơn vị = biên độ 16-bit)."""
    rng = np.random.default_rng(seed)
    lens = [int(round(pl['n'] / FPS * rate)) for pl in plans]
    out = np.zeros(sum(lens), dtype=np.float32)
    amp = pen_vol * 32767
    off = 0
    for pl, ln in zip(plans, lens):
        for it, s0, e0 in pl['sch']:
            soft = 0.55 if isinstance(it, (Fill, CharItem)) else 1.0
            t = s0
            while t < e0 - 0.03:
                L = min(rng.uniform(0.06, 0.18), e0 - t)
                n = int(L * rate)
                if n < 64:
                    break
                x = rng.standard_normal(n + 64).astype(np.float32)
                mid = _smooth(x, 6) - _smooth(x, 40)       # thân tiếng bút (trầm, êm, không rít)
                nz = _norm_noise(mid)[32:32 + n]
                env = np.sin(np.linspace(0, np.pi, n)) ** 1.5         # vào/ra mềm
                env *= 0.75 + 0.25 * np.sin(np.linspace(0, rng.uniform(6, 14) * np.pi, n))
                a = off + int(t * rate)
                b = min(a + n, off + ln)
                if b > a:
                    out[a:b] += nz[:b - a] * env[:b - a] * amp * rng.uniform(0.55, 1.0) * soft
                t += L + rng.uniform(0.02, 0.07)
        if not pl['last'] and not pl.get('keep_next') and TRANS_SND != 'tat' and pl.get('trans') != 'bay':   # tiếng lau bảng
            n = int(pl.get('tr', ERASE) * rate)
            x = rng.standard_normal(n + 400).astype(np.float32)
            rub = _norm_noise(_smooth(x, 9) - _smooth(x, 60))[200:200 + n]
            k = np.linspace(0, 1, n)
            env = np.abs(np.sin(np.pi * 4 * k)) ** 0.5 * np.minimum(1, (1 - k) * 8)
            a = off + ln - n
            out[a:a + n] += rub * env * amp * (0.3 if TRANS_SND == 'vut' else 0.15)
        off += ln
    return _soften(out, rate)


def _soften(x, rate):
    """Lọc bỏ tần số chói (>2.2 kHz) và tiếng ù (<200 Hz) để tiếng bút/lau bảng êm tai."""
    try:
        from scipy.signal import butter, sosfilt
        sos = butter(4, [200, 2200], btype='band', fs=rate, output='sos')
        return sosfilt(sos, x).astype(np.float32) * 1.6
    except Exception:
        return _smooth(x, 5)


def _fx_sound(kind, rate):
    """Âm thanh hiệu ứng tự tổng hợp (không cần file, không lo bản quyền)."""
    rng = np.random.default_rng(len(kind))
    if kind == 'vut':                                     # vút: tiếng gió lướt qua khi chuyển cảnh
        n = int(0.42 * rate)
        x = rng.standard_normal(n + 64).astype(np.float32)
        k = np.linspace(0, 1, n)
        lo = _smooth(x, 18)[32:32 + n]
        hi = (x - _smooth(x, 3))[32:32 + n]
        nz = lo * (1 - k) + hi * 0.35 * k
        env = np.sin(np.pi * k) ** 1.6
        return _norm_noise(nz) * env * 0.55
    if kind == 'giay':                                    # lật giấy: tiếng sột nhẹ, trầm, không rít
        n = int(0.32 * rate)
        x = rng.standard_normal(n + 64).astype(np.float32)
        k = np.linspace(0, 1, n)
        nz = (_smooth(x, 30) - _smooth(x, 120))[32:32 + n]
        env = (k / 0.25).clip(0, 1) ** 2 * np.exp(-np.clip(k - 0.25, 0, None) * 9)
        return _norm_noise(nz) * env * 0.22
    t = np.arange(int(rate * {'ting': 0.55, 'bup': 0.12, 'tick': 0.07, 'bum': 0.5, 'chuong': 1.4}.get(kind, 0.3))) / rate
    if kind == 'ting':                                    # ting: chuông nhỏ trong trẻo
        y = np.sin(2 * np.pi * 1760 * t) + 0.45 * np.sin(2 * np.pi * 2640 * t) + 0.2 * np.sin(2 * np.pi * 3520 * t)
        return (y * np.exp(-t * 7.5) * np.minimum(1, t * 400)).astype(np.float32) * 0.42
    if kind == 'bup':                                     # bụp: bong bóng bật nhẹ
        f0 = 620 * np.exp(-t * 22) + 180
        y = np.sin(2 * np.pi * np.cumsum(f0) / rate)
        return (y * np.exp(-t * 30) * np.minimum(1, t * 900)).astype(np.float32) * 0.6
    if kind == 'tick':                                    # tích: gõ nhẹ khi hiện dấu tích
        y = np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 70)
        return (y * np.minimum(1, t * 1500)).astype(np.float32) * 0.35
    if kind == 'bum':                                     # bùm: nhịp trầm mở đầu
        f0 = 110 * np.exp(-t * 6) + 45
        y = np.sin(2 * np.pi * np.cumsum(f0) / rate) + 0.15 * rng.standard_normal(len(t)) * np.exp(-t * 60)
        return (y * np.exp(-t * 7) * np.minimum(1, t * 600)).astype(np.float32) * 0.85
    if kind == 'chuong':                                  # chuông kết: hai nốt ngân
        y = np.sin(2 * np.pi * 1046.5 * t) * np.exp(-t * 3.2)
        t2 = np.clip(t - 0.18, 0, None)
        y += np.where(t > 0.18, np.sin(2 * np.pi * 1318.5 * t2) * np.exp(-t2 * 3.0), 0)
        return (y * np.minimum(1, t * 300)).astype(np.float32) * 0.32
    return np.zeros(1, np.float32)


def fx_events(plans):
    """[(giây tính từ đầu video, loại âm)] lấy từ lịch vẽ của từng cảnh."""
    ev, off = [], 0.0
    for i, pl in enumerate(plans):
        if i == 0 and FX.get('punch'):
            ev.append((0.0, 'bum'))
        for it, s0, e0 in pl['sch']:
            k = getattr(it, 'sfx', None)
            if k:
                ev.append((off + max(0.0, s0), k))
        if pl.get('logo_end'):
            ev.append((off + 0.15, 'chuong'))
        if not pl['last'] and not pl.get('keep_next') and TRANS_SND in ('vut', 'giay'):
            if pl.get('_tt') != 'glide':
                ev.append((off + pl['dur'] - pl.get('tr', ERASE) + 0.02, TRANS_SND))
        off += pl['n'] / FPS
    return ev


def fx_track(plans, rate=44100, vol=1.0):
    total = int(sum(pl['n'] for pl in plans) / FPS * rate) + rate
    out = np.zeros(total, np.float32)
    cache, last = {}, {}
    for at, kind in sorted(fx_events(plans)):
        if kind in ('tick', 'bup') and at - last.get(kind, -9) < 0.12:   # tránh dồn dập
            continue
        last[kind] = at
        snd = cache.get(kind)
        if snd is None:
            snd = cache[kind] = _fx_sound(kind, rate)
        a = int(at * rate)
        b = min(total, a + len(snd))
        if b > a:
            out[a:b] += snd[:b - a]
    return out * 32767 * 0.16 * vol


def mix_into_wav(path, track, duck_amt=0.6):
    with wave.open(path) as w:
        ch, sw, fr, nf = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        data = np.frombuffer(w.readframes(nf), dtype=np.int16).astype(np.float32).reshape(-1, ch)
    m = min(len(data), len(track))
    # nhường giọng đọc: khi đang có lời, tiếng bút nhỏ lại còn ~40%
    voice = np.abs(data[:m].mean(1))
    k = max(1, int(fr * 0.08))
    env = np.convolve(voice, np.ones(k, dtype=np.float32) / k, mode='same')
    duck = 1.0 - duck_amt * np.clip(env / 1500.0, 0, 1)
    data[:m] += (track[:m] * duck)[:, None]
    with wave.open(path, 'wb') as w:
        w.setnchannels(ch); w.setsampwidth(sw); w.setframerate(fr)
        w.writeframes(np.clip(data, -32768, 32767).astype(np.int16).tobytes())


class Snap:
    """Cảnh trước thu nhỏ lại, giữ trên bảng làm cầu nối (không cần tay vẽ)."""
    nohand = True

    def __init__(self, img, src_box, dst_box):
        self.img, self.src, self.dst = img, src_box, dst_box
        self.dur, self.gap = 0.7, 0.05

    def draw(self, f, r):
        k = eio(clamp(r))
        bx = [a + (b - a) * k for a, b in zip(self.src, self.dst)]
        w, h = max(2, int(bx[2] - bx[0])), max(2, int(bx[3] - bx[1]))
        im = self.img.resize((w, h), Image.LANCZOS)
        f.paste(im, (int(bx[0]), int(bx[1])), im)

    def pos(self, r, t):
        return None


def _sync_frac(say_n, key):
    """Vị trí (0..1) của cụm chữ key trong lời đọc đã chuẩn hoá."""
    words = norm(key).split()
    if not say_n or not words:
        return None
    for nw in (4, 3, 2, 1):
        k = ' '.join(words[:nw])
        if len(k) < 3:
            continue
        i = say_n.find(k)
        if i >= 0:
            return i / max(1, len(say_n))
    return None


# ------------------------------------------------------------------ dựng
def warp_r(it, r):
    """Nhịp tay tự nhiên: khi cảnh dư thời gian, bút dừng một nhịp ngắn giữa chừng (tiến độ đứng yên)."""
    pz = getattr(it, '_pz', None)
    if not pz or r <= 0 or r >= 1:
        return r
    ratio, n = pz
    q = ratio / n                          # thời lượng mỗi lần dừng (theo tỉ lệ)
    seg = (1 - ratio) / (n + 1)            # thời lượng mỗi đoạn vẽ
    u, done = r, 0.0
    for j in range(n + 1):
        if u <= seg:
            return (j + u / seg) / (n + 1)
        u -= seg
        if j < n:
            if u <= q:
                return (j + 1) / (n + 1)
            u -= q
    return 1.0


PEN_TEXT = None      # None: bút gốc (Du Học Hải Dương); chuỗi: in chữ này lên bút trắng (lĩnh vực khác)
PEN_COLOR = (25, 70, 170)


def _pen_label(im, pen, text):
    """In tên thương hiệu dọc thân bút (bút đã xoá chữ gốc)."""
    size = int(pen['h'] * 1.25)
    f = font(size)
    while size > 12:
        bb = f.getbbox(text, stroke_width=1)
        if bb[2] - bb[0] <= pen['len'] * 1.08 and bb[3] - bb[1] <= pen['h'] * 1.2:
            break
        size -= 2
        f = font(size)
    bb = f.getbbox(text, stroke_width=1)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lay = Image.new('RGBA', (tw + 20, th + 20), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((10 - bb[0], 10 - bb[1]), text, font=f, fill=PEN_COLOR + (235,),
                             stroke_width=1, stroke_fill=PEN_COLOR + (235,))
    lay = lay.rotate(-pen['ang'], resample=Image.BICUBIC, expand=True)
    out = im.copy()
    out.alpha_composite(lay, (int(pen['cx'] - lay.width / 2), int(pen['cy'] - lay.height / 2)))
    return out


class Renderer:
    def __init__(self, logo_path=None, label=None, bg='trang', subs=False, trans='xoa', hook=True, cam=False):
        self.cam = bool(cam)
        self.trans = trans if trans in ('xoa', 'lia', 'xen', 'bang', 'bay') else 'xoa'
        self.hook = bool(hook)
        self.hand, self.tip, self.hand_shadow = self._load_hand('hand')
        self.hand_c = None                                        # tay cầm bút tô màu (nếu có ảnh hand_to.png)
        if os.path.exists(os.path.join(ASSETS, 'hand_to.png')):
            try:
                self.hand_c, self.tip_c, self.shadow_c = self._load_hand('hand_to')
            except Exception:
                self.hand_c = None
        lg = load_logo(logo_path if logo_path and os.path.exists(logo_path) else os.path.join(ASSETS, 'logo.png'))
        lw = LAY['logo_w']
        self.logo_small = scaled(lg, lw)
        if self.logo_small.height > lw:
            self.logo_small = lg.resize((int(lg.width * lw / lg.height), lw), Image.LANCZOS)
        bw, bh = LAY['big_logo']
        self.logo_big = scaled(lg, bw)
        if self.logo_big.height > bh:
            self.logo_big = lg.resize((int(lg.width * bh / lg.height), bh), Image.LANCZOS)
        self.paper = make_paper(bg or 'trang')
        self.subs = bool(subs)
        self.sub_style = 'noibat' if subs == 'noibat' else 'thuong'
        self.sub_font = font(80 if self.sub_style == 'noibat' else 60)
        self.label = None
        if label and label.strip():
            t = Txt(label.strip().upper(), 40, (255, 255, 255), 0, cx=0)
            w = t.im.width + 30
            im = Image.new('RGBA', (w, 70), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, 69), 35, fill=BLUE)
            im.alpha_composite(t.im, ((w - t.im.width) // 2, (70 - t.im.height) // 2))
            self.label = im
        self.eraser = self._make_eraser()

    @staticmethod
    def _load_hand(name):
        hj = json.load(open(os.path.join(ASSETS, name + '.json')))
        pen = hj.get('pen')
        if PEN_TEXT is not None and pen and os.path.exists(os.path.join(ASSETS, name + '_trang.png')):
            im = Image.open(os.path.join(ASSETS, name + '_trang.png')).convert('RGBA')
            if PEN_TEXT.strip():
                im = _pen_label(im, pen, PEN_TEXT.strip().upper())
        else:
            im = Image.open(os.path.join(ASSETS, name + '.png')).convert('RGBA')
        ha = np.asarray(im)[:, :, 3]                              # bóng tay: hình tay tô đen, làm mờ
        sh = Image.new('RGBA', im.size, (20, 20, 30, 0))
        sh.putalpha(Image.fromarray((ha * 0.22).astype(np.uint8)))
        return im, hj['tip'], sh.filter(ImageFilter.GaussianBlur(9))

    def _coloring(self, pl, t):
        """Tay đang ở giai đoạn tô màu (tô mảng, tô màu cho hình)?"""
        for it, s0, e0 in pl['sch']:
            if s0 <= t <= e0 and not getattr(it, 'nohand', False) and not getattr(it, 'presenter', False):
                if isinstance(it, Fill):
                    return True
                if isinstance(it, CharItem) and it.bp is not None:
                    return warp_r(it, (t - s0) / max(e0 - s0, 1e-3)) >= it.LE
                return False
        return False

    EMPH_T = 0.75

    @staticmethod
    def _layer_of(it):
        """Ảnh đã vẽ xong của một hình (cắt sát) + vị trí, tính một lần."""
        lay = getattr(it, '_lay', None)
        if lay is None:
            tmp = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            it.draw(tmp, 1.0)
            bb = tmp.getbbox() or (0, 0, 1, 1)
            lay = it._lay = (tmp.crop(bb), bb)
        return lay

    def _paste_scaled(self, f, it, k, dx=0.0, dy=0.0, alpha=1.0):
        im, (x0, y0, x1, y1) = self._layer_of(it)
        if k <= 0.02 or alpha <= 0.01:
            return
        w, h = max(1, int(im.width * k)), max(1, int(im.height * k))
        sc = im.resize((w, h), Image.BILINEAR) if (w, h) != im.size else im
        if alpha < 0.999:
            sc = with_alpha(sc, alpha)
        cx, cy = (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy
        f.paste(sc, (int(cx - w / 2), int(cy - h / 2)), sc)

    def _draw_item(self, f, it, r, t, e):
        if getattr(it, 'pop', False) and 0 < r < 1:          # nảy vào: to vượt một chút rồi về đúng cỡ
            c1 = 1.70158 * 1.4
            u = clamp(r) - 1
            k = 1 + (c1 + 1) * u ** 3 + c1 * u ** 2
            self._paste_scaled(f, it, max(0.05, k), alpha=clamp(r * 3))
            return
        em = getattr(it, 'emph', None) if FX.get('emph') else None
        if em and r >= 1 and e < t < e + self.EMPH_T:
            u = (t - e) / self.EMPH_T
            if em == 'phinh':
                self._paste_scaled(f, it, 1 + 0.09 * math.sin(math.pi * clamp(u * 2) ) * (1 - u * 0.5))
            elif em == 'rung':
                self._paste_scaled(f, it, 1.0, dx=14 * math.sin(u * 2 * math.pi * 5) * (1 - u))
            elif em == 'nay':
                self._paste_scaled(f, it, 1.0, dy=-34 * abs(math.sin(u * 2 * math.pi)) * (1 - u))
            else:
                it.draw(f, r)
            return
        it.draw(f, r)

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
        (top, bot), rows = LAY['erase'], 4
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

    def _wrap_sub(self, text, maxw=None):
        maxw = maxw or SUB_MAXW
        words, lines, cur = text.split(), [], ''
        for w_ in words:
            t = (cur + ' ' + w_).strip()
            if self.sub_font.getlength(t) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur); cur = w_
        if cur:
            lines.append(cur)
        return lines

    def make_subs(self, say, start, dur):
        """Phụ đề karaoke: mỗi lần 1 dòng ngắn, từng từ đổi màu theo nhịp đọc (thời gian chia theo độ dài chữ)."""
        say = re.sub(r'\s+', ' ', (say or '').replace('*', '')).strip()
        say = re.sub(r'([?!.…:])\s*,', r'\1', say).rstrip(',')
        if not say or not dur:
            return []
        parts = [p_.strip() for p_ in re.split(r'(?<=[.!?…;:,])\s+', say) if p_.strip()]
        lines = []
        for p_ in parts:
            for l in self._wrap_sub(p_):
                if lines and len(l) < 12 and self.sub_font.getlength(lines[-1] + ' ' + l) <= SUB_MAXW:
                    lines[-1] += ' ' + l
                else:
                    lines.append(l)
        weight = lambda w_: len(w_) + 2
        total = sum(weight(w_) for l in lines for w_ in l.split())
        out, t = [], start
        for l in lines:
            words = l.rstrip(',').split()
            ws, wt = [], t
            for w_ in words:
                d = dur * weight(w_) / total
                ws.append((wt, wt + d))
                wt += d
            out.append((t, wt, words, ws))
            t = wt
        return out

    def draw_sub(self, f, pl, t):
        subs = pl.get('subs') or []
        for k, (a, b, words, ws) in enumerate(subs):
            last = k == len(subs) - 1
            if a <= t < b or (last and b <= t < b + 0.6):
                fnt = self.sub_font
                sp = fnt.getlength(' ')
                widths = [fnt.getlength(w_) for w_ in words]
                total = sum(widths) + sp * (len(words) - 1)
                x = W / 2 - total / 2
                d = ImageDraw.Draw(f)
                if self.sub_style == 'noibat':             # kiểu CapCut: chữ trắng viền đậm, từ đang đọc nằm trong ô cam
                    asc, desc = fnt.getmetrics()
                    cur = max([j for j, (wa, _) in enumerate(ws) if wa <= t] or [0])
                    for j, (w_, wd, (wa, wb)) in enumerate(zip(words, widths, ws)):
                        if j == cur:
                            pad = 14
                            d.rounded_rectangle((x - pad, SUB_Y - 4, x + wd + pad, SUB_Y + asc + desc + 2), 18,
                                                fill=ORANGE)
                            d.text((x, SUB_Y), w_, font=fnt, fill=(255, 255, 255), stroke_width=3, stroke_fill=ORANGE)
                        else:
                            d.text((x, SUB_Y), w_, font=fnt, fill=(255, 255, 255) if t >= wa else (250, 250, 250),
                                   stroke_width=9, stroke_fill=(25, 28, 40))
                        x += wd + sp
                    return
                for w_, wd, (wa, wb) in zip(words, widths, ws):
                    col = SUB_ON if t >= wa else SUB_OFF
                    d.text((x, SUB_Y), w_, font=fnt, fill=col, stroke_width=7, stroke_fill=(255, 255, 255))
                    x += wd + sp
                return

    def plan(self, scenes, audio_durs, gender=None):
        global LCX, LMAXW, BOTTOM_AREA
        if self.trans == 'bay':
            self._auto_group(scenes)
        plans = []
        old_bottom = BOTTOM_AREA
        if self.subs:
            BOTTOM_AREA = SUB_Y - 22 if any(audio_durs or []) else BOTTOM_AREA
        n = len(scenes)
        poses = [None] * n
        if gender and char_path(gender, 'chao'):
            poses[0] = 'chao'
            if n > 1:
                poses[-1] = 'like'
            budget = max(1, int((n - 2) * 0.4))
            for i in range(1, n - 1):
                if budget and poses[i - 1] is None and important_scene(scenes[i]) and scene_kind(scenes[i]) != 'vs':
                    poses[i] = 'chi'
                    budget -= 1
        for i, sc in enumerate(scenes):
            logo_end = any('logo' in tags for _, tags in sc['lines'])
            pose = poses[i] if not (poses[i] and not logo_end and scene_kind(sc) == 'vs') else None
            if self.trans == 'bay' and sc.get('keep') and i > 0:    # trong cùng góc bảng: người dẫn đã đứng ở trang đầu
                pose = None
            if pose == 'like':
                LCX, LMAXW = LAY['col_like']
            elif pose:
                LCX, LMAXW = LAY['col_char']
            else:
                LCX, LMAXW = LAY['col_full']
            snap = None
            nxt_logo_any = i + 1 < len(scenes) and any('logo' in tg for _, tg in scenes[i + 1]['lines'])
            chain = self.trans == 'bang' and i > 0 and not logo_end     # bảng liền: cảnh cũ thu nhỏ lên trên, vẽ tiếp bên dưới
            if (sc.get('keep') or chain) and plans and not plans[-1]['logo_end'] and self.trans != 'bay':
                snap = self._snapshot(plans[-1], big=chain and not sc.get('keep'))
            if snap:
                old_top = TOP_AREA
                globals()['TOP_AREA'] = snap.dst[3] + 34
                try:
                    items = layout_scene(sc, i, logo_end)
                finally:
                    globals()['TOP_AREA'] = old_top
                items = [snap] + items
                p_ = plans[-1]
                if not p_.get('keep_next'):
                    p_['keep_next'] = True
                    p_['n'] = max(1, p_['n'] - int(p_.get('tr', ERASE) * FPS))
                    p_['dur'] = p_['n'] / FPS
            else:
                items = layout_scene(sc, i, logo_end)
            if sc.get('count'):
                at = 1 if (items and isinstance(items[0], Snap)) else 0
                items = items[:at] + [Badge(sc['count'], seed=i * 7)] + items[at:]
            if pose:
                cx_, feet_, kk = LAY['char']
                hgt = {'chao': 760, 'chi': 640, 'like': 700}[pose] * kk
                hgt = min(hgt, feet_ - TOP_AREA + 40)
                ch = CharItem(char_path(gender, pose), cx_, feet_, hgt)
                ch.gap = 0.1
                ch.presenter = True
                items = [ch] + items
            lcx = LCX
            LCX, LMAXW = LAY['col_full']
            natural = ENTER + sum(it.dur + getattr(it, 'gap', GAP) for it in items)
            A = audio_durs[i] if audio_durs else None
            k = 1.0
            if A:
                k = max(0.45, min(1.5, (A * 0.88) / max(natural, 0.1)))
            say_n = norm(' '.join(sc.get('say') or []))
            t, sch = ENTER * k, []
            spare = (A * 0.88) / max(natural, 0.1) if A else 1.0
            pz_ratio = 0.12 if spare >= 1.6 else 0.07 if spare >= 1.2 else 0.0
            for it in items:
                it._pz = None
                if pz_ratio and it.dur * k >= 0.9 and not isinstance(it, (Badge, Snap)) \
                        and not getattr(it, 'presenter', False):
                    it._pz = (pz_ratio, max(1, min(4, int(it.dur * k / 0.9))))
                if isinstance(it, Badge):                         # huy hiệu 1/3 tự hiện nhanh, không bắt tay vẽ
                    it.nohand = True
                    it.sfx = 'bup'
                    sch.append((it, 0.0, 0.3))
                    continue
                if i == 0 and self.hook and isinstance(it, Txt):   # cảnh mở: chữ hiện ngay từ khung đầu
                    it.nohand = True
                    sch.append((it, -1.0, -0.999))
                    continue
                d = it.dur * k
                key = getattr(it, 'sync', None)
                if key and A:                       # chờ tới lúc lời đọc nhắc tới mới vẽ
                    f_ = _sync_frac(say_n, key)
                    if f_ is not None:
                        t = max(t, 0.12 + f_ * A - 0.2)
                sch.append((it, t, t + d))
                t += d + getattr(it, 'gap', GAP) * k
            ed = (sch[-1][2]) if sch else 0.3
            hold = 2.0 if logo_end else (0.3 if A else 1.2)
            dur = max(ed + EXIT + hold, (A + 0.45) if A else 0)
            last = i == len(scenes) - 1
            tr = ERASE
            if self.trans == 'bay':                            # camera bay: lướt trong góc bảng, bay giữa các góc
                nxt_logo = i + 1 < len(scenes) and any('logo' in tg for _, tg in scenes[i + 1]['lines'])
                nxt_cont = i + 1 < len(scenes) and scenes[i + 1].get('keep') and not nxt_logo
                tr = 2.6 if (nxt_logo and i >= 2) else 0.8 if nxt_cont else 2.1
            if not last:
                dur += tr
            nfr = int(math.ceil(dur * FPS))
            subs = self.make_subs(' '.join(sc.get('say') or []), 0.12, A) if (self.subs and A) else []
            trans = 'bay' if self.trans == 'bay' else \
                'lia' if (self.trans == 'bang' and nxt_logo_any) else \
                'lia' if (self.trans == 'lia' or (self.trans == 'xen' and i % 2 == 1)) else 'xoa'
            plans.append({'sch': sch, 'ed': ed, 'n': nfr, 'dur': nfr / FPS, 'logo_end': logo_end, 'last': last,
                          'lcx': lcx, 'subs': subs, 'trans': trans, 'tr': tr,
                          'cont': bool(self.trans == 'bay' and sc.get('keep') and i > 0 and not logo_end)})
        BOTTOM_AREA = old_bottom
        if self.trans == 'bay':
            self._board(plans)
        return plans

    # ------------------------------------------------------------ CAMERA BAY (kiểu VideoScribe)
    # Mỗi cảnh là một "trang" đặt trên tấm bảng lớn: thế giới (x, y, tỉ lệ). Không xoá bảng:
    #  - bay: camera lùi ra rồi bay sang chỗ trống bên cạnh; chữ đầu của cảnh mới đã có sẵn ở đó (hạt giống)
    #  - lặn: cảnh mới bắt đầu bằng số (huy hiệu 1/3...) thì số đó hiện bé xíu ở chỗ trống của cảnh cũ,
    #         camera phóng xuyên vào nó và nó thành đầu cảnh mới
    #  - tóm tắt: trước cảnh kết camera lùi thật xa cho thấy cả tấm bảng
    DIRS = [(1, 0), (1, 0), (0, 1), (-1, 0), (-1, 0), (0, 1)]

    def _seed_of(self, pl):
        for it, s_, e_ in pl['sch']:
            if isinstance(it, Badge):
                return it
        for it, s_, e_ in pl['sch']:
            if isinstance(it, Txt) and not getattr(it, 'nohand', False):
                return it
        return None

    @staticmethod
    def _auto_group(scenes):
        """Camera bay: gộp 2–3 dòng liền nhau thành một "góc bảng" (nếu kịch bản chưa tự đánh dấu [tiếp])."""
        if any(sc.get('keep') for sc in scenes):
            return
        n = 0
        for i, sc in enumerate(scenes):
            tags = [tg for _, tg in sc.get('lines', [])]
            logo = any('logo' in tg for tg in tags)
            if i <= 1 or logo or sc.get('count') or n >= 3 or scene_kind(sc) in ('vs', 'big'):
                n = 1                                          # cảnh mở đầu, cảnh có số [1/3], bảng so sánh: mở góc mới
                continue
            sc['keep'] = True
            n += 1

    def _board(self, plans):
        """Đặt các trang lên tấm bảng lớn. Trong một góc bảng, các trang nối nhau sát mép nội dung
        (dọc: xếp xuống dưới, ngang: xếp sang phải); các góc bảng nằm cạnh nhau theo hình zic-zắc."""
        for i, p_ in enumerate(plans):
            p_['_i'] = i
            p_['_all'] = plans
        for i, p_ in enumerate(plans):                      # chữ/số mở đầu cảnh mới vẽ sẵn: camera tới là thấy
            if i == 0:
                continue
            sd = self._seed_of(p_)
            if sd is None:
                continue
            p_['sch'] = [(it, -1.0, -0.999) if it is sd else (it, a_, b_) for it, a_, b_ in p_['sch']]
            sd.nohand = True
            p_['_seed'] = sd
        tall = H >= W
        groups, cur = [], []
        for p_ in plans:
            if cur and not p_.get('cont'):
                groups.append(cur)
                cur = []
            cur.append(p_)
        if cur:
            groups.append(cur)
        gid = 0
        for g in groups:
            for p_ in g:
                p_['_g'] = gid
            gid += 1
        # vị trí trong góc: xếp theo khung nội dung thật
        for g in groups:
            x, y = 0.0, 0.0
            prev_bb = None
            for p_ in g:
                bb = self._ink(p_, p_['dur'] - p_.get('tr', ERASE)).getbbox() or (0, TOP_AREA, W, BOTTOM_AREA)
                if prev_bb is not None:
                    if tall:
                        y = y + prev_bb[3] + 70 - bb[1]
                    else:
                        x = x + prev_bb[2] + 80 - bb[0]
                p_['_rel'] = (x, y)
                prev_bb = bb
            # khung bao cả góc (toạ độ góc, chưa nhân tỉ lệ)
            xs0 = min(p_['_rel'][0] for p_ in g); ys0 = min(p_['_rel'][1] for p_ in g)
            xs1 = max(p_['_rel'][0] + W for p_ in g); ys1 = max(p_['_rel'][1] + H for p_ in g)
            for p_ in g:
                p_['_gbox'] = (xs0, ys0, xs1, ys1)
        # đặt các góc lên bảng: dọc thì đi ngang (zic-zắc xuống), ngang thì đi dọc (zic-zắc sang phải)
        DIRS = [(1, 0), (1, 0), (0, 1), (-1, 0), (-1, 0), (0, 1)] if tall else [(0, 1), (0, 1), (1, 0), (0, -1), (0, -1), (1, 0)]
        ox, oy, sc_ = 0.0, 0.0, 1.0
        step = 0
        prev_box = None
        boxes = []
        for gi, g in enumerate(groups):
            gx0, gy0, gx1, gy1 = g[0]['_gbox']
            if gi > 0:
                prv = groups[gi - 1][-1]
                px, py, ps = prv['_wp']
                prv['_tt'] = 'recap' if prv.get('tr', ERASE) > 2.3 else 'fly'
                spot = None
                if prv['_tt'] == 'fly' and isinstance(g[0].get('_seed'), Badge):
                    spot = self._dive_spot(prv, g[0])
                if spot:
                    q, sx, sy = spot
                    sc_ = ps * q
                    ox = px + sx * ps - g[0]['_rel'][0] * sc_
                    oy = py + sy * ps - g[0]['_rel'][1] * sc_
                    prv['_tt'] = 'dive'
                else:
                    bx0, by0, bx1, by1 = prev_box
                    gap = 0.12

                    def cand(d):
                        dx, dy = d
                        if dx > 0:
                            return bx1 + gap * W * sc_ - gx0 * sc_, by0 - gy0 * sc_
                        if dx < 0:
                            return bx0 - gap * W * sc_ - gx1 * sc_, by0 - gy0 * sc_
                        if dy > 0:
                            return bx0 - gx0 * sc_, by1 + gap * H * sc_ - gy0 * sc_
                        return bx0 - gx0 * sc_, by0 - gap * H * sc_ - gy1 * sc_

                    def free(o):                               # không đè lên góc bảng nào đã vẽ
                        nb = (o[0] + gx0 * sc_, o[1] + gy0 * sc_, o[0] + gx1 * sc_, o[1] + gy1 * sc_)
                        m = 0.05 * W * sc_
                        return all(nb[2] + m <= q[0] or nb[0] >= q[2] + m or nb[3] + m <= q[1] or nb[1] >= q[3] + m
                                   for q in boxes)

                    pref = DIRS[step % len(DIRS)]
                    step += 1
                    o = None
                    for d in [pref, (1, 0), (0, 1), (-1, 0), (0, -1)]:
                        c_ = cand(d)
                        if free(c_):
                            o = c_
                            break
                    if o is None:                              # hết chỗ quanh đây: sang hẳn hàng mới bên dưới tất cả
                        o = (bx0 - gx0 * sc_, max(q[3] for q in boxes) + gap * H * sc_ - gy0 * sc_)
                    ox, oy = o
            for p_ in g:
                rx, ry = p_['_rel']
                p_['_wp'] = (ox + rx * sc_, oy + ry * sc_, sc_)
            prev_box = (ox + gx0 * sc_, oy + gy0 * sc_, ox + gx1 * sc_, oy + gy1 * sc_)
            boxes.append(prev_box)
            for p_ in g[:-1]:
                p_['_tt'] = 'glide'

    def _dive_spot(self, prv, cur):
        """Tìm chỗ trống trên trang cũ đủ chứa cả góc bảng mới (thu nhỏ) để camera phóng xuyên vào.
        Trả (tỉ lệ, gốc x, gốc y của trang đầu góc mới trong toạ độ trang cũ) hoặc None."""
        gx0, gy0, gx1, gy1 = cur['_gbox']
        rx, ry = cur['_rel']
        gw, gh = gx1 - gx0, gy1 - gy0
        ink = np.asarray(self._ink(prv, prv['dur'] - prv.get('tr', ERASE)))[:, :, 3] > 20
        cs = 8
        hh, ww = H // cs, W // cs
        m = ink[:hh * cs, :ww * cs].reshape(hh, cs, ww, cs).any(axis=(1, 3)).astype(np.int32)
        ii = np.pad(m.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        top, bot = int((TOP_AREA + 30) / cs), int((BOTTOM_AREA - 30) / cs)
        for q in (0.26, 0.2, 0.15, 0.11):
            bw, bh = int(gw * q / cs) + 6, int(gh * q / cs) + 6
            best = None
            for y in range(top, bot - bh, 2):
                for x in range(3, ww - bw - 3, 2):
                    if ii[y + bh, x + bw] - ii[y, x + bw] - ii[y + bh, x] + ii[y, x] == 0:
                        score = y + 0.6 * x                   # ưu tiên góc dưới bên phải
                        if best is None or score > best[0]:
                            best = (score, x, y)
            if best:
                _, x, y = best
                X, Y = (x + 3) * cs, (y + 3) * cs                # góc trên-trái của cả góc bảng mới
                return q, X + (rx - gx0) * q, Y + (ry - gy0) * q
        return None

    def _content(self, pl, t):
        """Giấy + mọi thứ đã vẽ tới thời điểm t (chưa có tay, camera, logo nhỏ, phụ đề)."""
        f = self.paper.copy()
        self._paint(f, pl, t)
        return f

    def _paint(self, f, pl, t):
        if pl['logo_end']:
            k = eo((t - 0.1) / 0.6)
            if k > 0:
                lg = with_alpha(self.logo_big, k)
                f.paste(lg, (int(pl.get('lcx', W / 2) - lg.width / 2), int(LAY['big_logo_y'] + (1 - k) * 30)), lg)
        for it, s, e in pl['sch']:
            if isinstance(it, Fill):
                it.draw(f, warp_r(it, (t - s) / max(e - s, 1e-3)))
        for it, s, e in pl['sch']:
            if not isinstance(it, Fill):
                self._draw_item(f, it, warp_r(it, (t - s) / max(e - s, 1e-3)), t, e)

    def _ink(self, pl, t):
        """Chỉ phần mực (nền trong suốt) để ghép nhiều cảnh lên cùng một tờ giấy."""
        key = ('_ink', round(t, 3))
        c = pl.setdefault('_inkc', {})
        if key not in c:
            lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            self._paint(lay, pl, t)
            c[key] = lay
        return c[key]

    def _put(self, g, ink, wp, cx, cy, vs, alpha=1.0):
        """Ghép trang (mực) đặt ở wp=(x, y, tỉ lệ) lên khung hình theo camera (tâm cx, cy; vs = đơn vị/px)."""
        x, y, sc = wp
        k = sc / vs                                           # cỡ trang trên màn hình so với khung
        if k < 0.004 or alpha <= 0.01:
            return
        x0, y0 = (x - cx) / vs + W / 2, (y - cy) / vs + H / 2
        X0, Y0 = max(0.0, x0), max(0.0, y0)
        X1, Y1 = min(float(W), x0 + W * k), min(float(H), y0 + H * k)
        if X1 - X0 < 2 or Y1 - Y0 < 2:
            return
        box = ((X0 - x0) / k, (Y0 - y0) / k, (X1 - x0) / k, (Y1 - y0) / k)
        tw, th = int(round(X1 - X0)), int(round(Y1 - Y0))
        if tw < 1 or th < 1:
            return
        im = ink.resize((tw, th), Image.BILINEAR, box=box, reducing_gap=2.0 if k < 0.5 else None)
        if alpha < 0.999:
            im = with_alpha(im, alpha)
        g.paste(im, (int(round(X0)), int(round(Y0))), im)

    @staticmethod
    def _view(p_):
        x, y, sc = p_['_wp']
        return x + W * sc / 2, y + H * sc / 2, sc

    def _gview(self, p_):
        """Camera nhìn trọn cả góc bảng chứa trang p_."""
        x, y, sc = p_['_wp']
        rx, ry = p_['_rel']
        gx0, gy0, gx1, gy1 = p_['_gbox']
        ox, oy = x - rx * sc, y - ry * sc
        bw, bh = (gx1 - gx0) * sc, (gy1 - gy0) * sc
        v = max(bw / W, bh / H) / 0.94
        return ox + (gx0 + gx1) / 2 * sc, oy + (gy0 + gy1) / 2 * sc, max(v, sc)

    @staticmethod
    def _lerpv(a, b, u):
        return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u,
                math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * u))

    def _arc(self, a, b, u):
        """Bay từ view a sang view b, giữa đường lùi ra một chút để thấy cả hai nơi."""
        cx, cy, vb = self._lerpv(a, b, u)
        dx, dy = abs(b[0] - a[0]) / vb, abs(b[1] - a[1]) / vb
        A = min(1.2, max(0.0, max(dx / W, dy / H) - 0.15))
        return cx, cy, vb * (1 + A * math.sin(math.pi * u))

    def _end_view(self, p_):
        """Camera lúc trang vừa vẽ xong (khung đầy đủ của trang)."""
        return self._view(p_)

    def _compose(self, upto, cx, cy, vs, skip=None, special=None, dim=None):
        g = self.paper.copy()
        allp = upto[0]['_all'] if upto else []
        for p_ in upto:
            if p_ is skip:
                continue
            if special is not None and p_ is special[0]:
                ink = special[1]
            else:
                ink = self._ink(p_, p_['dur'] - p_.get('tr', ERASE))
            if p_['_wp'][2] / vs > 1.7 and not (dim and p_ is dim[0]):
                continue                                       # trang quá to (đã phóng xuyên qua): bỏ cho khỏi rối
            self._put(g, ink, p_['_wp'], cx, cy, vs, dim[1] if (dim and p_ is dim[0]) else 1.0)
        return g

    def fly(self, pl, e, first, prog):
        allp, i = pl['_all'], pl['_i']
        nxt = allp[i + 1]
        tt = pl.get('_tt', 'fly')
        a = self._end_view(pl)
        b = self._start_view(nxt)
        k = clamp(e)
        nxt_ink = self._ink(nxt, 0.0)
        dim = None
        if tt == 'glide':                                     # trong góc bảng: lướt nhẹ sang phần vẽ tiếp
            cx, cy, vs = self._lerpv(a, b, eio(k))
        elif tt == 'dive':                                    # số bé xíu hiện ra, rồi camera phóng xuyên vào nó
            seed_k = eo(clamp(k / 0.22))
            u = eio(clamp((k - 0.22) / 0.78))
            v0, v1 = a[2], b[2]
            vs = math.exp(math.log(v0) + (math.log(v1) - math.log(v0)) * u)
            r_ = (vs - v1) / (v0 - v1) if abs(v0 - v1) > 1e-9 else 1 - u
            cx, cy = b[0] + (a[0] - b[0]) * r_, b[1] + (a[1] - b[1]) * r_
            dim = (pl, 1 - clamp((u - 0.5) / 0.35))
            if seed_k < 0.999:
                sd = nxt.get('_seed')
                lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                if sd is not None:
                    bb = self._item_bb(sd)
                    if bb:
                        c_ = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
                        s2 = max(0.05, seed_k)
                        im = nxt_ink.resize((max(1, int(W * s2)), max(1, int(H * s2))), Image.BILINEAR)
                        lay.paste(im, (int(c_[0] - c_[0] * s2), int(c_[1] - c_[1] * s2)), im)
                nxt_ink = lay
        else:
            gv = self._gview(pl)                              # lùi ra nhìn trọn góc bảng vừa vẽ xong
            if tt == 'recap':                                 # trước cảnh kết: lùi thật xa cho thấy cả tấm bảng
                pts = [p_['_wp'] for p_ in allp[:i + 2]]
                xs0 = min(x for x, y, s_ in pts); ys0 = min(y for x, y, s_ in pts)
                xs1 = max(x + W * s_ for x, y, s_ in pts); ys1 = max(y + H * s_ for x, y, s_ in pts)
                gv = ((xs0 + xs1) / 2, (ys0 + ys1) / 2, max(max((xs1 - xs0) / W, (ys1 - ys0) / H) / 0.92, a[2], b[2]))
            if k < 0.34:
                cx, cy, vs = self._lerpv(a, gv, eio(k / 0.34))
            elif k < 0.5:
                cx, cy, vs = gv
            else:
                cx, cy, vs = self._arc(gv, b, eio((k - 0.5) / 0.5))
        g = self._compose(allp[:i + 1] + [nxt], cx, cy, vs, special=(nxt, nxt_ink), dim=dim)
        return self._overlay(g, pl, prog)

    def _overlay(self, g, pl, prog):
        if not pl['logo_end']:
            g.paste(self.logo_small, LAY['logo_xy'], self.logo_small)
        if self.label is not None:
            g.paste(self.label, (W - LAY['label_r'] - self.label.width, LAY['label_y']), self.label)
        if prog is not None:
            d = ImageDraw.Draw(g)
            bx0, by0, bx1 = LAY['bar']
            d.rounded_rectangle((bx0, by0, bx1, by0 + 12), 6, fill=(232, 232, 228))
            d.rounded_rectangle((bx0, by0, bx0 + max(12, int((bx1 - bx0) * clamp(prog))), by0 + 12), 6, fill=ORANGE)
        return g

    def _neighbors(self, f, pl):
        """Camera bay: vẽ các trang đã xong nằm quanh trang hiện tại (cùng góc bảng hoặc góc cạnh bên)."""
        allp, i = pl['_all'], pl['_i']
        x, y, sc = pl['_wp']
        cx, cy = x + W * sc / 2, y + H * sc / 2
        for p_ in allp[:i]:
            if p_['_wp'][2] / sc > 1.7:
                continue
            self._put(f, self._ink(p_, p_['dur'] - p_.get('tr', ERASE)), p_['_wp'], cx, cy, sc)

    def _story(self, pl, t):
        """Camera kể chuyện: cận cảnh chữ/hình đầu tiên, tới khi vẽ hình kế tiếp thì lùi ra lấy chỗ vẽ thêm."""
        st = pl.get('_story', 0)
        if st == 0:
            st = None
            sch = [x for x in pl['sch'] if not getattr(x[0], 'nohand', False) and not getattr(x[0], 'presenter', False)
                   and not isinstance(x[0], (Snap, Badge))]
            sd = pl.get('_seed')
            first = None
            if sd is not None and sch and sch[0][1] >= 0.8:          # mở cảnh: đang cận chữ có sẵn, lùi ra khi vẽ tiếp
                first, s0, s1 = sd, -1.0, sch[0][1]
            elif len(sch) >= 2 and sch[1][1] - sch[0][1] >= 1.4:
                first, s0, s1 = sch[0][0], sch[0][1], sch[1][1]
            if first is not None:
                lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))     # khung thật của chữ/hình (không đoán theo nét bút)
                try:
                    first.draw(lay, 1.0)
                    bb = lay.getbbox()
                except Exception:
                    bb = None
                if bb:
                    x0, y0, x1, y1 = bb[0] - 60, bb[1] - 60, bb[2] + 60, bb[3] + 60
                    Z = min(1.4, W / max(1, x1 - x0), 0.6 * H / max(1, y1 - y0))
                    if Z >= 1.1:
                        st = (Z, (x0 + x1) / 2, (y0 + y1) / 2, s0, s1)
            pl['_story'] = st
        if not st:
            return 1.0, None
        Z, fx, fy, s0, s1 = st
        zin = 1.0 if s0 < 0 else eio(clamp((t - (s0 - 0.3)) / 0.7))
        zout = 1 - eio(clamp((t - (s1 - 0.55)) / 0.75))
        return 1 + (Z - 1) * zin * zout, (fx, fy)

    def _start_view(self, p_):
        """Camera lúc cảnh bắt đầu (có thể đang cận chữ mở đầu) tính theo toạ độ bảng lớn."""
        x, y, sc = p_['_wp']
        z, zx, zy = 1.0, W / 2, H / 2
        if self.cam and not p_['logo_end']:
            sz, fc = self._story(p_, 0.0)
            if fc is not None and sz > 1.0005:
                z, zx, zy = sz, fc[0], fc[1]
                hw, hh = W / (2 * z), H / (2 * z)
                zx, zy = min(max(zx, hw), W - hw), min(max(zy, hh), H - hh)
        return x + zx * sc, y + zy * sc, sc / z

    @staticmethod
    def _item_bb(it):
        bb = getattr(it, '_bbx', 0)
        if bb == 0:
            lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            try:
                it.draw(lay, 1.0)
                bb = lay.getbbox()
            except Exception:
                bb = None
            try:
                it._bbx = bb
            except Exception:
                pass
        return bb

    def _drawn_bb(self, pl, t):
        """Khung bao các chữ/hình đã bắt đầu vẽ tới lúc t (bỏ người dẫn, huy hiệu, hình nền)."""
        u = None
        for it, s_, e_ in pl['sch']:
            if s_ > t or isinstance(it, (Fill, Badge)) or getattr(it, 'presenter', False):
                continue
            bb = self._item_bb(it)
            if bb:
                u = bb if u is None else (min(u[0], bb[0]), min(u[1], bb[1]), max(u[2], bb[2]), max(u[3], bb[3]))
        return u

    def _bgc(self):
        c = getattr(self, '_bg_c', None)
        if c is None:
            a = np.asarray(self.paper.convert('RGB'))
            c = self._bg_c = tuple(int(v) for v in np.median(a.reshape(-1, 3), axis=0))
        return c

    def _snapshot(self, pl, big=False):
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for it, s_, e_ in pl['sch']:
            if isinstance(it, Fill):
                it.draw(layer, 1.0)
        for it, s_, e_ in pl['sch']:
            if isinstance(it, Badge) or (big and isinstance(it, Snap)):   # bảng liền: chỉ giữ cảnh ngay trước cho dễ đọc
                continue
            if not isinstance(it, (Fill, CharItem)) or (isinstance(it, CharItem) and not getattr(it, 'presenter', False)):
                it.draw(layer, 1.0)
        bb = layer.getbbox()
        if not bb:
            return None
        img = layer.crop(bb)
        mh = (BOTTOM_AREA - TOP_AREA) * (0.36 if big else 0.3)
        k = min(mh / img.height, (W * (0.8 if big else 0.62)) / img.width, 1.0)
        w, h = img.width * k, img.height * k
        dst = (W / 2 - w / 2, TOP_AREA - 10, W / 2 + w / 2, TOP_AREA - 10 + h)
        return Snap(img, tuple(bb), dst)

    def hand_pos(self, pl, t):
        """Vị trí đầu bút (x, y, độ nhấc 0..1). Giữa hai nét: tay nhấc lên theo đường cong rồi hạ xuống."""
        sch = [x for x in pl['sch'] if not getattr(x[0], 'nohand', False)]
        ed = pl['ed']
        OFF = LAY['hand_off']
        if not sch:
            return None
        lerp = lambda a, b, k: (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)

        def hop(a, b, k):
            p_ = lerp(a, b, eio(k))
            lift = math.sin(math.pi * clamp(k)) * min(1.0, math.dist(a, b) / 260)
            return (p_[0], p_[1] - 46 * lift, lift)
        if t < sch[0][1]:
            return hop(OFF, sch[0][0].pos(0, t), t / max(sch[0][1], 0.01))
        for i, (it, s, e) in enumerate(sch):
            if s <= t <= e:
                p_ = it.pos(warp_r(it, (t - s) / max(e - s, 1e-3)), t)
                return (p_[0] + 1.3 * math.sin(t * 47), p_[1] + 1.1 * math.cos(t * 41), 0.0)
            if i + 1 < len(sch) and e < t < sch[i + 1][1]:
                return hop(it.pos(1, t), sch[i + 1][0].pos(0, t), (t - e) / max(sch[i + 1][1] - e, 1e-3))
        k = (t - ed) / EXIT
        if k >= 1:
            return None
        return hop(sch[-1][0].pos(1, t), OFF, k)

    CAM_Z = 0.05            # phóng tối đa 5%

    def _focus_raw(self, pl, t):
        sch = [x for x in pl['sch'] if not getattr(x[0], 'nohand', False) and not getattr(x[0], 'presenter', False)]
        if not sch:
            return None
        cur = sch[0]
        for x in sch:
            if x[1] <= t:
                cur = x
        it, s0, e0 = cur
        cc = getattr(it, '_cc', None)                 # tâm của cả hình/chữ (cố định), không bám đầu bút
        if cc is None:
            try:
                pts = [it.pos(k, 0.0) for k in (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95)]
                cc = (sum(p_[0] for p_ in pts) / len(pts), sum(p_[1] for p_ in pts) / len(pts))
            except Exception:
                cc = (W / 2, (TOP_AREA + BOTTOM_AREA) / 2)
            it._cc = cc
        return cc

    def cam_view(self, pl, t):
        """(độ phóng, tâm x, tâm y): phóng nhẹ theo chỗ tay đang vẽ, vẽ xong thì lùi ra toàn cảnh."""
        if not self.cam or pl.get('logo_end'):
            return 1.0, W / 2, H / 2
        ed = pl['ed']
        z_in = eio(clamp((t - 0.15) / 1.0))
        z_out = 1 - eio(clamp((t - ed - 0.2) / 1.1))
        z_end = 1 - eio(clamp((t - (pl['dur'] - pl.get('tr', ERASE) - 0.7)) / 0.6)) if not pl['last'] else 1.0
        z = 1 + self.CAM_Z * z_in * z_out * z_end
        if z <= 1.0005:
            return 1.0, W / 2, H / 2
        path = pl.get('_campath')
        if path is None:                              # đường đi camera của cả cảnh, làm mượt một lần (Gauss ~0.6s)
            n = pl['n'] + 2
            raw = np.array([self._focus_raw(pl, k / FPS) or (W / 2, (TOP_AREA + BOTTOM_AREA) / 2) for k in range(n)],
                           dtype=np.float64)
            sig = 0.6 * FPS
            ker = np.exp(-0.5 * (np.arange(-int(3 * sig), int(3 * sig) + 1) / sig) ** 2)
            ker /= ker.sum()
            pad = len(ker) // 2
            sm = [np.convolve(np.pad(raw[:, j], pad, mode='edge'), ker, mode='valid') for j in (0, 1)]
            path = pl['_campath'] = np.stack(sm, axis=1)
        fi = clamp(t * FPS / max(1, len(path) - 1)) * (len(path) - 1)
        i0 = int(fi); i1 = min(i0 + 1, len(path) - 1); u = fi - i0
        cx = path[i0, 0] * (1 - u) + path[i1, 0] * u
        cy = path[i0, 1] * (1 - u) + path[i1, 1] * u
        cx = W / 2 + (cx - W / 2) * 0.7                     # chỉ nghiêng về phía chỗ đang vẽ, không bám sát
        cy = (TOP_AREA + BOTTOM_AREA) / 2 + (cy - (TOP_AREA + BOTTOM_AREA) / 2) * 0.7
        hw, hh = W / (2 * z), H / (2 * z)
        return z, min(max(cx, hw), W - hw), min(max(cy, hh), H - hh)

    def frame(self, pl, t, first, prog=None):
        TR = pl.get('tr', ERASE)
        if pl.get('trans') == 'bay' and '_all' in pl and not pl['last'] and not pl.get('keep_next') \
                and t > pl['dur'] - TR:
            return self.fly(pl, (t - (pl['dur'] - TR)) / TR, first, prog)
        if pl.get('trans') == 'bay' and '_wp' in pl and pl['_i'] > 0:
            f = self.paper.copy()
            self._neighbors(f, pl)
            self._paint(f, pl, t)
        else:
            f = self._content(pl, t)
        hp = self.hand_pos(pl, t)
        if hp:
            lift = hp[2] if len(hp) > 2 else 0.0
            hand, tip, shadow = self.hand, self.tip, self.hand_shadow
            if self.hand_c is not None and self._coloring(pl, t):
                hand, tip, shadow = self.hand_c, self.tip_c, self.shadow_c
            hx, hy = int(hp[0] - tip[0]), int(hp[1] - tip[1])
            f.paste(shadow, (hx + int(14 + 30 * lift), hy + int(18 + 52 * lift)), shadow)
            f.paste(hand, (hx, hy), hand)
        z, zx, zy = self.cam_view(pl, t)
        if self.cam and self.trans in ('bay', 'bang') and not pl['logo_end']:
            sz, fc = self._story(pl, t)
            if fc is not None and sz > 1.0005:
                u = (sz - 1) / max(1e-6, pl['_story'][0] - 1)
                z = z * sz
                zx, zy = zx + (fc[0] - zx) * u, zy + (fc[1] - zy) * u
                hw, hh = W / (2 * z), H / (2 * z)
                zx, zy = min(max(zx, hw), W - hw), min(max(zy, hh), H - hh)
        if z > 1.0005:                                     # đừng để camera cắt mất chữ/hình đã vẽ (nếu khung đủ chứa)
            ub = self._drawn_bb(pl, t)
            if ub:
                hw, hh = W / (2 * z), H / (2 * z)
                if ub[2] - ub[0] <= 2 * hw:
                    zx = min(max(zx, ub[2] - hw), ub[0] + hw)
                tb = (LAY['logo_xy'][1] + self.logo_small.height + 8) / z     # dải logo trên cùng bị phủ giấy
                if ub[3] - ub[1] <= 2 * hh - tb:
                    zy = min(max(zy, ub[3] - hh), ub[1] + hh - tb)
                zx, zy = min(max(zx, hw), W - hw), min(max(zy, hh), H - hh)
        if first and FX.get('punch') and t < 0.6:          # phá nhịp giây đầu: bắt đầu sát rồi lùi ra nhanh
            zp = 1 + 0.14 * (1 - eo(clamp(t / 0.55)))
            if zp > 1.0005:
                ay = (TOP_AREA + BOTTOM_AREA) / 2
                z, zx, zy = z * zp, zx + (W / 2 - zx) * 0.6, zy + (ay - zy) * 0.6
                hw, hh = W / (2 * z), H / (2 * z)
                zx, zy = min(max(zx, hw), W - hw), min(max(zy, hh), H - hh)
        if z > 1.0005:                                   # camera phóng nhẹ (logo, nhãn, thanh tiến độ đứng yên)
            hw, hh = W / (2 * z), H / (2 * z)          # phép biến đổi lẻ điểm ảnh: không giật từng 1px
            f = f.transform((W, H), Image.AFFINE, (1 / z, 0, zx - hw, 0, 1 / z, zy - hh), resample=Image.BILINEAR)
            top = LAY['logo_xy'][1] + self.logo_small.height + 8
            f.paste(self.paper.crop((0, 0, W, top)), (0, 0))
        if not pl['logo_end']:
            lg = with_alpha(self.logo_small, eo(t / 0.4) if first else 1.0)
            f.paste(lg, LAY['logo_xy'], lg)
        if self.label is not None:
            f.paste(self.label, (W - LAY['label_r'] - self.label.width, LAY['label_y']), self.label)
        if prog is not None:
            d = ImageDraw.Draw(f)
            bx0, by0, bx1 = LAY['bar']
            d.rounded_rectangle((bx0, by0, bx1, by0 + 12), 6, fill=(232, 232, 228))
            d.rounded_rectangle((bx0, by0, bx0 + max(12, int((bx1 - bx0) * clamp(prog))), by0 + 12), 6, fill=ORANGE)
        if self.subs:
            self.draw_sub(f, pl, t)
        if not pl['last'] and not pl.get('keep_next') and t > pl['dur'] - TR:
            e = (t - (pl['dur'] - TR)) / TR
            if pl.get('trans') == 'lia':
                f = self.pan(f, pl, e, first, prog)
            else:
                self.erase(f, e)
        return f

    def pan(self, f, pl, e, first, prog):
        """Chuyển cảnh lia ngang: nội dung trượt sang trái, giấy và logo đứng yên."""
        dx = int(W * eio(clamp(e)))
        g = self.paper.copy()
        if dx < W:
            g.paste(f.crop((dx, 0, W, H)), (0, 0))
            g.paste(self.paper.crop((W - dx, 0, W, H)), (W - dx, 0))
        top = LAY['logo_xy'][1] + self.logo_small.height + 8
        g.paste(self.paper.crop((0, 0, W, top)), (0, 0))
        if not pl['logo_end']:
            g.paste(self.logo_small, LAY['logo_xy'], self.logo_small)
        if self.label is not None:
            g.paste(self.label, (W - LAY['label_r'] - self.label.width, LAY['label_y']), self.label)
        if prog is not None:
            d = ImageDraw.Draw(g)
            bx0, by0, bx1 = LAY['bar']
            g.paste(self.paper.crop((0, by0 - 4, W, by0 + 18)), (0, by0 - 4))
            d.rounded_rectangle((bx0, by0, bx1, by0 + 12), 6, fill=(232, 232, 228))
            d.rounded_rectangle((bx0, by0, bx0 + max(12, int((bx1 - bx0) * clamp(prog))), by0 + 12), 6, fill=ORANGE)
        return g


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
    thumbs = [r.frame(pl, pl['ed'] + EXIT + 0.05, False).resize((360, int(360 * H / W))) for pl in plans]
    cols = min(len(thumbs), 4)
    rows = math.ceil(len(thumbs) / cols)
    th_h = thumbs[0].height if thumbs else 640
    sheet = Image.new('RGB', (cols * 370 + 10, rows * (th_h + 10) + 10), (70, 70, 70))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (10 + (i % cols) * 370, 10 + (i // cols) * (th_h + 10)))
    sheet.save(out_png)
    return out_png


def preview_scenes(script_text, opts, out_dir):
    """Ảnh xem trước từng cảnh (khung hình cuối cảnh) + thông tin để sửa cảnh trên web."""
    os.makedirs(out_dir, exist_ok=True)
    simple = is_simple(script_text)
    scenes = parse_script(script_text)
    if opts.get('auto', True):
        auto_style(scenes)
    add_hotline(scenes, opts.get('hotline'))
    r = Renderer(opts.get('logo'), opts.get('label'), opts.get('bg', 'trang'), opts.get('subs', False),
                 opts.get('trans', 'xoa'), opts.get('hook', True))
    est = [max(1.5, len(' '.join(sc.get('say') or [])) * 0.075) for sc in scenes]
    plans = r.plan(scenes, est if opts.get('subs') else None, resolve_gender(opts))
    info = []
    for i, (sc, pl) in enumerate(zip(scenes, plans)):
        t = pl['ed'] + EXIT + 0.05
        subs_on, r.subs = r.subs, False
        fr = r.frame(pl, t, i == 0)
        r.subs = subs_on
        if pl.get('subs'):
            a0, b0, words, ws = pl['subs'][0]
            r.draw_sub(fr, pl, ws[len(ws) // 2][0])
        fr.convert('RGB').resize(LAY['thumb'], Image.LANCZOS).save(os.path.join(out_dir, 'c%02d.jpg' % i), quality=82)
        icon = next((tag_icon(tg) for _, tg in sc['lines'] if tag_icon(tg)), None)
        info.append({'i': i, 'src': sc.get('src') or [], 'icon': icon or '', 'say': ' '.join(sc.get('say') or [])})
    return {'simple': simple, 'scenes': info}


def _cover_image(scenes):
    """Hình kho đầu tiên trong video (ưu tiên cảnh mở đầu) để làm ảnh bìa."""
    for sc in scenes:
        for _, tg in sc.get('lines', []):
            n = tag_icon(tg)
            if n and kho_has(n):
                return kho_index()[norm(n)]
    if scenes:
        t = ' '.join(x for x, _ in scenes[0].get('lines', []))
        n = pick_icon(t, ' '.join(scenes[0].get('say') or []))
        if n and kho_has(n):
            return kho_index()[norm(n)]
    return None


def make_cover(scenes, opts, path):
    """Ảnh bìa: câu mở đầu chữ to đậm (từ khoá tô cam) + hình chính + logo. Cùng khổ với video."""
    if not scenes:
        return None
    raw = ' '.join(t for t, tg in scenes[0].get('lines', []) if t and not tag_icon(tg))
    raw = re.sub(r'\[[^\]]*\]', ' ', raw).replace(' / ', ' ').replace('||', ' ')
    raw = re.sub(r'\s+', ' ', raw).strip()
    if not raw:
        return None
    if '*' not in raw:                          # chưa đánh dấu từ khoá: tự tô số / từ khoá chính
        sp = key_spans(raw)
        for a0, b0, _ in reversed(sp[:2]):
            raw = raw[:a0] + '*' + raw[a0:b0] + '*' + raw[b0:]
    words, hot = [], False                      # (chữ, có phải từ khoá)
    for w in raw.split(' '):
        if not w:
            continue
        if w.startswith('*'):
            hot = True
        words.append((w.replace('*', ''), hot))
        if w.rstrip('?!.,:;').endswith('*'):
            hot = False
    im = make_paper(opts.get('bg', 'trang')).convert('RGBA')
    d = ImageDraw.Draw(im)
    wide = bool(LAY.get('wide'))
    pic_path = _cover_image(scenes)
    maxw = W * (0.5 if wide and pic_path else 0.88)
    area_h = (H * 0.62 if wide else H * 0.36) if pic_path else H * 0.6
    size = int(min(W, H) * (0.15 if not wide else 0.13))
    while True:                                  # ngắt dòng + giảm cỡ chữ cho vừa
        f = font(size); lines, cur = [], []
        for w in words:
            if cur and f.getlength(' '.join(x for x, _ in cur + [w])) > maxw:
                lines.append(cur); cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(cur)
        lh = line_h(size) * 0.98
        if (len(lines) <= 4 and len(lines) * lh <= area_h) or size <= 44:
            break
        size -= 4
    total_h = len(lines) * lh
    pic = None
    if pic_path:
        pic = Image.open(pic_path).convert('RGBA')
        bw, bh = (W * 0.4, H * 0.72) if wide else (W * 0.86, H * 0.86 - total_h - H * 0.16)
        k = min(bw / pic.width, bh / pic.height)
        pic = pic.resize((max(1, int(pic.width * k)), max(1, int(pic.height * k))), Image.LANCZOS) if k > 0 else None
    gap = H * 0.035
    logo_h = H * (0.1 if not wide else 0.14)
    if wide or not pic:
        ty = logo_h + max(0, (H - logo_h - total_h) / 2 - H * 0.03)
    else:                                         # khổ dọc: cụm chữ + hình nằm giữa
        grp = total_h + gap + pic.height
        ty = logo_h + max(0, (H - logo_h - grp) / 2)
    sw = max(2, size // 22)                       # nét chữ dày hơn cho dễ đọc khi thu nhỏ
    y = ty
    for ln in lines:
        lw = f.getlength(' '.join(x for x, _ in ln))
        x = W * 0.06 if (wide and pic) else (W - lw) / 2
        for j, (wd, hk) in enumerate(ln):
            ww = f.getlength(wd)
            if hk:                                # nền dạ quang cam nhạt sau từ khoá (liền mạch cả cụm)
                nxt = j + 1 < len(ln) and ln[j + 1][1]
                ex = f.getlength(wd + ' ') - ww if nxt else 0
                d.rounded_rectangle((x - size * 0.08, y + lh * 0.18, x + ww + ex + size * 0.08, y + lh * 0.92),
                                    radius=size // 6, fill=(255, 214, 150))
            col = (214, 72, 10) if hk else INK
            d.text((x, y), wd, font=f, fill=col, stroke_width=sw, stroke_fill=col)
            x += f.getlength(wd + ' ')
        y += lh
    if pic:
        if wide:
            px, py = W * 0.78 - pic.width / 2, H * 0.55 - pic.height / 2
        else:
            px, py = (W - pic.width) / 2, ty + total_h + gap
        im.alpha_composite(pic, (int(px), int(py)))
    if opts.get('logo'):
        try:
            lg = scaled(load_logo(opts['logo']), min(W, H) * 0.2)
            im.alpha_composite(lg, (int(W * 0.04), int(H * 0.02)))
        except Exception:
            pass
    im.convert('RGB').save(path, quality=90)
    return path


def render(script_text, opts, progress=lambda msg, frac: None):
    """opts: voice ('hoaimy'|'namminh'|'eleven'|'none'), rate, eleven_key, eleven_voice, eleven_model,
    music, music_vol (0-100), logo, out_path"""
    scenes = parse_script(script_text)
    if opts.get('auto', True):
        auto_style(scenes)
    add_hotline(scenes, opts.get('hotline'))
    if opts.get('cover_path'):
        try:
            make_cover(scenes, opts, opts['cover_path'])
        except Exception as e:
            print('Không tạo được ảnh bìa:', e)
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
                tts_eleven(apply_phat_am(say), opts.get('eleven_key'), opts.get('eleven_voice'), opts.get('eleven_model', ''), mp3)
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
        r = Renderer(opts.get('logo'), opts.get('label'), opts.get('bg', 'trang'), opts.get('subs', False),
                     opts.get('trans', 'xoa'), opts.get('hook', True), opts.get('cam', True))
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

        if opts.get('pen_sound', True):
            mix_into_wav(narr, sfx_track(plans, rate_hz, 0.018 * float(opts.get('pen_vol', 1.0))))
        if FX.get('sfx'):
            mix_into_wav(narr, fx_track(plans, rate_hz, float(opts.get('fx_vol', 1.0))), duck_amt=0.25)

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
