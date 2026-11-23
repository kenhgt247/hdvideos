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
            'by': job.get('by', ''), 'script': job.get('script', '')[:3000]}

    voice = job.get('voice') or 'vieneu_nam'
    character = job.get('character') or 'auto'
    opts = {'rate': int(job.get('rate') or 0), 'auto': bool(job.get('auto', True)),
            'label': (job.get('label') or '').strip() or None,
            'hotline': (job.get('hotline') or '').strip() or None,
            'logo': os.path.join(HERE, 'engine', 'assets', 'logo.png'),
            'out_path': os.path.join(out_dir, 'video.mp4')}
    if not job.get('logo', True):
        opts['logo'] = None

    gender = 'chi' if voice in ('vieneu_nu', 'hoaimy') else 'anh'
    if voice.startswith('vieneu') and job.get('vieneu_voice'):
        lab = E.norm(job['vieneu_voice'])
        tail = lab.split('—')[-1] if '—' in lab else lab
        if tail.replace('·', ' ').split()[:1] == ['nu']:
            gender = 'chi'
    opts['character'] = gender if character == 'auto' else character

    if voice.startswith('vieneu'):
        opts['voice'] = 'vieneu'
        opts['vieneu_voice'] = job.get('vieneu_voice') or ('auto:nu' if voice == 'vieneu_nu' else 'auto:nam')
    else:
        opts['voice'] = voice if voice in ('namminh', 'hoaimy', 'none') else 'namminh'

    t0 = time.time()
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
        if used == 'vieneu':
            info['voice'] = 'VieNeu: ' + (E.LAST_VIENEU.get('picked') or opts.get('vieneu_voice') or '')
        else:
            info['voice'] = {'namminh': 'Microsoft Nam Minh', 'hoaimy': 'Microsoft Hoài My'}.get(used, used)
        if E.LAST_VIENEU.get('voices'):
            info['voices'] = E.LAST_VIENEU['voices']
        info['ok'] = True
        info['seconds'] = int(time.time() - t0)
        info['size'] = os.path.getsize(opts['out_path'])
    except E.VideoError as e:
        info['error'] = str(e)
    except Exception as e:
        info['error'] = 'Lỗi khi dựng video: %s' % e
        traceback.print_exc()
    if E.LAST_VIENEU.get('voices') and 'voices' not in info:
        info['voices'] = E.LAST_VIENEU['voices']
    with open(os.path.join(out_dir, 'info.json'), 'w', encoding='utf-8') as fh:
        json.dump(info, fh, ensure_ascii=False)
    print(json.dumps({k: v for k, v in info.items() if k not in ('script', 'voices')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
