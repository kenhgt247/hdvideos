# -*- coding: utf-8 -*-
"""Soạn sẵn bài đăng Facebook / TikTok / YouTube từ kịch bản video."""
import re, unicodedata


def _norm(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.replace('đ', 'd').replace('Đ', 'D').lower()


def _clean(t):
    t = re.sub(r'\[[^\]]*\]', '', t or '')          # bỏ [vẽ: ...], [đỏ]...
    t = t.replace('*', '')
    t = re.sub(r'\s+/\s+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip(' -–•')


def _sentence(t):
    t = t.strip()
    if t and t[-1] not in '.!?…:':
        t += '.'
    return t[:1].upper() + t[1:]


TAGS = [
    (('han quoc', ' han ', 'topik', 'tieng han', 'd4', 'd2'), ['#duhochanquoc', '#hanquoc']),
    (('dai loan',), ['#duhocdailoan', '#dailoan']),
    (('visa',), ['#visaduhoc']),
    (('hoc bong',), ['#hocbong']),
    (('lam them', 'vua hoc vua lam'), ['#vuahocvualam']),
    (('chi phi', 'hoc phi'), ['#chiphiduhoc']),
    (('tieng han', 'topik'), ['#tienghan']),
    (('tieng trung', 'tocfl'), ['#tiengtrung']),
    (('tuyen sinh', 'ky thang'), ['#tuyensinh']),
    (('ho so',), ['#hosoduhoc']),
    (('chon truong', 'chon nganh'), ['#chontruong', '#huongnghiep']),
    (('phu huynh',), ['#phuhuynh']),
]


def make_posts(script, name='', hotline='', credit=''):
    lines = [l.rstrip() for l in (script or '').replace('\r', '').split('\n') if l.strip()]
    lines = [l for l in lines if not l.strip().startswith('===') and not l.lower().startswith('đọc:')]
    rows = []
    for l in lines:
        bullet = l.lstrip().startswith('- ')
        body = l.lstrip()[2:] if bullet else l
        scr, _, say = body.partition('||')
        rows.append({'bullet': bullet, 'screen': _clean(scr), 'say': _clean(say) or _clean(scr)})
    if not rows:
        return {}
    hook = rows[0]['say'] or rows[0]['screen']
    cta = rows[-1]['say'] if len(rows) > 1 else ''
    points = []                     # (kiểu, chữ): kiểu 'pt' = ý chính, 'lead' = câu dẫn, 'sub' = gạch đầu dòng
    mid = rows[1:-1] if len(rows) > 2 else []
    for i, r in enumerate(mid):
        if r['bullet']:
            t = r['screen'].rstrip(':').strip()
            if t:
                points.append(('sub', t))
            continue
        nxt_bullet = i + 1 < len(mid) and mid[i + 1]['bullet']
        if nxt_bullet or r['screen'].endswith(':'):
            points.append(('lead', (r['say'] or r['screen']).rstrip(':').strip()))
        else:
            points.append(('pt', r['say'] or r['screen']))
    points = points[:10]
    full = ' ' + _norm(script) + ' '
    tags = ['#duhochaiduong']
    for keys, tg in TAGS:
        if any(k in full for k in keys):
            tags += [t for t in tg if t not in tags]
    tags += ['#duhoc', '#tuvanduhoc']
    hl = ('📞 Hotline/Zalo: ' + hotline.strip()) if (hotline or '').strip() else '📩 Inbox fanpage để được tư vấn miễn phí'
    if not (hotline or '').strip() and 'inbox' in _norm(cta):
        hl = ''
    cr = ('\n\n🎵 ' + credit) if credit else ''

    fb = '🔥 ' + _sentence(hook) + '\n\n'
    def fmt(sym_pt, sym_lead, sym_sub):
        out = []
        for k, t in points:
            if k == 'sub':
                out.append('   ' + sym_sub + ' ' + t[:1].upper() + t[1:])
            else:
                out.append((sym_lead if k == 'lead' else sym_pt) + ' ' + (_sentence(t) if k == 'pt' else t[:1].upper() + t[1:] + ':'))
        return '\n'.join(out)
    if points:
        fb += fmt('✅', '📌', '▫️') + '\n\n'
    if cta:
        fb += '👉 ' + _sentence(cta) + '\n'
    fb += (hl + '\n' if hl else '') + '🏫 Du Học Hải Dương – Định Hướng Tương Lai' + cr + '\n\n' + ' '.join(tags)

    tt_tags = tags[:6] + ['#xuhuong', '#learnontiktok']
    tt = _sentence(hook) + ' 👇'
    if cta:
        tt += '\n👉 ' + _sentence(cta)
    tt += cr.replace('\n\n', '\n') + '\n' + ' '.join(tt_tags)

    title = (name or hook).strip()
    if len(title) > 90:
        title = title[:87].rsplit(' ', 1)[0] + '…'
    yt_desc = _sentence(hook) + '\n\n'
    if points:
        yt_desc += fmt('•', '•', '-') + '\n\n'
    yt_desc += (('👉 ' + _sentence(cta) + '\n') if cta else '') + (hl + '\n' if hl else '') + 'Du Học Hải Dương – Định Hướng Tương Lai' + cr + '\n\n' + ' '.join(tags[:8]) + ' #shorts'
    return {'facebook': fb, 'tiktok': tt, 'youtube_title': title + ' #shorts', 'youtube': yt_desc}
