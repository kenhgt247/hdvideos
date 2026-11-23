# -*- coding: utf-8 -*-
"""Chạy VieNeu-TTS trong tiến trình riêng (nếu lỗi không làm tắt app)."""
import json, os, sys, traceback

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def say(*a):
    print(*a, flush=True)


def resolve_voice(tts, wanted):
    """Đổi tên hiển thị (vd '⭐ Hải Đăng — Nam · Bắc') thành tên giọng VieNeu nhận ('Hải Đăng')."""
    wanted = wanted.strip()
    try:
        items = list(tts.list_preset_voices())
    except Exception:
        return wanted
    pairs = []
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            pairs.append((str(it[0]), str(it[1])))
        else:
            pairs.append((str(it), str(it)))
    ids = [vid for _, vid in pairs]
    if wanted in ids:
        return wanted
    for label, vid in pairs:
        if wanted == label:
            return vid
    # tên ngắn nằm trong tên dài: chọn tên dài nhất khớp (tránh 'Adam' khớp nhầm 'Adam bựa')
    found = [vid for vid in ids if vid and vid in wanted]
    if found:
        return max(found, key=len)
    for label, vid in pairs:
        if label and (label in wanted or wanted in label):
            return vid
    return wanted


def pick_auto(tts, gender):
    """Chọn giọng có sẵn theo giới tính ('nam'/'nu'), ưu tiên giọng Bắc và giọng gắn sao."""
    try:
        items = list(tts.list_preset_voices())
    except Exception:
        return None
    best, score = None, -1
    for it in items:
        label = str(it[0] if isinstance(it, (list, tuple)) else it)
        tail = label.split('—')[-1].lower() if '—' in label else label.lower()
        words = tail.replace('·', ' ').replace('-', ' ').split()
        first = words[0] if words else ''   # sau dấu — là giới tính, rồi mới tới vùng miền
        is_nu = first in ('nữ', 'nu')
        is_nam = first == 'nam'
        if (gender == 'nu' and not is_nu) or (gender == 'nam' and not is_nam):
            continue
        sc = (2 if 'bắc' in words else 0) + (1 if '⭐' in label else 0)
        if sc > score:
            best, score = label, sc
    return best


def main():
    with open(sys.argv[1], encoding='utf-8') as fh:
        job = json.load(fh)
    try:
        from vieneu import Vieneu
    except Exception as e:
        sys.stderr.write('ERR_IMPORT %r\n' % e)
        sys.exit(3)
    say('STAGE load')
    try:
        tts = Vieneu(precision='fp32')   # CPU đời cũ: int8 có thể làm méo giọng
    except TypeError:
        tts = Vieneu()
    if job.get('list'):
        for item in tts.list_preset_voices():
            label = item[0] if isinstance(item, (list, tuple)) else item
            say('VOICE\t%s' % label)
        say('DONE')
        return
    try:
        for item in tts.list_preset_voices():
            label = item[0] if isinstance(item, (list, tuple)) else item
            say('VOICE\t%s' % label)
    except Exception:
        pass
    v = job.get('voice') or ''
    if v.startswith('auto:'):
        job['voice'] = pick_auto(tts, v[5:]) or None
        say('PICKED\t%s' % (job['voice'] or ''))
    kw = {}
    if job.get('ref_audio'):
        kw['ref_audio'] = job['ref_audio']
    elif job.get('voice'):
        kw['voice'] = resolve_voice(tts, job['voice'])
    n = len(job['texts'])
    for i, (text, out) in enumerate(zip(job['texts'], job['outs'])):
        say('STAGE say %d %d' % (i + 1, n))
        audio = tts.infer(text, **kw)
        tts.save(audio, out)
    say('DONE')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        sys.exit(2)
