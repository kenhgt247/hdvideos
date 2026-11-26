# -*- coding: utf-8 -*-
"""Xử lý ảnh nhân viên tải lên qua web: tách nền rồi đưa vào Kho hình / Nhân vật.

engine/assets/kho_moi/<tên>.<đuôi>        -> engine/assets/kho/<tên>.png
engine/assets/nhanvat_moi/<anh|chi>_<chao|chi|like>.<đuôi> -> engine/assets/nhanvat/...
engine/assets/nhanvat_moi/_khoi_phuc      -> khôi phục nhân vật gốc
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'engine'))
import engine as E  # noqa: E402

IMG = ('.png', '.jpg', '.jpeg', '.webp')


def main():
    kho_moi = os.path.join(E.ASSETS, 'kho_moi')
    nv_moi = os.path.join(E.ASSETS, 'nhanvat_moi')
    n = 0
    for f in sorted(os.listdir(kho_moi)) if os.path.isdir(kho_moi) else []:
        src = os.path.join(kho_moi, f)
        base, ext = os.path.splitext(f)
        if ext.lower() not in IMG:
            continue
        folder = E.KHO_DIR
        if '__' in base and base.split('__', 1)[0].startswith('kho_'):   # ảnh của lĩnh vực khác: kho_ngoi__ten.png
            sub, base = base.split('__', 1)
            folder = os.path.join(E.ASSETS, re.sub(r'[^a-z0-9_]', '', sub))
        old = os.path.join(folder, base + '.png')
        if os.path.exists(old):          # tải lại cùng tên = thay ảnh cũ
            os.remove(old)
        try:
            print('Kho:', f, '->', E.kho_add(src, base.replace('_', ' '), folder))
            n += 1
        except Exception as e:
            print('Bỏ qua', f, e)
        os.remove(src)
    for f in sorted(os.listdir(nv_moi)) if os.path.isdir(nv_moi) else []:
        src = os.path.join(nv_moi, f)
        base, ext = os.path.splitext(f)
        if f == '_khoi_phuc':
            print('Khôi phục nhân vật gốc:', E.restore_characters())
            os.remove(src)
            n += 1
            continue
        if ext.lower() not in IMG:
            continue
        if '__' in base:                       # nhân vật riêng: <người>__<anh|chi>_<tư thế>
            who, rest = base.split('__', 1)
            parts = rest.split('_')
            if who.startswith('lv_') and len(parts) == 2 and parts[0] in dict(E.GENDERS) and parts[1] in dict(E.POSES):
                dst_dir = os.path.join(E.ASSETS, 'lv', re.sub(r'[^a-z0-9]', '', who[3:]), 'nhanvat')
                os.makedirs(dst_dir, exist_ok=True)
                E.remove_bg(src).save(os.path.join(dst_dir, rest + '.png'))
                print('Nhân vật lĩnh vực:', who, rest)
                n += 1
                os.remove(src)
                continue
            if who and len(parts) == 2 and parts[0] in dict(E.GENDERS) and parts[1] in dict(E.POSES):
                dst_dir = os.path.join(E.ASSETS, 'nhanvat_rieng', who)
                os.makedirs(dst_dir, exist_ok=True)
                E.remove_bg(src).save(os.path.join(dst_dir, rest + '.png'))
                print('Nhân vật riêng:', who, rest)
                n += 1
            os.remove(src)
            continue
        parts = base.split('_')
        if len(parts) == 2 and parts[0] in dict(E.GENDERS) and parts[1] in dict(E.POSES):
            try:
                print('Nhân vật:', f, '->', E.set_character_image(parts[0], parts[1], src))
                n += 1
            except Exception as e:
                print('Bỏ qua', f, e)
        os.remove(src)
    print('Đã xử lý', n, 'ảnh')


if __name__ == '__main__':
    main()
