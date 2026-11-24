# -*- coding: utf-8 -*-
"""Nhập 1 lô hình lưới vào Kho.
Dùng: python tools/nhap_lo.py anh_luoi.png SO_HANG SO_COT danh_sach.txt [so_lo]
danh_sach.txt: mỗi dòng "ten_file.png | Tên hiển thị | từ khoá, từ khoá" theo thứ tự trái→phải, trên→dưới.
Dòng "-" = bỏ hình đó."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
import engine as E

src, rows, cols, lst = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
lo = int(sys.argv[5]) if len(sys.argv) > 5 else 0
items = []
for line in open(lst, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    parts = [x.strip() for x in line.split('|')]
    if parts[0] in ('-', 'bo', 'bỏ'):
        items.append(None); continue
    stem = os.path.splitext(parts[0])[0]
    items.append({'stem': stem, 'ten': parts[1] if len(parts) > 1 else stem.replace('_', ' '),
                  'tu_khoa': [k.strip() for k in (parts[2] if len(parts) > 2 else '').split(',') if k.strip()]})
names = [it['stem'] if it else '-' for it in items]
saved = E.kho_add_grid(src, rows, cols, names)
meta = E.kho_meta()
real = [it for it in items if it]
for it, path in zip(real, saved):
    key = os.path.splitext(os.path.basename(path))[0]
    meta[key] = {'ten': it['ten'], 'tu_khoa': it['tu_khoa'], **({'lo': lo} if lo else {})}
    print('OK', key, '|', it['ten'], '|', os.path.getsize(path) // 1024, 'KB')
json.dump(meta, open(E.KHO_TUKHOA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
