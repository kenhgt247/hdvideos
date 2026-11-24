# -*- coding: utf-8 -*-
"""Vẽ từng nét như người thật: dò xương nét (skeleton) của ảnh/chữ, tách thành các nét liền,
sắp thứ tự như người vẽ, rồi tính "thời điểm hiện ra" cho từng điểm ảnh của nét."""
import numpy as np

try:
    from scipy import ndimage
    from skimage.morphology import skeletonize
    OK = True
except Exception:          # thiếu thư viện -> dùng kiểu quét cũ
    OK = False

NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _trace(skel):
    """Tách xương nét thành danh sách các nét (mỗi nét là list (y, x))."""
    ys, xs = np.nonzero(skel)
    pts = set(zip(ys.tolist(), xs.tolist()))
    if not pts:
        return []
    deg = {}
    for (y, x) in pts:
        deg[(y, x)] = sum((y + dy, x + dx) in pts for dy, dx in NB)
    seen = set()
    strokes = []

    def walk(start):
        path = [start]
        seen.add(start)
        cur = start
        while True:
            nxt = None
            # ưu tiên hàng xóm thẳng (4 hướng) để nét mượt
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                q = (cur[0] + dy, cur[1] + dx)
                if q in pts and q not in seen:
                    nxt = q
                    break
            if nxt is None:
                return path
            seen.add(nxt)
            path.append(nxt)
            cur = nxt
            if deg.get(cur, 0) >= 3:        # tới ngã ba: kết thúc nét, các nhánh vẽ sau
                return path

    ends = sorted([p for p in pts if deg[p] <= 1])
    for p in ends:
        if p not in seen:
            strokes.append(walk(p))
    # còn lại: nhánh từ ngã ba, vòng kín
    changed = True
    while changed:
        changed = False
        for p in sorted(pts - seen):
            if p in seen:
                continue
            strokes.append(walk(p))
            changed = True
    return strokes


def _order(strokes, mode, unit):
    """Sắp thứ tự nét: 'img' = gần nhau nhất bắt đầu từ trên-trái; 'text' = trái sang phải."""
    if not strokes:
        return []
    rest = list(range(len(strokes)))
    if mode == 'text':
        band = max(8.0, unit * 0.45)
        rest.sort(key=lambda i: (int(min(x for _, x in strokes[i]) / band), min(y for y, _ in strokes[i])))
        out, pen = [], None
        while rest:
            # trong cửa sổ vài nét kế tiếp theo chiều trái->phải, chọn nét gần bút nhất
            win = rest[:6]
            if pen is None:
                k = win[0]
            else:
                def cost(i):
                    s = strokes[i]
                    d0 = (s[0][0] - pen[0]) ** 2 + (s[0][1] - pen[1]) ** 2
                    d1 = (s[-1][0] - pen[0]) ** 2 + (s[-1][1] - pen[1]) ** 2
                    return min(d0, d1)
                k = min(win, key=cost)
            s = strokes[k]
            if pen is not None and ((s[-1][0] - pen[0]) ** 2 + (s[-1][1] - pen[1]) ** 2) < \
                    ((s[0][0] - pen[0]) ** 2 + (s[0][1] - pen[1]) ** 2):
                s = s[::-1]
            out.append(s)
            pen = s[-1]
            rest.remove(k)
        return out
    # ảnh: nét dài trước một chút, bắt đầu từ trên-trái, sau đó nét gần nhất
    start = min(rest, key=lambda i: strokes[i][0][0] * 2 + strokes[i][0][1])
    out, pen = [], None
    cur = start
    while True:
        s = strokes[cur]
        if pen is not None:
            d0 = (s[0][0] - pen[0]) ** 2 + (s[0][1] - pen[1]) ** 2
            d1 = (s[-1][0] - pen[0]) ** 2 + (s[-1][1] - pen[1]) ** 2
            if d1 < d0:
                s = s[::-1]
        out.append(s)
        pen = s[-1]
        rest.remove(cur)
        if not rest:
            break
        def cost(i):
            t = strokes[i]
            d = min((t[0][0] - pen[0]) ** 2 + (t[0][1] - pen[1]) ** 2, (t[-1][0] - pen[0]) ** 2 + (t[-1][1] - pen[1]) ** 2)
            return d ** 0.5 - min(len(t), 60) * 0.6
        cur = min(rest, key=cost)
    return out


def plan(mask, mode='img', unit=40, min_len=3, max_side=900):
    """mask: mảng bool (nét cần vẽ). Trả về (reveal, pen) hoặc None:
    reveal: float32 cùng cỡ mask, thời điểm 0..1 mỗi điểm ảnh hiện ra (vô cực = không phải nét)
    pen: mảng (N, 3) [t, x, y] vị trí đầu bút theo thời gian."""
    if not OK or mask is None or not mask.any():
        return None
    h0, w0 = mask.shape
    k = min(1.0, max_side / max(h0, w0))
    m = mask
    if k < 1.0:                      # ảnh lớn: dò nét trên bản thu nhỏ cho nhanh
        from PIL import Image
        m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((max(1, int(w0 * k)), max(1, int(h0 * k))))) > 127
    skel = skeletonize(m)
    strokes = [s for s in _trace(skel) if len(s) >= min_len] or _trace(skel)
    if not strokes:
        return None
    strokes = _order(strokes, mode, unit * k)
    lens = [len(s) for s in strokes]
    jump = [0.0] + [((strokes[i][0][0] - strokes[i - 1][-1][0]) ** 2 + (strokes[i][0][1] - strokes[i - 1][-1][1]) ** 2) ** 0.5
                    for i in range(1, len(strokes))]
    # thời gian: vẽ nét theo độ dài; nhấc bút giữa các nét tốn ít thời gian (theo khoảng cách, có giới hạn)
    lift = [min(j * 0.25, 25.0) for j in jump]
    total = sum(lens) + sum(lift)
    tmap = np.full(m.shape, np.inf, dtype=np.float32)
    pen = []
    t = 0.0
    for s, lf in zip(strokes, lift):
        t += lf
        arr = np.array(s)
        ts = (t + np.arange(len(s))) / total
        tmap[arr[:, 0], arr[:, 1]] = ts
        step = max(1, len(s) // 12)
        for j in range(0, len(s), step):
            pen.append((ts[j], s[j][1] / k, s[j][0] / k))
        pen.append((ts[-1], s[-1][1] / k, s[-1][0] / k))
        t += len(s)
    # mỗi điểm ảnh của nét lấy thời điểm của điểm xương gần nhất
    _, (iy, ix) = ndimage.distance_transform_edt(~np.isfinite(tmap), return_indices=True)
    rev_small = tmap[iy, ix]
    if k < 1.0:
        from PIL import Image
        rev = np.asarray(Image.fromarray(rev_small).resize((w0, h0), Image.NEAREST))
    else:
        rev = rev_small
    rev = np.where(mask, rev, np.inf).astype(np.float32)
    return rev, np.array(sorted(pen), dtype=np.float32)


def pen_at(pen, p):
    """Vị trí đầu bút tại tiến độ p (0..1)."""
    if pen is None or len(pen) == 0:
        return None
    i = int(np.searchsorted(pen[:, 0], p))
    if i <= 0:
        return float(pen[0, 1]), float(pen[0, 2])
    if i >= len(pen):
        return float(pen[-1, 1]), float(pen[-1, 2])
    a, b = pen[i - 1], pen[i]
    u = 0.0 if b[0] <= a[0] else (p - a[0]) / (b[0] - a[0])
    return float(a[1] + (b[1] - a[1]) * u), float(a[2] + (b[2] - a[2]) * u)


def brush(arr, mask, band=None, max_groups=6, seed=3):
    """Tô màu như cầm cọ: chia ảnh theo nhóm màu, tô xong nhóm này mới sang nhóm khác,
    trong mỗi nhóm cọ quét qua lại theo từng dải (mép dải lượn sóng cho giống nét cọ).
    Trả về (reveal HxW float32 trong 0..1, pen Nx3 [t, x, y]) hoặc None."""
    H, W = mask.shape
    white = mask & (arr[:, :, :3].min(axis=2) > 222)      # mảng trắng trên giấy trắng: hiện luôn, khỏi tô
    mask = mask & ~white
    ys, xs = np.nonzero(mask)
    if len(ys) < 50:
        return None
    band = band or max(10, int(min(H, W) / 11))
    cols = arr[ys, xs, :3].astype(np.int32)
    key = (cols[:, 0] // 64) * 16 + (cols[:, 1] // 64) * 4 + (cols[:, 2] // 64)
    uniq, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    big = [i for i in np.argsort(-cnt) if cnt[i] >= 0.03 * len(ys)][:max_groups] or [int(np.argmax(cnt))]
    means = np.array([cols[inv == i].mean(axis=0) for i in big])
    d = ((cols[:, None, :] - means[None, :, :]) ** 2).sum(axis=2)
    grp = np.argmin(d, axis=1)                           # mỗi điểm ảnh thuộc 1 nhóm màu lớn
    # thứ tự nhóm: mảng lớn trước, chi tiết nhỏ sau
    sizes = np.bincount(grp, minlength=len(big)).astype(np.float64)
    order = list(np.argsort(-sizes))
    weights = np.maximum(sizes / sizes.sum(), 0.08)
    weights = weights / weights[order].sum()
    rng = np.random.RandomState(seed)
    reveal = np.full((H, W), 2.0, np.float32)
    pen, t0 = [], 0.0
    for g in order:
        sel = grp == g
        gy, gx = ys[sel], xs[sel]
        if len(gy) == 0:
            continue
        ph = rng.rand() * 6.28
        wav = band * 0.35 * np.sin(gx / (band * 2.3) * 6.28 + ph)
        b = np.floor((gy + wav) / band).astype(np.int32)
        bands = np.unique(b)
        rank = np.searchsorted(bands, b)
        nb = len(bands)
        bmin = np.full(nb, W, np.int32); bmax = np.zeros(nb, np.int32)
        np.minimum.at(bmin, rank, gx); np.maximum.at(bmax, rank, gx)
        span = np.maximum(1, bmax - bmin)
        xf = (gx - bmin[rank]) / span[rank]
        xf = np.where(rank % 2 == 0, xf, 1 - xf)          # đi qua rồi đi lại
        wg = float(weights[g])
        reveal[gy, gx] = t0 + wg * (rank + xf) / nb
        for k in range(nb):
            yc = (bands[k] + 0.5) * band
            xa, xb = (bmin[k], bmax[k]) if k % 2 == 0 else (bmax[k], bmin[k])
            steps = max(2, int(abs(xb - xa) / (band * 0.8)))
            for s in range(steps + 1):
                u = s / steps
                zig = band * 0.38 * (1 if s % 2 else -1)
                pen.append((t0 + wg * (k + u) / nb, xa + (xb - xa) * u, yc + zig))
        t0 += wg
    reveal = np.minimum(reveal, 1.0)
    reveal[~mask] = 0.0                                    # gồm cả mảng trắng
    pen = np.array(pen, np.float32)
    pen = pen[np.argsort(pen[:, 0], kind='stable')]
    return reveal.astype(np.float32), pen
