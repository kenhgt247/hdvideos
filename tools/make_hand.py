"""Chuẩn bị ảnh bàn tay cho video: nối dài ống tay áo (để tay luôn kéo ra ngoài màn hình),
tìm đầu ngòi bút (điểm xa nhất bên trái), lưu PNG + JSON.
Dùng: python tools/make_hand.py anh_tay.png engine/assets/hand.png"""
import json, sys
import numpy as np
from PIL import Image, ImageFilter


def make_hand(src, dst, ext=1000):
    im = Image.open(src).convert('RGBA')
    a = np.asarray(im).astype(np.float32)
    H, W = a.shape[:2]
    al = a[:, :, 3]
    if al.min() > 250:                                   # nền trắng -> trong suốt
        rgb = a[:, :, :3]
        al = np.where(rgb.min(axis=2) > 245, 0, 255).astype(np.float32)
        a[:, :, 3] = al
    ys, xs = np.nonzero(al > 128)
    i = np.argmin(xs)
    tip = (float(xs[i]), float(np.median(ys[xs <= xs[i] + 3])))

    def edges(r):
        x = np.nonzero(al[r] > 128)[0]
        return (x.min(), x.max()) if len(x) else (None, None)
    ref = next(r for r in range(H - 1, 0, -1) if edges(r)[1] is not None and edges(r)[1] < W - 3)
    l_ref, r_ref = edges(ref)
    width = r_ref - l_ref + 1
    lb, _ = edges(H - 1)
    slope = (lb - l_ref) / max(1, (H - 1 - ref))
    prof = np.zeros((width, 4), np.float32)
    for r in range(ref - 30, ref):
        l, rr = edges(r)
        seg = a[r, l:rr + 1]
        prof += seg[np.round(np.linspace(0, len(seg) - 1, width)).astype(int)]
    prof /= 30
    prof[:, 3] = 255
    out = np.zeros((H + ext, int(lb + ext * slope + width + 20), 4), np.float32)
    out[:H, :W] = a
    rng = np.random.default_rng(1)
    for y in range(ref, H + ext):
        xi = np.arange(width) + int(np.floor(l_ref + (y - ref) * slope))
        ok = (xi >= 0) & (xi < out.shape[1])
        row = prof.copy()
        row[:, :3] += rng.normal(0, 1.2, (width, 1))
        if y < H:
            keep = out[y, xi[ok], 3] > 128
            out[y, xi[ok][~keep]] = row[ok][~keep]
        else:
            out[y, xi[ok]] = row[ok]
    res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    r_, g_, b_, a_ = res.split()
    res = Image.merge('RGBA', (r_, g_, b_, a_.filter(ImageFilter.GaussianBlur(0.8))))
    bb = res.getbbox()
    res = res.crop(bb)
    tip = [round(tip[0] - bb[0], 1), round(tip[1] - bb[1], 1)]
    res.save(dst, optimize=True)
    json.dump({'tip': tip}, open(dst[:-4] + '.json', 'w'))
    return res.size, tip


if __name__ == '__main__':
    print(make_hand(sys.argv[1], sys.argv[2]))
