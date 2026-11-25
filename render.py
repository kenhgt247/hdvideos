# -*- coding: utf-8 -*-
"""Dựng một video từ job.json (chạy trên máy GitHub Actions).

python render.py job.json out_dir
Kết quả: out_dir/video.mp4 và out_dir/info.json
"""
import json, os, re, sys, time, traceback, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'engine'))
import engine as E  # noqa: E402


def slug(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'D')
    s = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')
    return (s or 'video')[:60]


def log(msg, frac=None):
    pct = '' if frac is None else ' (%d%%)' % int(frac * 100)
    print('>> %s%s' % (msg, pct), flush=True)


def main():
    job_file, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    with open(job_file, encoding='utf-8') as fh:
        job = json.load(fh)
    name = (job.get('name') or '').strip() or 'Video %s' % time.strftime('%d-%m %H:%M')
    info = {'ok': False, 'name': name, 'file': slug(name) + '.mp4', 'created': int(time.time()),
            'by': job.get('by', ''), 'script': job.get('script', '')[:3000],
            'tpl': job.get('tpl', ''), 'ab': job.get('ab', ''), 'abg': job.get('abg', ''), 'batch': job.get('batch', '')}

    voice = job.get('voice') or 'vieneu_nam'
    character = job.get('character') or 'auto'
    opts = {'rate': int(job.get('rate') or 0), 'auto': bool(job.get('auto', True)),
            'label': (job.get('label') or '').strip() or None,
            'hotline': (job.get('hotline') or '').strip() or None,
            'logo': os.path.join(HERE, 'engine', 'assets', 'logo.png'),
            'out_path': os.path.join(out_dir, 'video.mp4'), 'cover_path': os.path.join(out_dir, 'bia.jpg')}
    if not job.get('logo', True):
        opts['logo'] = None
    E.STROKE = job.get('stroke', True) is not False
    E.REVEAL = job.get('reveal') if job.get('reveal') in ('quet', 'loang') else 'net'
    E.CharItem._cache.clear()
    fmt = job.get('fmt') or 'doc'
    E.set_format(fmt if fmt in E.FORMATS else 'doc')
    info['fmt'] = fmt
    bg = job.get('bg') or 'trang'
    opts['bg'] = bg if bg in dict(E.BG_STYLES) else 'trang'
    opts['subs'] = bool(job.get('subs', False))
    tr = job.get('trans') or 'xoa'
    opts['trans'] = tr if tr in ('xoa', 'lia', 'xen') else 'xoa'
    opts['hook'] = job.get('hook', True) is not False
    opts['cam'] = job.get('cam', True) is not False
    pen = job.get('pen', 1)
    pen = {True: 1.0, False: 0.0}.get(pen, pen)
    try:
        pen = max(0.0, min(3.0, float(pen)))
    except (TypeError, ValueError):
        pen = 1.0
    opts['pen_sound'] = pen > 0
    opts['pen_vol'] = pen
    music = os.path.basename(job.get('music') or '')
    if music and os.path.exists(os.path.join(HERE, 'engine', 'assets', 'nhac', music)):
        opts['music'] = os.path.join(HERE, 'engine', 'assets', 'nhac', music)
        opts['music_vol'] = max(0, min(40, int(job.get('music_vol') or 12)))
        info['music'] = music
        try:
            meta = json.load(open(os.path.join(HERE, 'engine', 'assets', 'nhac', '_danh_sach.json'), encoding='utf-8')).get(music, {})
            if str(meta.get('mo_ta', '')).startswith('Nhạc:'):
                info['credit'] = meta['mo_ta']
        except Exception:
            pass
    clone = os.path.basename(job.get('clone') or '')
    clone_src = os.path.join(HERE, 'engine', 'assets', 'giong', clone) if clone else ''

    who = re.sub(r'[^a-z0-9_]', '', job.get('who') or '')
    if who and os.path.isdir(os.path.join(HERE, 'engine', 'assets', 'nhanvat_rieng', who)):
        E.CHAR_OVERRIDE = os.path.join(HERE, 'engine', 'assets', 'nhanvat_rieng', who)
    gender = 'chi' if voice in ('vieneu_nu', 'hoaimy') else 'anh'
    if voice.startswith('vieneu') and job.get('vieneu_voice'):
        lab = E.norm(job['vieneu_voice'])
        tail = lab.split('—')[-1] if '—' in lab else lab
        if tail.replace('·', ' ').split()[:1] == ['nu']:
            gender = 'chi'
    if voice == 'clone' and re.search(r'(^|_)(chi|nu|co|nu_)', os.path.splitext(clone)[0]):
        gender = 'chi'
    opts['character'] = gender if character == 'auto' else character

    if voice == 'clone' and clone_src and os.path.exists(clone_src):
        ref = os.path.join(out_dir, 'giong_mau.wav')
        E.run_ff(['-i', clone_src, '-ac', '1', '-ar', '24000', '-t', '20', ref])
        opts['voice'] = 'vieneu'
        opts['vieneu_ref'] = ref
        info['clone'] = clone
    elif voice.startswith('vieneu'):
        opts['voice'] = 'vieneu'
        opts['vieneu_voice'] = job.get('vieneu_voice') or ('auto:nu' if voice == 'vieneu_nu' else 'auto:nam')
    else:
        opts['voice'] = voice if voice in ('namminh', 'hoaimy', 'none') else 'namminh'

    t0 = time.time()
    if job.get('preview'):
        try:
            data = E.preview_scenes(job.get('script', ''), opts, out_dir)
            info.update(ok=True, preview=True, **data)
        except E.VideoError as e:
            info['error'] = str(e)
        except Exception as e:
            info['error'] = 'Lỗi khi xem trước: %s' % e
            traceback.print_exc()
        with open(os.path.join(out_dir, 'info.json'), 'w', encoding='utf-8') as fh:
            json.dump(info, fh, ensure_ascii=False)
        print('preview', info.get('ok'), len(info.get('scenes', [])))
        return
    try:
        try:
            E.render(job.get('script', ''), opts, log)
            used = opts['voice']
        except Exception as e:
            if opts['voice'] != 'vieneu':
                raise
            # VieNeu lỗi -> dùng giọng Microsoft để vẫn ra video
            info['fallback'] = 'VieNeu lỗi, đã dùng giọng Microsoft thay thế: %s' % str(e)[-300:]
            log(info['fallback'])
            opts['voice'] = 'hoaimy' if gender == 'chi' else 'namminh'
            E.render(job.get('script', ''), opts, log)
            used = opts['voice']
        if used == 'vieneu' and opts.get('vieneu_ref'):
            info['voice'] = 'Giọng nhân bản: ' + os.path.splitext(clone)[0].replace('_', ' ')
        elif used == 'vieneu':
            info['voice'] = 'VieNeu: ' + (E.LAST_VIENEU.get('picked') or opts.get('vieneu_voice') or '')
        else:
            info['voice'] = {'namminh': 'Microsoft Nam Minh', 'hoaimy': 'Microsoft Hoài My'}.get(used, used)
        if E.LAST_VIENEU.get('voices'):
            info['voices'] = E.LAST_VIENEU['voices']
        info['ok'] = True
        try:
            from posts import make_posts
            info['posts'] = make_posts(job.get('script', ''), name, job.get('hotline', ''), info.get('credit', ''), info.get('fmt', 'doc'))
        except Exception as e:
            print('Không soạn được bài đăng:', e)
        info['seconds'] = int(time.time() - t0)
        info['size'] = os.path.getsize(opts['out_path'])
    except E.VideoError as e:
        info['error'] = str(e)
    except Exception as e:
        info['error'] = 'Lỗi khi dựng video: %s' % e
        traceback.print_exc()
    try:   # câu không có hình hợp trong Kho -> trang web gom lại thành danh sách 'hình còn thiếu'
        seen, miss = set(), []
        for t in E.MISSING:
            t = ' '.join(str(t).replace('*', '').split())[:80]
            if t and t.lower() not in seen:
                seen.add(t.lower()); miss.append(t)
        if miss:
            info['thieu_hinh'] = miss[:30]
    except Exception:
        pass
    if E.LAST_VIENEU.get('voices') and 'voices' not in info:
        info['voices'] = E.LAST_VIENEU['voices']
    with open(os.path.join(out_dir, 'info.json'), 'w', encoding='utf-8') as fh:
        json.dump(info, fh, ensure_ascii=False)
    print(json.dumps({k: v for k, v in info.items() if k not in ('script', 'voices')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
