# -*- coding: utf-8 -*-
"""Bộ ghép hình vẽ tay: nhân vật nhiều tư thế + đồ vật + các cảnh du học.
Toạ độ trong khung cảnh: x từ -300 đến 300, y từ -200 đến 200 (y hướng xuống)."""
import math
import numpy as np

E = None  # module engine (gán khi engine nạp)

INK = (34, 36, 48); BLUE = (32, 70, 170); RED = (214, 38, 50); ORANGE = (238, 128, 20)
GREEN = (30, 140, 70); GREY = (100, 104, 118); BROWN = (120, 80, 40); PURPLE = (130, 60, 170)
YEL = (220, 170, 20); TEAL = (20, 130, 140)
SKIN = (253, 228, 205); HAIR = (60, 48, 42)
LB = (205, 220, 248); LR = (250, 210, 210); LO = (253, 225, 180); LG = (205, 235, 210)
LY = (253, 240, 170); LGR = (232, 232, 232); LP = (230, 212, 242); WHITE = (255, 255, 255); LT = (200, 235, 235)


class Pen:
    def __init__(self, cx, cy, s, seed):
        self.cx, self.cy, self.s, self.seed = cx, cy, s, seed
        self.items = []

    def P(self, x, y):
        return (self.cx + x * self.s, self.cy + y * self.s)

    def _sd(self):
        self.seed += 3
        return self.seed

    def w(self, w):
        return max(2.0, (w if w else 6.5) * self.s + 1.5)

    def L(self, pts, c=INK, w=None, bow=3):
        self.items.append(E.Path(E.poly([self.P(*p) for p in pts], seed=self._sd(), bow=bow * self.s), c, self.w(w)))

    def fill(self, pts, fc):
        if fc:
            self.items.append(E.Fill([self.P(*p) for p in pts], fc, 0.55))

    def PG(self, pts, c=INK, fill=None, w=None, bow=3):
        self.fill(pts, fill)
        self.L(list(pts) + [pts[0]], c, w, bow)

    def R(self, x0, y0, x1, y1, c=INK, fill=None, w=None):
        self.PG([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], c, fill, w, bow=2)

    def E(self, x, y, rx, ry=None, c=INK, fill=None, w=None, turns=1.06):
        ry = rx if ry is None else ry
        if fill:
            self.items.append(E.Fill([self.P(x + rx * math.cos(a), y + ry * math.sin(a))
                                      for a in np.linspace(0, 2 * math.pi, 40)], fill, 0.55))
        X, Y = self.P(x, y)
        self.items.append(E.Path(E.ellipse(X, Y, rx * self.s, ry * self.s, turns=turns, seed=self._sd()), c, self.w(w)))

    def DOT(self, x, y, r, c=INK):
        self.items.append(E.Fill([self.P(x + r * math.cos(a), y + r * math.sin(a))
                                  for a in np.linspace(0, 2 * math.pi, 16)], c, 1.0))

    def ARC(self, x, y, rx, ry, a0, a1, c=INK, w=None, fill=None):
        pts = [(x + rx * math.cos(a), y + ry * math.sin(a)) for a in np.linspace(math.radians(a0), math.radians(a1), 28)]
        if fill:
            self.fill(pts, fill)
        self.items.append(E.Path(E.wobble([self.P(*p) for p in pts], 1.5, self._sd()), c, self.w(w)))

    def T(self, text, x, y, size=34, c=INK):
        X, Y = self.P(x, y)
        t = E.Txt(text, max(14, int(size * self.s)), c, Y, cx=X)
        t.dur = max(0.15, len(text) * 0.02)
        self.items.append(t)


# ------------------------------------------------------------------ nhân vật
def person(p, x, fy, k=1.0, shirt=BLUE, pose='down', face='smile', hair='short', hat=None, backpack=False,
           lpose='down', pants=INK):
    hy, hr = fy - 215 * k, 30 * k
    sh = hy + hr + 12 * k
    hip = fy - 85 * k
    light = tuple(min(255, int(c * 0.35 + 255 * 0.65)) for c in shirt)
    if backpack:
        p.R(x - 58 * k, sh + 5 * k, x - 28 * k, hip - 10 * k, ORANGE, LO)
    # chân
    if pose == 'sit':
        p.L([(x - 10 * k, hip), (x + 45 * k, hip), (x + 48 * k, fy)], pants, 9 * k)
        p.L([(x + 10 * k, hip), (x + 60 * k, hip + 4 * k), (x + 62 * k, fy)], pants, 9 * k)
    elif pose in ('walk', 'pull'):
        p.L([(x - 12 * k, hip), (x - 38 * k, fy)], pants, 9 * k)
        p.L([(x + 12 * k, hip), (x + 30 * k, fy)], pants, 9 * k)
    else:
        p.L([(x - 13 * k, hip), (x - 20 * k, fy)], pants, 9 * k)
        p.L([(x + 13 * k, hip), (x + 20 * k, fy)], pants, 9 * k)
    # thân
    p.PG([(x - 34 * k, sh), (x + 34 * k, sh), (x + 28 * k, hip), (x - 28 * k, hip)], shirt, light)
    # tay
    ls, rs = (x - 32 * k, sh + 8 * k), (x + 32 * k, sh + 8 * k)
    anchors = {'head': (x, hy), 'top': (x, hy - hr), 'chest': (x, sh + 30 * k), 'hip': (x, hip)}

    def arm(side, kind):
        sg = -1 if side == 'l' else 1
        s0 = ls if side == 'l' else rs
        if kind == 'down':
            pts = [s0, (x + sg * 46 * k, hip - 6 * k)]
        elif kind == 'wave':
            pts = [s0, (x + sg * 70 * k, sh - 8 * k), (x + sg * 82 * k, hy - 40 * k)]
        elif kind == 'raise':
            pts = [s0, (x + sg * 44 * k, hy - 30 * k), (x + sg * 46 * k, hy - 95 * k)]
        elif kind == 'think':
            pts = [s0, (x + sg * 60 * k, sh + 42 * k), (x + sg * 16 * k, hy + 22 * k)]
        elif kind == 'hold':
            pts = [s0, (x + sg * 46 * k, sh + 42 * k), (x + sg * 22 * k, sh + 58 * k)]
        elif kind == 'present':
            pts = [s0, (x + sg * 70 * k, sh + 5 * k), (x + sg * 100 * k, sh - 25 * k)]
        elif kind == 'pull':
            pts = [s0, (x + sg * 55 * k, sh + 40 * k), (x + sg * 78 * k, hip + 8 * k)]
        elif kind == 'phone':
            pts = [s0, (x + sg * 55 * k, sh + 38 * k), (x + sg * 30 * k, hy + 6 * k)]
        elif kind == 'type':
            pts = [s0, (x + sg * 30 * k, sh + 45 * k), (x + 70 * k + sg * 12 * k, sh + 52 * k)]
        elif kind == 'shake':
            pts = [s0, (x + sg * 50 * k, sh + 40 * k), (x + sg * 80 * k, sh + 38 * k)]
        else:
            pts = [s0, (x + sg * 46 * k, hip - 6 * k)]
        p.L(pts, shirt, 8 * k)
        anchors[side + 'hand'] = pts[-1]

    arm('l', lpose if pose not in ('hold', 'type') else pose)
    arm('r', pose if pose not in ('walk', 'sit') else 'down')
    # đầu
    if hair == 'long':
        p.PG([(x - hr * 1.08, hy - 2 * k), (x - hr * 1.15, hy + hr * 1.3), (x - hr * 0.6, hy + hr * 1.1)], HAIR, HAIR)
        p.PG([(x + hr * 1.08, hy - 2 * k), (x + hr * 1.15, hy + hr * 1.3), (x + hr * 0.6, hy + hr * 1.1)], HAIR, HAIR)
    p.E(x, hy, hr, hr, INK, SKIN, 6 * k)
    top = [(x + hr * 1.06 * math.cos(a), hy + hr * 1.06 * math.sin(a)) for a in np.linspace(math.pi * 1.02, math.pi * 1.98, 14)]
    p.PG(top + [(x + hr * 0.85, hy - hr * 0.3), (x - hr * 0.85, hy - hr * 0.3)], HAIR, HAIR, 4 * k)
    p.DOT(x - 10 * k, hy + 2 * k, 3.5 * k)
    p.DOT(x + 10 * k, hy + 2 * k, 3.5 * k)
    if face == 'smile':
        p.ARC(x, hy + 9 * k, 11 * k, 7 * k, 20, 160, INK, 3.5 * k)
    elif face == 'sad':
        p.ARC(x, hy + 22 * k, 10 * k, 6 * k, 200, 340, INK, 3.5 * k)
    elif face == 'wow':
        p.E(x, hy + 15 * k, 5 * k, 6 * k, INK, None, 3 * k)
    else:
        p.L([(x - 8 * k, hy + 16 * k), (x + 8 * k, hy + 16 * k)], INK, 3.5 * k, 1)
    if face in ('sad', 'worried'):
        p.L([(x - 16 * k, hy - 12 * k), (x - 5 * k, hy - 8 * k)], INK, 3 * k, 1)
        p.L([(x + 16 * k, hy - 12 * k), (x + 5 * k, hy - 8 * k)], INK, 3 * k, 1)
    if hat == 'grad':
        t = hy - hr - 4 * k
        p.PG([(x, t - 20 * k), (x + 52 * k, t - 2 * k), (x, t + 14 * k), (x - 52 * k, t - 2 * k)], INK, (70, 74, 100), 4 * k)
        p.L([(x, t - 3 * k), (x + 40 * k, t + 6 * k), (x + 40 * k, t + 30 * k)], ORANGE, 3.5 * k, 1)
    return anchors


# ------------------------------------------------------------------ đồ vật
def suitcase(p, x, y, k=1.0, c=ORANGE):
    fc = {ORANGE: LO, BLUE: LB, RED: LR}.get(c, LO)
    p.R(x - 45 * k, y - 120 * k, x + 45 * k, y - 10 * k, c, fc)
    p.L([(x - 15 * k, y - 120 * k), (x - 15 * k, y - 150 * k), (x + 15 * k, y - 150 * k), (x + 15 * k, y - 120 * k)], INK, 5 * k)
    p.L([(x - 20 * k, y - 120 * k), (x - 20 * k, y - 10 * k)], c, 4 * k)
    p.L([(x + 20 * k, y - 120 * k), (x + 20 * k, y - 10 * k)], c, 4 * k)
    p.E(x - 32 * k, y - 3 * k, 7 * k, 7 * k, INK, None, 4 * k)
    p.E(x + 32 * k, y - 3 * k, 7 * k, 7 * k, INK, None, 4 * k)


def backpack(p, x, y, k=1.0):
    p.PG([(x - 40 * k, y), (x - 45 * k, y - 90 * k), (x, y - 110 * k), (x + 45 * k, y - 90 * k), (x + 40 * k, y)], ORANGE, LO)
    p.R(x - 25 * k, y - 45 * k, x + 25 * k, y - 10 * k, ORANGE)


def book(p, x, y, k=1.0, c=BLUE, open_=True):
    fc = {BLUE: LB, RED: LR, GREEN: LG, ORANGE: LO}.get(c, LB)
    if open_:
        p.PG([(x, y - 30 * k), (x - 70 * k, y - 42 * k), (x - 70 * k, y + 30 * k), (x, y + 40 * k)], c, fc)
        p.PG([(x, y - 30 * k), (x + 70 * k, y - 42 * k), (x + 70 * k, y + 30 * k), (x, y + 40 * k)], c, fc)
        p.L([(x - 55 * k, y - 18 * k), (x - 15 * k, y - 12 * k)], GREY, 3 * k, 1)
        p.L([(x + 15 * k, y - 12 * k), (x + 55 * k, y - 18 * k)], GREY, 3 * k, 1)
    else:
        p.R(x - 45 * k, y - 60 * k, x + 45 * k, y + 60 * k, c, fc)
        p.L([(x - 35 * k, y - 60 * k), (x - 35 * k, y + 60 * k)], c, 4 * k)


def laptop(p, x, y, k=1.0, screen='form'):
    p.R(x - 80 * k, y - 110 * k, x + 80 * k, y - 10 * k, INK, (225, 230, 240))
    p.PG([(x - 100 * k, y - 10 * k), (x + 100 * k, y - 10 * k), (x + 115 * k, y + 10 * k), (x - 115 * k, y + 10 * k)], INK, LGR)
    if screen == 'form':
        for i in range(3):
            p.R(x - 60 * k, y - 95 * k + i * 25 * k, x + 60 * k, y - 80 * k + i * 25 * k, GREY, WHITE, 3 * k)
        p.R(x - 25 * k, y - 25 * k, x + 25 * k, y - 15 * k, BLUE, LB, 3 * k)
    elif screen == 'video':
        p.E(x, y - 75 * k, 18 * k, 18 * k, INK, SKIN, 4 * k)
        p.ARC(x, y - 25 * k, 32 * k, 28 * k, 180, 360, BLUE, 4 * k, LB)
    elif screen == 'web':
        p.R(x - 70 * k, y - 100 * k, x + 70 * k, y - 85 * k, BLUE, LB, 3 * k)
        p.R(x - 70 * k, y - 75 * k, x - 10 * k, y - 25 * k, ORANGE, LO, 3 * k)
        p.L([(x, y - 70 * k), (x + 65 * k, y - 70 * k)], GREY, 3 * k, 1)
        p.L([(x, y - 50 * k), (x + 55 * k, y - 50 * k)], GREY, 3 * k, 1)
    elif screen == 'chart':
        for i, hh in enumerate([25, 45, 65]):
            p.R(x - 45 * k + i * 35 * k, y - 25 * k - hh * k, x - 25 * k + i * 35 * k, y - 25 * k, GREEN, LG, 3 * k)
    elif screen == 'check':
        p.L([(x - 30 * k, y - 60 * k), (x - 5 * k, y - 35 * k), (x + 40 * k, y - 85 * k)], GREEN, 10 * k, 1)


def phone(p, x, y, k=1.0, c=INK):
    p.R(x - 25 * k, y - 45 * k, x + 25 * k, y + 45 * k, c, (225, 230, 240))
    p.L([(x - 8 * k, y + 35 * k), (x + 8 * k, y + 35 * k)], c, 3 * k, 1)


def passport(p, x, y, k=1.0, open_=False, visa=False):
    if open_:
        p.R(x - 90 * k, y - 60 * k, x, y + 60 * k, (110, 40, 60), (245, 235, 235))
        p.R(x, y - 60 * k, x + 90 * k, y + 60 * k, (110, 40, 60), (245, 235, 235))
        p.R(x - 75 * k, y - 40 * k, x - 35 * k, y + 5 * k, GREY, LB, 3 * k)
        p.L([(x - 75 * k, y + 25 * k), (x - 15 * k, y + 25 * k)], GREY, 3 * k, 1)
        if visa:
            p.R(x + 12 * k, y - 48 * k, x + 78 * k, y + 48 * k, GREEN, LG, 3 * k)
            p.T('VISA', x + 45 * k, y - 25 * k, 24 * k, GREEN)
            p.L([(x + 22 * k, y + 10 * k), (x + 68 * k, y + 10 * k)], GREEN, 3 * k, 1)
            p.L([(x + 22 * k, y + 28 * k), (x + 58 * k, y + 28 * k)], GREEN, 3 * k, 1)
        else:
            p.L([(x + 15 * k, y - 30 * k), (x + 75 * k, y - 30 * k)], GREY, 3 * k, 1)
            p.L([(x + 15 * k, y), (x + 75 * k, y)], GREY, 3 * k, 1)
    else:
        p.R(x - 45 * k, y - 65 * k, x + 45 * k, y + 65 * k, (110, 40, 60), (240, 200, 210))
        p.E(x, y - 10 * k, 22 * k, 22 * k, ORANGE, None, 4 * k)
        p.T('PASSPORT', x, y + 38 * k, 20 * k, ORANGE)


def ticket(p, x, y, k=1.0):
    p.R(x - 85 * k, y - 38 * k, x + 85 * k, y + 38 * k, BLUE, LB)
    p.L([(x + 35 * k, y - 38 * k), (x + 35 * k, y + 38 * k)], BLUE, 3 * k, 1)
    p.PG([(x - 60 * k, y), (x - 10 * k, y - 18 * k), (x - 20 * k, y + 2 * k)], BLUE, None, 3 * k, 1)
    p.L([(x - 70 * k, y + 22 * k), (x + 15 * k, y + 22 * k)], GREY, 3 * k, 1)
    p.L([(x + 50 * k, y - 15 * k), (x + 70 * k, y - 15 * k)], GREY, 3 * k, 1)


def globe(p, x, y, r=80):
    p.E(x, y, r, r, BLUE, LB)
    p.E(x, y, r * 0.42, r, BLUE, None, 3.5)
    p.L([(x - r, y), (x + r, y)], BLUE, 3.5, 1)
    p.PG([(x - r * 0.5, y - r * 0.45), (x + r * 0.05, y - r * 0.65), (x + r * 0.3, y - r * 0.2),
          (x - r * 0.1, y + r * 0.15), (x - r * 0.45, y + r * 0.05)], GREEN, LG, 3)
    p.PG([(x + r * 0.2, y + r * 0.3), (x + r * 0.55, y + r * 0.25), (x + r * 0.45, y + r * 0.6)], GREEN, LG, 3)


def plane(p, x, y, k=1.0, c=BLUE):
    body = [(x - 110 * k, y + 5 * k), (x - 90 * k, y - 12 * k), (x + 75 * k, y - 12 * k), (x + 108 * k, y),
            (x + 75 * k, y + 12 * k), (x - 90 * k, y + 12 * k)]
    p.PG(body, c, LB)
    p.PG([(x - 5 * k, y + 10 * k), (x - 45 * k, y + 70 * k), (x - 22 * k, y + 70 * k), (x + 30 * k, y + 10 * k)], c, LB)
    p.L([(x - 5 * k, y - 10 * k), (x - 35 * k, y - 55 * k), (x - 17 * k, y - 55 * k), (x + 25 * k, y - 10 * k)], c)
    p.L([(x - 85 * k, y - 11 * k), (x - 105 * k, y - 50 * k), (x - 88 * k, y - 50 * k), (x - 62 * k, y - 11 * k)], c)


def map_shape(p, kind, x, y, k=1.0, c=GREEN, fill=LG):
    shapes = {
        'han': [(-40, -130), (60, -150), (70, -100), (40, -60), (60, -10), (75, 40), (70, 90), (50, 120), (0, 125),
                (-40, 115), (-60, 90), (-50, 50), (-70, 10), (-60, -30), (-80, -60), (-60, -100)],
        'dai loan': [(10, -130), (40, -110), (55, -60), (50, 0), (30, 60), (5, 120), (-10, 130), (-25, 90), (-35, 30),
                     (-30, -40), (-15, -100)],
        'viet nam': [(-30, -150), (25, -150), (15, -110), (-15, -80), (5, -40), (40, 0), (55, 40), (40, 90), (10, 120),
                     (-20, 145), (-32, 120), (-5, 90), (18, 50), (5, 10), (-25, -30), (-45, -80), (-40, -120)],
    }
    pts = [(x + a * k, y + b * k) for a, b in shapes[kind]]
    p.PG(pts, c, fill, None, 2)
    if kind == 'han':
        p.E(x - 30 * k, y + 160 * k, 18 * k, 9 * k, c, fill, 3 * k)
        p.DOT(x - 30 * k, y - 20 * k, 7 * k, RED)
    elif kind == 'dai loan':
        p.DOT(x + 25 * k, y - 110 * k, 7 * k, RED)
    else:
        p.DOT(x - 5 * k, y - 120 * k, 6 * k, RED)
        p.DOT(x + 20 * k, y + 110 * k, 6 * k, RED)


def world_map(p, x, y, k=1.0):
    p.R(x - 230 * k, y - 120 * k, x + 230 * k, y + 120 * k, BLUE, (225, 236, 250), 4)
    for poly_ in ([(-200, -80), (-120, -95), (-110, -40), (-140, 0), (-115, 30), (-130, 95), (-150, 60), (-165, 0), (-195, -40)],
                  [(-40, -85), (10, -90), (20, -50), (-5, -40), (20, 0), (0, 80), (-25, 60), (-40, 0), (-50, -50)],
                  [(20, -95), (170, -90), (190, -40), (150, 0), (100, 10), (60, -20), (30, -50)],
                  [(130, 50), (190, 45), (195, 85), (140, 90)]):
        p.PG([(x + a * k, y + b * k) for a, b in poly_], GREEN, LG, 3)


def flag(p, kind, x, y, k=1.0):
    w, h = 90 * k, 60 * k
    if kind == 'viet nam':
        p.R(x - w, y - h, x + w, y + h, RED, (230, 70, 60))
        star(p, x, y, 32 * k, YEL, (255, 220, 60))
    elif kind == 'han':
        p.R(x - w, y - h, x + w, y + h, INK, WHITE)
        r = 30 * k
        top = [(x + r * math.cos(a), y + r * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 20)]
        bot = [(x + r * math.cos(a), y + r * math.sin(a)) for a in np.linspace(0, math.pi, 20)]
        p.PG(top, RED, (225, 60, 60), 3)
        p.PG(bot, BLUE, (60, 90, 190), 3)
        for sx, sy in ((-1, -1), (1, 1), (1, -1), (-1, 1)):
            cx_, cy_ = x + sx * 62 * k, y + sy * 38 * k
            for i in range(3):
                d = (i - 1) * 9 * k
                p.L([(cx_ - 12 * k + d * sy * sx * 0.3, cy_ + d - 6 * k * sx * sy), (cx_ + 12 * k + d * sy * sx * 0.3, cy_ + d + 6 * k * sx * sy)], INK, 4 * k, 1)
    elif kind == 'dai loan':
        p.R(x - w, y - h, x + w, y + h, RED, (225, 60, 60))
        p.R(x - w, y - h, x, y, BLUE, (40, 70, 170))
        sun_x, sun_y = x - w / 2, y - h / 2
        for i in range(12):
            a = i * math.pi / 6
            p.L([(sun_x + 12 * k * math.cos(a), sun_y + 12 * k * math.sin(a)),
                 (sun_x + 22 * k * math.cos(a), sun_y + 22 * k * math.sin(a))], WHITE, 3 * k, 1)
        p.E(sun_x, sun_y, 10 * k, 10 * k, WHITE, WHITE, 3 * k)
    p.L([(x - w, y - h), (x - w, y + h + 90 * k)], BROWN, 5 * k, 1)


def star(p, x, y, r, c=ORANGE, fill=LY):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.42
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    p.PG(pts, c, fill, None, 1)


def building(p, x, y, k=1.0, c=RED, kind='uni'):
    fc = {RED: LR, BLUE: LB, ORANGE: LO, GREY: LGR, GREEN: LG}.get(c, LR)
    if kind == 'uni':
        p.PG([(x - 150 * k, y - 120 * k), (x, y - 190 * k), (x + 150 * k, y - 120 * k)], c, fc)
        p.R(x - 140 * k, y - 120 * k, x + 140 * k, y, c, fc)
        for i in range(5):
            xx = x - 110 * k + i * 55 * k
            p.L([(xx, y - 110 * k), (xx, y - 8 * k)], c, 6 * k, 1)
        p.R(x - 20 * k, y - 55 * k, x + 20 * k, y, INK, (240, 230, 220), 4 * k)
        p.E(x, y - 150 * k, 14 * k, 14 * k, c, WHITE, 4 * k)
    elif kind == 'dorm':
        p.R(x - 90 * k, y - 220 * k, x + 90 * k, y, c, fc)
        for r_ in range(4):
            for c_ in range(3):
                xx, yy = x - 60 * k + c_ * 60 * k, y - 200 * k + r_ * 45 * k
                p.R(xx - 15 * k, yy, xx + 15 * k, yy + 25 * k, BLUE, LB, 3 * k)
        p.R(x - 18 * k, y - 30 * k, x + 18 * k, y, INK, None, 4 * k)
    elif kind == 'embassy':
        p.PG([(x - 140 * k, y - 140 * k), (x, y - 190 * k), (x + 140 * k, y - 140 * k)], GREY, LGR)
        p.R(x - 140 * k, y - 140 * k, x + 140 * k, y - 125 * k, GREY, LGR)
        for i in range(6):
            xx = x - 115 * k + i * 46 * k
            p.R(xx - 9 * k, y - 125 * k, xx + 9 * k, y - 10 * k, GREY, WHITE, 3 * k)
        p.R(x - 150 * k, y - 10 * k, x + 150 * k, y, GREY, LGR)
        p.L([(x + 120 * k, y - 190 * k), (x + 120 * k, y - 250 * k)], BROWN, 4 * k, 1)
        p.R(x + 120 * k, y - 250 * k, x + 170 * k, y - 220 * k, BLUE, LB, 3 * k)
    elif kind == 'house':
        p.PG([(x - 110 * k, y - 100 * k), (x, y - 180 * k), (x + 110 * k, y - 100 * k)], RED, LR)
        p.R(x - 90 * k, y - 100 * k, x + 90 * k, y, ORANGE, LO)
        p.R(x - 20 * k, y - 55 * k, x + 20 * k, y, INK, None, 4 * k)
        p.R(x - 70 * k, y - 80 * k, x - 35 * k, y - 50 * k, BLUE, LB, 3 * k)
        p.R(x + 35 * k, y - 80 * k, x + 70 * k, y - 50 * k, BLUE, LB, 3 * k)
    elif kind == 'shop':
        p.R(x - 120 * k, y - 130 * k, x + 120 * k, y, GREEN, LG)
        for i in range(6):
            xx = x - 120 * k + i * 40 * k
            p.PG([(xx, y - 130 * k), (xx + 40 * k, y - 130 * k), (xx + 40 * k, y - 105 * k), (xx, y - 105 * k)],
                 GREEN, WHITE if i % 2 else LG, 3 * k)
        p.R(x - 100 * k, y - 90 * k, x - 10 * k, y - 20 * k, BLUE, LB, 3 * k)
        p.R(x + 15 * k, y - 85 * k, x + 70 * k, y, INK, None, 4 * k)
    elif kind == 'office':
        p.R(x - 70 * k, y - 230 * k, x + 70 * k, y, BLUE, LB)
        for r_ in range(5):
            for c_ in range(2):
                xx, yy = x - 35 * k + c_ * 70 * k, y - 210 * k + r_ * 40 * k
                p.R(xx - 18 * k, yy, xx + 18 * k, yy + 22 * k, BLUE, WHITE, 3 * k)


def skyline(p, x, y, k=1.0):
    for (dx, w_, h_, c) in [(-230, 60, 140, BLUE), (-160, 50, 210, GREY), (-100, 70, 160, TEAL), (-20, 45, 260, BLUE),
                            (35, 65, 180, GREY), (110, 55, 230, TEAL), (175, 60, 150, BLUE)]:
        fc = {BLUE: LB, GREY: LGR, TEAL: LT}[c]
        p.R(x + dx * k, y - h_ * k, x + (dx + w_) * k, y, c, fc, 4)
        for yy in range(int(h_ / 40)):
            p.L([(x + (dx + 12) * k, y - (h_ - 20 - yy * 40) * k), (x + (dx + w_ - 12) * k, y - (h_ - 20 - yy * 40) * k)],
                c, 2.5, 1)
    p.L([(x - 260 * k, y), (x + 260 * k, y)], INK, 5, 2)


def doc(p, x, y, k=1.0, c=INK, fill=WHITE, lines=4, title=None):
    p.R(x - 60 * k, y - 80 * k, x + 60 * k, y + 80 * k, c, fill)
    if title:
        p.T(title, x, y - 55 * k, 22 * k, c)
    for i in range(lines):
        p.L([(x - 40 * k, y - 25 * k + i * 25 * k), (x + 40 * k - (i % 2) * 20 * k, y - 25 * k + i * 25 * k)], GREY, 3 * k, 1)


def stamp(p, x, y, text, c=GREEN, k=1.0, angle=-8):
    w = (len(text) * 14 + 30) * k
    a = math.radians(angle)
    pts = [(-w / 2, -28 * k), (w / 2, -28 * k), (w / 2, 28 * k), (-w / 2, 28 * k)]
    rot = [(x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a)) for px, py in pts]
    p.PG(rot, c, None, 7 * k, 2)
    p.T(text, x, y, 32 * k, c)


def stack(p, x, y, k=1.0, labels=('HỌC BẠ', 'BẰNG', 'HỘ CHIẾU')):
    cols = [(BLUE, LB), (ORANGE, LO), (GREEN, LG), (RED, LR)]
    for i, lab in enumerate(labels):
        c, f = cols[i % 4]
        yy = y - i * 34 * k
        p.R(x - 110 * k + i * 6 * k, yy - 30 * k, x + 110 * k + i * 6 * k, yy, c, f)
        p.T(lab, x + 50 * k + i * 6 * k, yy - 15 * k, 20 * k, c)


def clipboard(p, x, y, k=1.0, n=3, ticks=3):
    p.R(x - 80 * k, y - 100 * k, x + 80 * k, y + 110 * k, INK, (245, 245, 240))
    p.R(x - 30 * k, y - 115 * k, x + 30 * k, y - 88 * k, ORANGE, LO)
    for i in range(n):
        yy = y - 55 * k + i * 55 * k
        p.R(x - 60 * k, yy - 14 * k, x - 32 * k, yy + 14 * k, GREY, WHITE, 3 * k)
        if i < ticks:
            p.L([(x - 58 * k, yy), (x - 46 * k, yy + 12 * k), (x - 28 * k, yy - 18 * k)], GREEN, 6 * k, 1)
        p.L([(x - 15 * k, yy), (x + 60 * k, yy)], GREY, 4 * k, 1)


def clock(p, x, y, r=60, c=ORANGE):
    p.E(x, y, r, r, c, LO)
    p.L([(x, y), (x, y - r * 0.65)], INK, 6, 1)
    p.L([(x, y), (x + r * 0.5, y + r * 0.25)], INK, 6, 1)


def calendar(p, x, y, k=1.0, mark=True):
    p.R(x - 80 * k, y - 70 * k, x + 80 * k, y + 80 * k, RED)
    p.R(x - 80 * k, y - 70 * k, x + 80 * k, y - 35 * k, RED, LR)
    p.L([(x - 45 * k, y - 85 * k), (x - 45 * k, y - 55 * k)], INK, 5 * k, 1)
    p.L([(x + 45 * k, y - 85 * k), (x + 45 * k, y - 55 * k)], INK, 5 * k, 1)
    for j in range(3):
        for i in range(4):
            p.DOT(x - 55 * k + i * 37 * k, y - 10 * k + j * 32 * k, 4 * k, GREY)
    if mark:
        p.E(x + 19 * k, y + 22 * k, 16 * k, 14 * k, ORANGE, None, 4 * k)


def bubble(p, x, y, w=120, h=60, text=None, c=BLUE, think=False, tail='left'):
    if think:
        p.E(x, y, w, h, c, (240, 245, 255))
        tx = x - w * 0.6 if tail == 'left' else x + w * 0.6
        p.E(tx, y + h + 18, 12, 10, c, None, 4)
        p.E(tx + (-14 if tail == 'left' else 14), y + h + 40, 7, 6, c, None, 3)
    else:
        sx = -1 if tail == 'left' else 1
        pts = [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x + sx * w * 0.3, y + h), (x + sx * w * 0.55, y + h + 35),
               (x + sx * w * 0.6, y + h)][:]
        if tail == 'left':
            pts = [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w * 0.3, y + h), (x - w * 0.6, y + h + 35),
                   (x - w * 0.55, y + h), (x - w, y + h)]
        else:
            pts = [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x + w * 0.55, y + h), (x + w * 0.6, y + h + 35),
                   (x + w * 0.3, y + h), (x - w, y + h)]
        p.PG(pts, c, (240, 245, 255), None, 2)
    if text:
        p.T(text, x, y, 30, c)


def coin(p, x, y, r=22):
    p.E(x, y, r, r, ORANGE, LY, 4)
    p.L([(x, y - r * 0.5), (x, y + r * 0.5)], ORANGE, 3, 1)


def money(p, x, y, k=1.0):
    for i in range(3):
        d = (2 - i) * 12 * k
        p.R(x - 85 * k - d, y - 45 * k - d, x + 85 * k - d, y + 45 * k - d, GREEN, LG if i == 2 else None, 4 * k)
    p.E(x, y, 24 * k, 24 * k, GREEN, None, 4 * k)
    p.T('$', x, y, 34 * k, GREEN)


def money_bag(p, x, y, k=1.0):
    p.PG([(x - 25 * k, y - 75 * k), (x + 25 * k, y - 75 * k), (x + 15 * k, y - 60 * k), (x + 70 * k, y - 10 * k),
          (x + 60 * k, y + 55 * k), (x - 60 * k, y + 55 * k), (x - 70 * k, y - 10 * k), (x - 15 * k, y - 60 * k)], BROWN, LO)
    p.L([(x - 20 * k, y - 60 * k), (x + 20 * k, y - 60 * k)], BROWN, 5 * k, 1)
    p.T('$', x, y + 5 * k, 50 * k, GREEN)


def piggy(p, x, y, k=1.0):
    p.E(x, y, 80 * k, 58 * k, (210, 90, 130), (250, 210, 225))
    p.E(x + 78 * k, y + 5 * k, 16 * k, 13 * k, (210, 90, 130), (250, 190, 210), 4 * k)
    p.PG([(x + 30 * k, y - 50 * k), (x + 45 * k, y - 80 * k), (x + 55 * k, y - 48 * k)], (210, 90, 130), (250, 210, 225), 4 * k)
    for dx in (-45, -15, 20, 50):
        p.L([(x + dx * k, y + 48 * k), (x + dx * k, y + 70 * k)], (210, 90, 130), 7 * k, 1)
    p.DOT(x + 45 * k, y - 15 * k, 4 * k)
    p.L([(x - 20 * k, y - 57 * k), (x + 15 * k, y - 57 * k)], INK, 5 * k, 1)


def scale_(p, x, y, k=1.0, labels=('A', 'B')):
    p.L([(x, y + 90 * k), (x, y - 80 * k)], BROWN, 7 * k, 1)
    p.L([(x - 70 * k, y + 90 * k), (x + 70 * k, y + 90 * k)], BROWN, 7 * k, 1)
    p.L([(x - 130 * k, y - 70 * k), (x + 130 * k, y - 80 * k)], BROWN, 6 * k, 1)
    for sx, lab, c, f in ((-1, labels[0], BLUE, LB), (1, labels[1], ORANGE, LO)):
        bx = x + sx * 130 * k
        p.L([(bx, y - 75 * k), (bx - 40 * k, y - 5 * k)], GREY, 3 * k, 1)
        p.L([(bx, y - 75 * k), (bx + 40 * k, y - 5 * k)], GREY, 3 * k, 1)
        p.ARC(bx, y - 5 * k, 50 * k, 22 * k, 0, 180, c, 5 * k, f)
        p.T(lab, bx, y + 40 * k, 24 * k, c)


def bars(p, x, y, k=1.0, vals=(60, 100, 150, 200), cols=(GREEN,)):
    p.L([(x - 140 * k, y - 210 * k), (x - 140 * k, y), (x + 150 * k, y)], INK, 5 * k, 1)
    n = len(vals)
    for i, v in enumerate(vals):
        c = cols[i % len(cols)]
        f = {GREEN: LG, BLUE: LB, ORANGE: LO, RED: LR}.get(c, LG)
        xx = x - 120 * k + i * (250 / n) * k
        p.R(xx, y - v * k, xx + (250 / n - 18) * k, y, c, f, 4 * k)


def table_grid(p, x, y, k=1.0, rows=4, cols=4, head=('', 'A', 'B', 'C')):
    w, h = 110 * k, 42 * k
    x0, y0 = x - cols * w / 2, y - rows * h / 2
    p.R(x0, y0, x0 + cols * w, y0 + h, BLUE, LB, 4 * k)
    p.R(x0, y0, x0 + cols * w, y0 + rows * h, INK, None, 4 * k)
    for r in range(1, rows):
        p.L([(x0, y0 + r * h), (x0 + cols * w, y0 + r * h)], GREY, 3 * k, 1)
    for c in range(1, cols):
        p.L([(x0 + c * w, y0), (x0 + c * w, y0 + rows * h)], GREY, 3 * k, 1)
    for c, t in enumerate(head[:cols]):
        if t:
            p.T(t, x0 + c * w + w / 2, y0 + h / 2, 24 * k, BLUE)
    return x0, y0, w, h


def desk(p, x, y, k=1.0):
    p.R(x - 130 * k, y - 15 * k, x + 130 * k, y, BROWN, LO)
    p.L([(x - 115 * k, y), (x - 115 * k, y + 70 * k)], BROWN, 6 * k, 1)
    p.L([(x + 115 * k, y), (x + 115 * k, y + 70 * k)], BROWN, 6 * k, 1)


def food(p, kind, x, y, k=1.0):
    if kind == 'com':
        p.ARC(x, y, 60 * k, 45 * k, 0, 180, RED, 5 * k, LR)
        p.ARC(x, y + 2 * k, 52 * k, 30 * k, 180, 360, GREY, 4 * k, WHITE)
        p.L([(x + 20 * k, y - 70 * k), (x + 70 * k, y - 20 * k)], BROWN, 4 * k, 1)
        p.L([(x + 32 * k, y - 76 * k), (x + 78 * k, y - 30 * k)], BROWN, 4 * k, 1)
    elif kind == 'mi':
        p.ARC(x, y, 65 * k, 48 * k, 0, 180, BLUE, 5 * k, LB)
        for i in range(4):
            p.ARC(x - 30 * k + i * 20 * k, y - 4 * k, 9 * k, 7 * k, 180, 360, YEL, 3 * k)
        p.E(x + 25 * k, y - 10 * k, 15 * k, 9 * k, ORANGE, LY, 3 * k)
        for i in range(3):
            p.L([(x - 30 * k + i * 25 * k, y - 25 * k), (x - 25 * k + i * 25 * k, y - 60 * k)], GREY, 2.5 * k, 2)
    elif kind == 'kimchi':
        p.ARC(x, y, 60 * k, 35 * k, 0, 180, GREY, 5 * k, LGR)
        for dx in (-30, 0, 28):
            p.E(x + dx * k, y - 12 * k, 22 * k, 14 * k, RED, (240, 120, 100), 3 * k)
    elif kind == 'tra sua':
        p.PG([(x - 35 * k, y - 80 * k), (x + 35 * k, y - 80 * k), (x + 28 * k, y + 40 * k), (x - 28 * k, y + 40 * k)],
             BROWN, (235, 210, 180))
        p.L([(x + 5 * k, y - 80 * k), (x + 20 * k, y - 120 * k)], INK, 6 * k, 1)
        for dx, dy in ((-15, 25), (0, 30), (15, 22), (-5, 15), (10, 10)):
            p.DOT(x + dx * k, y + dy * k, 6 * k, INK)
    elif kind == 'banh bao':
        p.ARC(x, y + 20 * k, 75 * k, 30 * k, 0, 180, BROWN, 5 * k, LO)
        for dx in (-35, 0, 35):
            p.ARC(x + dx * k, y + 10 * k, 22 * k, 26 * k, 180, 360, GREY, 3 * k, WHITE)
    elif kind == 'ca phe':
        p.PG([(x - 35 * k, y - 50 * k), (x + 35 * k, y - 50 * k), (x + 28 * k, y + 30 * k), (x - 28 * k, y + 30 * k)],
             BROWN, (235, 210, 180))
        p.ARC(x + 38 * k, y - 15 * k, 16 * k, 18 * k, -90, 90, BROWN, 5 * k)
        for i in range(3):
            p.L([(x - 15 * k + i * 15 * k, y - 60 * k), (x - 10 * k + i * 15 * k, y - 90 * k)], GREY, 2.5 * k, 2)


def bus(p, x, y, k=1.0):
    p.R(x - 120 * k, y - 100 * k, x + 120 * k, y - 15 * k, GREEN, LG)
    for i in range(4):
        p.R(x - 105 * k + i * 55 * k, y - 85 * k, x - 65 * k + i * 55 * k, y - 50 * k, BLUE, LB, 3 * k)
    p.E(x - 75 * k, y - 10 * k, 18 * k, 18 * k, INK, LGR, 4 * k)
    p.E(x + 75 * k, y - 10 * k, 18 * k, 18 * k, INK, LGR, 4 * k)


def train(p, x, y, k=1.0):
    p.PG([(x - 150 * k, y - 100 * k), (x + 110 * k, y - 100 * k), (x + 160 * k, y - 60 * k), (x + 160 * k, y - 15 * k),
          (x - 150 * k, y - 15 * k)], TEAL, LT)
    for i in range(4):
        p.R(x - 135 * k + i * 60 * k, y - 85 * k, x - 95 * k + i * 60 * k, y - 50 * k, BLUE, LB, 3 * k)
    p.L([(x - 150 * k, y - 35 * k), (x + 160 * k, y - 35 * k)], RED, 4 * k, 1)
    p.L([(x - 180 * k, y), (x + 190 * k, y)], INK, 5 * k, 1)


def cart(p, x, y, k=1.0):
    p.L([(x - 90 * k, y - 90 * k), (x - 65 * k, y - 90 * k), (x - 45 * k, y - 20 * k), (x + 70 * k, y - 20 * k), (x + 85 * k, y - 75 * k),
         (x - 55 * k, y - 75 * k)], GREY, 6 * k)
    p.E(x - 30 * k, y, 10 * k, 10 * k, INK, None, 4 * k)
    p.E(x + 55 * k, y, 10 * k, 10 * k, INK, None, 4 * k)
    p.E(x - 10 * k, y - 85 * k, 18 * k, 14 * k, RED, LR, 3 * k)
    p.R(x + 20 * k, y - 110 * k, x + 55 * k, y - 75 * k, GREEN, LG, 3 * k)


def washer(p, x, y, k=1.0):
    p.R(x - 70 * k, y - 160 * k, x + 70 * k, y, GREY, (240, 240, 245))
    p.L([(x - 70 * k, y - 130 * k), (x + 70 * k, y - 130 * k)], GREY, 4 * k, 1)
    p.E(x, y - 65 * k, 45 * k, 45 * k, BLUE, LB, 5 * k)
    p.ARC(x, y - 55 * k, 30 * k, 15 * k, 0, 180, BLUE, 3 * k)
    p.DOT(x + 45 * k, y - 145 * k, 5 * k, GREEN)


def lightbulb(p, x, y, k=1.0):
    pts = [(x + 50 * k * math.cos(a), y - 20 * k + 50 * k * math.sin(a)) for a in np.linspace(0.75 * math.pi, 2.25 * math.pi, 30)]
    p.PG(pts, ORANGE, LY)
    p.R(x - 22 * k, y + 20 * k, x + 22 * k, y + 45 * k, INK, LGR, 4 * k)
    for a in (-150, -90, -30):
        r = math.radians(a)
        p.L([(x + 65 * k * math.cos(r), y - 20 * k + 65 * k * math.sin(r)),
             (x + 85 * k * math.cos(r), y - 20 * k + 85 * k * math.sin(r))], ORANGE, 5 * k, 1)


def heart(p, x, y, r=30, c=RED):
    pts = [(x + r / 16 * 16 * math.sin(t) ** 3,
            y - r / 16 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))
           for t in np.linspace(0, 2 * math.pi, 40)]
    p.PG(pts, c, LR, 4, 1)


def hangul(p, x, y, k=1.0, c=BLUE):
    # 가 나 다 (vẽ nét)
    p.L([(x - 110 * k, y - 30 * k), (x - 80 * k, y - 30 * k), (x - 85 * k, y + 30 * k)], c, 7 * k, 1)
    p.L([(x - 65 * k, y - 40 * k), (x - 65 * k, y + 40 * k)], c, 7 * k, 1)
    p.L([(x - 65 * k, y), (x - 50 * k, y)], c, 7 * k, 1)
    p.L([(x - 25 * k, y - 30 * k), (x - 25 * k, y + 25 * k), (x + 5 * k, y + 25 * k)], c, 7 * k, 1)
    p.L([(x + 20 * k, y - 40 * k), (x + 20 * k, y + 40 * k)], c, 7 * k, 1)
    p.L([(x + 20 * k, y), (x + 35 * k, y)], c, 7 * k, 1)
    p.L([(x + 85 * k, y - 30 * k), (x + 55 * k, y - 30 * k), (x + 55 * k, y + 25 * k), (x + 85 * k, y + 25 * k)], c, 7 * k, 1)
    p.L([(x + 100 * k, y - 40 * k), (x + 100 * k, y + 40 * k)], c, 7 * k, 1)
    p.L([(x + 100 * k, y), (x + 115 * k, y)], c, 7 * k, 1)


def hanzi(p, x, y, k=1.0, c=RED):
    # chữ 中
    p.R(x - 45 * k, y - 30 * k, x + 45 * k, y + 20 * k, c, None, 8 * k)
    p.L([(x, y - 65 * k), (x, y + 65 * k)], c, 8 * k, 1)


def fingerprint(p, x, y, k=1.0):
    for i in range(5):
        r = (15 + i * 14) * k
        p.ARC(x, y, r * 0.8, r, 200, 520 - i * 8, PURPLE, 4 * k)


def headphones(p, x, y, k=1.0):
    p.ARC(x, y, 60 * k, 60 * k, 180, 360, INK, 8 * k)
    p.R(x - 72 * k, y - 10 * k, x - 48 * k, y + 35 * k, RED, LR, 4 * k)
    p.R(x + 48 * k, y - 10 * k, x + 72 * k, y + 35 * k, RED, LR, 4 * k)


def flask(p, x, y, k=1.0):
    p.PG([(x - 15 * k, y - 80 * k), (x + 15 * k, y - 80 * k), (x + 15 * k, y - 30 * k), (x + 60 * k, y + 50 * k),
          (x - 60 * k, y + 50 * k), (x - 15 * k, y - 30 * k)], TEAL, None)
    p.fill([(x - 38 * k, y + 12 * k), (x + 38 * k, y + 12 * k), (x + 60 * k, y + 50 * k), (x - 60 * k, y + 50 * k)], (150, 220, 200))
    p.DOT(x - 10 * k, y + 25 * k, 5 * k, WHITE)
    p.DOT(x + 12 * k, y + 35 * k, 4 * k, WHITE)


def board(p, x, y, k=1.0, text='A B C'):
    p.R(x - 140 * k, y - 85 * k, x + 140 * k, y + 70 * k, BROWN, (45, 80, 60))
    p.T(text, x, y - 10 * k, 46 * k, WHITE)


def id_card(p, x, y, k=1.0, c=BLUE):
    p.R(x - 70 * k, y - 45 * k, x + 70 * k, y + 45 * k, c, LB if c == BLUE else LO)
    p.E(x - 35 * k, y - 5 * k, 18 * k, 18 * k, INK, SKIN, 3 * k)
    p.L([(x - 5 * k, y - 15 * k), (x + 50 * k, y - 15 * k)], GREY, 3 * k, 1)
    p.L([(x - 5 * k, y + 10 * k), (x + 40 * k, y + 10 * k)], GREY, 3 * k, 1)


def pin(p, x, y, k=1.0, c=RED):
    p.PG([(x, y), (x - 25 * k, y - 40 * k), (x - 22 * k, y - 62 * k), (x, y - 75 * k), (x + 22 * k, y - 62 * k), (x + 25 * k, y - 40 * k)], c, LR)
    p.E(x, y - 48 * k, 9 * k, 9 * k, c, WHITE, 3 * k)


def cloud(p, x, y, k=1.0, rain=False):
    pts = []
    for cx_, cy_, r in ((-40, 0, 30), (0, -20, 40), (45, 0, 30)):
        pass
    p.PG([(x - 75 * k, y + 20 * k), (x - 70 * k, y - 10 * k), (x - 40 * k, y - 30 * k), (x - 10 * k, y - 50 * k), (x + 30 * k, y - 45 * k),
          (x + 55 * k, y - 20 * k), (x + 80 * k, y), (x + 75 * k, y + 20 * k)], GREY, LGR)
    if rain:
        for dx in (-45, -10, 25, 60):
            p.L([(x + dx * k, y + 35 * k), (x + dx * k - 8 * k, y + 60 * k)], BLUE, 4 * k, 1)


def thermometer(p, x, y, k=1.0):
    p.R(x - 10 * k, y - 80 * k, x + 10 * k, y + 20 * k, RED, WHITE, 4 * k)
    p.E(x, y + 35 * k, 20 * k, 20 * k, RED, LR, 4 * k)
    p.L([(x, y + 30 * k), (x, y - 40 * k)], RED, 6 * k, 1)


def pill(p, x, y, k=1.0):
    p.PG([(x - 40 * k, y - 15 * k), (x + 40 * k, y - 15 * k), (x + 40 * k, y + 15 * k), (x - 40 * k, y + 15 * k)], RED, LR, 4 * k)
    p.L([(x, y - 15 * k), (x, y + 15 * k)], RED, 4 * k, 1)


def trophy(p, x, y, k=1.0):
    p.PG([(x - 45 * k, y - 70 * k), (x + 45 * k, y - 70 * k), (x + 35 * k, y - 15 * k), (x, y + 5 * k), (x - 35 * k, y - 15 * k)], ORANGE, LY)
    p.L([(x, y + 5 * k), (x, y + 35 * k)], ORANGE, 6 * k, 1)
    p.R(x - 30 * k, y + 35 * k, x + 30 * k, y + 50 * k, BROWN, LO, 4 * k)


def diploma(p, x, y, k=1.0):
    p.R(x - 90 * k, y - 30 * k, x + 90 * k, y + 30 * k, ORANGE, (253, 240, 215))
    p.E(x - 90 * k, y, 10 * k, 30 * k, ORANGE, None, 4 * k)
    p.E(x + 90 * k, y, 10 * k, 30 * k, ORANGE, None, 4 * k)
    p.E(x + 30 * k, y + 40 * k, 16 * k, 16 * k, RED, LR, 4 * k)


def gradcap(p, x, y, k=1.0):
    p.PG([(x, y - 60 * k), (x + 110 * k, y - 15 * k), (x, y + 25 * k), (x - 110 * k, y - 15 * k)], INK, (70, 74, 100))
    p.PG([(x - 65 * k, y + 5 * k), (x - 60 * k, y + 60 * k), (x, y + 75 * k), (x + 60 * k, y + 60 * k), (x + 65 * k, y + 5 * k)], RED, LR)
    p.L([(x, y - 18 * k), (x + 85 * k, y - 5 * k), (x + 85 * k, y + 50 * k)], ORANGE, 5 * k, 1)


def mag(p, x, y, k=1.0):
    p.E(x, y, 45 * k, 45 * k, BLUE, LB, 6 * k)
    p.L([(x + 32 * k, y + 32 * k), (x + 85 * k, y + 85 * k)], INK, 12 * k, 1)


def warning(p, x, y, k=1.0):
    p.PG([(x, y - 70 * k), (x + 75 * k, y + 55 * k), (x - 75 * k, y + 55 * k)], ORANGE, LY)
    p.L([(x, y - 30 * k), (x, y + 15 * k)], RED, 10 * k, 1)
    p.DOT(x, y + 35 * k, 7 * k, RED)


def chair_desk_person(p, x, fy, shirt=BLUE, screen='form', face='smile', hair='short'):
    a = person(p, x, fy, 0.9, shirt, 'type', face, hair)
    desk(p, x + 110, fy - 70, 0.7)
    laptop(p, x + 110, fy - 82, 0.6, screen)
    return a


# ------------------------------------------------------------------ cảnh
_RAW = []
SCENES = {}


def scene(name, keys):
    def deco(fn):
        _RAW.append((name, keys, fn))
        return fn
    return deco


def _index():
    if not SCENES:
        for name, keys, fn in _RAW:
            SCENES[E.norm(name)] = (name, [E.norm(k) for k in keys], fn)
    return SCENES


# --- 1. Tổng quan du học
@scene('học sinh và địa cầu', ['du hoc', 'nuoc ngoai', 'the gioi', 'ra nuoc ngoai', 'bat dau'])
def _(p):
    person(p, -90, 190, 1.0, BLUE, 'wave', 'smile', backpack=True)
    globe(p, 110, 20, 105)
    p.L([(60, 130), (160, 130)], BROWN, 6, 1)
    p.L([(110, 125), (110, 190)], BROWN, 6, 1)


@scene('máy bay qua bản đồ', ['bay sang', 'xuat canh', 'bay qua', 'chuyen bay', 'sang han', 'sang dai loan'])
def _(p):
    world_map(p, 0, 20, 1.0)
    p.L([(-10, 0), (60, -60), (150, -40)], RED, 4, 6)
    plane(p, 120, -70, 0.7, BLUE)
    pin(p, -10, 10, 0.7, RED)


@scene('hộ chiếu visa vé máy bay', ['ho chieu', 've may bay', 'giay to bay', 'visa va ve'])
def _(p):
    passport(p, -170, 20, 1.0)
    passport(p, 20, 20, 0.9, open_=True, visa=True)
    ticket(p, 200, 90, 0.8)


@scene('học sinh cầm thư nhập học', ['thu moi', 'thu nhap hoc', 'giay bao nhap hoc', 'admission', 'trung tuyen'])
def _(p):
    a = person(p, -40, 190, 1.0, GREEN, 'hold', 'wow', hair='long')
    hx, hy = a['chest']
    p.R(hx - 60, hy - 30, hx + 60, hy + 45, BLUE, WHITE)
    p.PG([(hx - 60, hy - 30), (hx, hy + 10), (hx + 60, hy - 30)], BLUE, LB, 4)
    star(p, 150, -110, 30)
    star(p, 200, -40, 18)
    star(p, -170, -100, 22)


@scene('sinh viên trước cổng trường', ['cong truong', 'truong dai hoc', 'nhap hoc', 'ngay dau'])
def _(p):
    building(p, 60, 180, 1.0, RED, 'uni')
    person(p, -190, 190, 0.85, BLUE, 'wave', 'smile', backpack=True)


@scene('học sinh suy nghĩ chọn nước', ['chon nuoc', 'nuoc nao', 'phan van', 'nen di dau', 'han hay dai loan', 'so sanh'])
def _(p):
    person(p, 0, 195, 0.95, BLUE, 'think', 'worried')
    bubble(p, 0, -150, 200, 48, None, GREY, think=True)
    flag(p, 'han', -110, -158, 0.35)
    flag(p, 'dai loan', 15, -158, 0.35)
    p.T('?', 120, -152, 60, ORANGE)


@scene('lộ trình du học', ['lo trinh', 'quy trinh', 'tung buoc', 'cac buoc', 'tu a den z'])
def _(p):
    map_shape(p, 'viet nam', -210, 20, 0.7, RED, LR)
    p.L([(-170, 40), (-60, -40), (60, 30), (170, -40)], ORANGE, 5, 10)
    for i, (x, y) in enumerate([(-170, 40), (-60, -40), (60, 30), (170, -40)]):
        p.E(x, y, 26, 26, BLUE, WHITE, 5)
        p.T(str(i + 1), x, y, 32, BLUE)
    plane(p, 200, -120, 0.45)


@scene('tư vấn viên với phụ huynh', ['tu van', 'trung tam', 'phu huynh', 'gap truc tiep', 'trao doi'])
def _(p):
    desk(p, 0, 110, 1.0)
    person(p, -190, 190, 0.85, PURPLE, 'down', 'smile', 'short')
    person(p, -110, 190, 0.7, GREEN, 'down', 'smile', 'long')
    person(p, 190, 190, 0.9, RED, 'present', 'smile', 'long')
    doc(p, 30, 70, 0.4)
    bubble(p, 130, -150, 80, 32, 'Tư vấn', RED, tail='right')


@scene('sinh viên kéo vali sân bay', ['san bay', 'keo vali', 'len duong', 'khoi hanh'])
def _(p):
    a = person(p, -60, 190, 1.0, BLUE, 'pull', 'smile', backpack=True)
    suitcase(p, 55, 190, 0.9, ORANGE)
    plane(p, 120, -130, 0.6)
    p.L([(-280, 192), (280, 192)], GREY, 4, 2)


@scene('mũ tốt nghiệp và cuộn bằng', ['tot nghiep', 'bang cap', 'ra truong', 'van bang', 'bang dai hoc'])
def _(p):
    gradcap(p, -100, -20, 1.2)
    diploma(p, 130, 60, 1.0)
    star(p, 180, -110, 28)


# --- 2. Hồ sơ
@scene('bộ hồ sơ xếp chồng', ['ho so', 'bo ho so', 'giay to', 'nop ho so', 'chuan bi ho so'])
def _(p):
    stack(p, 0, 170, 1.1, ('HỌC BẠ', 'BẰNG', 'HỘ CHIẾU', 'TÀI CHÍNH'))
    p.PG([(-160, -110), (-60, -110), (-40, -140), (60, -140), (80, -110), (160, -110), (160, -30), (-160, -30)], BROWN, LO)
    p.T('HỒ SƠ DU HỌC', 0, -70, 34, BROWN)


@scene('học bạ bằng bảng điểm', ['hoc ba', 'bang diem', 'diem so', 'bang tot nghiep thpt', 'gpa'])
def _(p):
    doc(p, -170, 20, 1.0, BLUE, LB, 4, 'HỌC BẠ')
    doc(p, 0, 0, 1.0, ORANGE, LO, 4, 'BẰNG')
    doc(p, 170, 20, 1.0, GREEN, LG, 4, 'ĐIỂM')
    p.T('8.0', 170, 80, 30, RED)


@scene('hộ chiếu mở', ['mo ho chieu', 'trang ho chieu', 'thong tin ho chieu', 'lam ho chieu'])
def _(p):
    passport(p, 0, 0, 1.8, open_=True)


@scene('ảnh thẻ hồ sơ', ['anh the', 'chup anh', 'anh 3x4', 'anh 4x6'])
def _(p):
    for i, x in enumerate((-150, 0, 150)):
        p.R(x - 55, -80, x + 55, 70, BLUE, (225, 238, 252))
        p.E(x, -20, 25, 28, INK, SKIN, 4)
        p.ARC(x, 70, 45, 40, 180, 360, BLUE, 5, LB)


@scene('chứng chỉ ngoại ngữ', ['chung chi', 'topik', 'tocfl', 'ielts', 'chung chi ngoai ngu', 'chung chi tieng'])
def _(p):
    p.R(-190, -110, 190, 110, ORANGE, (253, 245, 225))
    p.R(-170, -90, 170, 90, ORANGE, None, 3)
    p.T('CHỨNG CHỈ', 0, -55, 44, ORANGE)
    p.L([(-110, 0), (110, 0)], GREY, 4, 1)
    p.L([(-80, 30), (80, 30)], GREY, 4, 1)
    p.E(110, 75, 30, 30, RED, LR, 5)
    p.L([(95, 100), (85, 150)], RED, 5, 1)
    p.L([(125, 100), (135, 150)], RED, 5, 1)


@scene('tờ khai thông tin', ['to khai', 'khai thong tin', 'dien don', 'mau don', 'form'])
def _(p):
    p.R(-140, -160, 140, 170, INK, WHITE)
    p.T('TỜ KHAI', 0, -125, 36, BLUE)
    for i in range(5):
        y = -70 + i * 50
        p.L([(-110, y), (-40, y)], GREY, 4, 1)
        p.R(-25, y - 18, 110, y + 12, GREY, (245, 248, 255), 3)
    p.L([(-20, -55), (90, -60)], BLUE, 4, 4)


@scene('checklist hồ sơ', ['checklist', 'danh sach', 'can chuan bi', 'kiem tra ho so', 'du giay to'])
def _(p):
    clipboard(p, -60, 20, 1.2, 4, 3)
    p.E(170, 50, 60, 60, GREEN, LG)
    p.L([(140, 50), (163, 75), (205, 25)], GREEN, 12, 1)


@scene('người ký đơn', ['ky don', 'ky ten', 'ky hop dong', 'cam ket'])
def _(p):
    p.R(-170, -30, 170, 160, INK, WHITE)
    for i in range(3):
        p.L([(-140, 0 + i * 35), (140, 0 + i * 35)], GREY, 4, 1)
    p.L([(-40, 125), (40, 110), (60, 135), (110, 115)], BLUE, 5, 6)
    p.L([(100, 60), (200, -80)], ORANGE, 14, 1)
    p.L([(100, 60), (92, 80)], INK, 8, 1)
    p.E(215, -100, 40, 35, INK, SKIN)


@scene('laptop đăng ký online', ['dang ky online', 'nop online', 'website', 'truc tuyen', 'dang ky'])
def _(p):
    laptop(p, 0, 120, 1.7, 'form')
    p.L([(120, 40), (150, 85), (135, 85), (150, 115)], INK, 4, 1)


@scene('hồ sơ đã hoàn thành', ['hoan thanh', 'hoan tat', 'xong ho so', 'da xong'])
def _(p):
    doc(p, -40, 20, 1.6, INK, WHITE, 5, 'HỒ SƠ')
    stamp(p, 40, 50, 'ĐÃ HOÀN THÀNH', GREEN, 0.9, -12)


# --- 3. Visa
@scene('visa trong hộ chiếu', ['visa', 'dan visa', 'dau visa', 'co visa'])
def _(p):
    passport(p, 0, 10, 1.9, open_=True, visa=True)


@scene('đại sứ quán', ['dai su quan', 'lanh su', 'lanh su quan', 'cuc xuat nhap canh'])
def _(p):
    building(p, 0, 175, 1.15, GREY, 'embassy')


@scene('nộp hồ sơ tại quầy', ['nop tai quay', 'quay tiep nhan', 'nop ho so visa', 'nop ho so tai'])
def _(p):
    p.R(-60, 60, 280, 100, BROWN, LO)
    p.R(-60, -150, 280, -120, BLUE, LB)
    p.T('TIẾP NHẬN', 110, -135, 26, BLUE)
    person(p, 170, 60, 0.6, RED, 'hold', 'smile', 'long')
    person(p, -170, 195, 0.95, BLUE, 'present', 'smile')
    doc(p, -45, 40, 0.45)


@scene('phỏng vấn visa', ['phong van', 'phong van visa', 'tra loi phong van', 'luyen phong van'])
def _(p):
    desk(p, 0, 100, 0.9)
    person(p, -170, 190, 0.85, BLUE, 'down', 'worried')
    person(p, 170, 190, 0.85, GREY, 'present', 'neutral')
    bubble(p, -150, -150, 90, 34, '?', GREY, tail='right')
    bubble(p, 150, -150, 100, 34, 'Vì sao?', BLUE, tail='left')


@scene('dấu approved', ['do visa', 'duoc duyet', 'approved', 'dau duyet', 'thanh cong'])
def _(p):
    doc(p, -30, 10, 1.5, INK, WHITE, 5)
    stamp(p, 20, 40, 'APPROVED', GREEN, 1.3, -14)


@scene('dấu pending', ['pending', 'dang cho', 'cho ket qua', 'cho duyet', 'dang xet'])
def _(p):
    doc(p, -30, 10, 1.5, INK, WHITE, 5)
    stamp(p, 20, 40, 'PENDING', ORANGE, 1.3, -14)
    clock(p, 190, -110, 45)


@scene('vân tay sinh trắc', ['van tay', 'sinh trac', 'lay van tay', 'biometric'])
def _(p):
    p.R(-150, -120, 150, 140, GREY, (240, 240, 248))
    fingerprint(p, 0, 10, 1.6)


@scene('lịch hẹn phỏng vấn', ['lich hen', 'hen phong van', 'ngay hen', 'dat lich'])
def _(p):
    calendar(p, -60, 20, 1.5)
    clock(p, 170, 60, 60)


@scene('học sinh chờ visa', ['cho visa', 'cho ket qua', 'hoi hop', 'lo lang'])
def _(p):
    person(p, -60, 195, 1.0, BLUE, 'think', 'worried')
    clock(p, 140, -60, 60)
    phone(p, 150, 110, 0.8)


@scene('trao lại hộ chiếu', ['tra ho chieu', 'nhan ho chieu', 'nhan visa', 'nhan ket qua'])
def _(p):
    person(p, -160, 195, 0.9, BLUE, 'shake', 'smile')
    person(p, 160, 195, 0.9, GREY, 'shake', 'smile', lpose='down')
    passport(p, 0, -10, 0.6)


# --- 4. Chọn trường / ngành
@scene('học sinh trước nhiều trường', ['nhieu truong', 'chon truong', 'truong nao', 'danh sach truong'])
def _(p):
    person(p, 0, 195, 0.9, BLUE, 'think', 'worried')
    for x, y, c in ((-180, -110, RED), (-60, -150, BLUE), (60, -150, GREEN), (180, -110, ORANGE)):
        p.E(x, y, 42, 42, c, {RED: LR, BLUE: LB, GREEN: LG, ORANGE: LO}[c])
        p.PG([(x - 18, y + 10), (x, y - 15), (x + 18, y + 10)], c, None, 4, 1)


@scene('bảng so sánh 3 trường', ['so sanh truong', 'bang so sanh', 'so sanh 3', 'uu nhuoc diem'])
def _(p):
    x0, y0, w, h = table_grid(p, 0, 10, 1.15, 4, 4, ('', 'A', 'B', 'C'))
    for r in range(1, 4):
        for c in range(1, 4):
            ok = (r + c) % 3 != 0
            cx_, cy_ = x0 + c * w + w / 2, y0 + r * h + h / 2
            if ok:
                p.L([(cx_ - 12, cy_), (cx_ - 3, cy_ + 10), (cx_ + 14, cy_ - 10)], GREEN, 5, 1)
            else:
                p.L([(cx_ - 10, cy_ - 10), (cx_ + 10, cy_ + 10)], RED, 5, 1)


@scene('tòa nhà đại học', ['dai hoc', 'truong dai hoc', 'co so', 'khuon vien'])
def _(p):
    building(p, 0, 180, 1.3, BLUE, 'uni')


@scene('lớp học quốc tế', ['lop hoc', 'lop quoc te', 'ban quoc te', 'hoc chung'])
def _(p):
    board(p, 0, -100, 0.9, 'Hello!')
    for x, sh, hr in ((-180, BLUE, 'short'), (-60, RED, 'long'), (60, GREEN, 'short'), (180, ORANGE, 'long')):
        person(p, x, 195, 0.55, sh, 'down', 'smile', hr)
    p.L([(-260, 120), (260, 120)], BROWN, 6, 1)


@scene('biểu tượng các ngành', ['nganh hoc', 'chuyen nganh', 'nganh nao', 'kinh doanh', 'cong nghe thong tin', 'ky thuat', 'y te'])
def _(p):
    for x, y in ((-200, -40), (-70, -40), (60, -40), (190, -40), (-5, 110)):
        p.E(x, y, 58, 58, GREY, (245, 245, 245), 4)
    bars(p, -200, -5, 0.3, (40, 70, 110), (GREEN,))
    laptop(p, -70, 0, 0.45, 'check')
    p.T('ABC', 60, -40, 36, PURPLE)
    p.L([(175, -40), (205, -40)], RED, 10, 1)
    p.L([(190, -55), (190, -25)], RED, 10, 1)
    p.E(-5, 110, 25, 25, GREY, None, 8, 1.0)
    for i in range(6):
        a = i * math.pi / 3
        p.L([(-5 + 28 * math.cos(a), 110 + 28 * math.sin(a)), (-5 + 42 * math.cos(a), 110 + 42 * math.sin(a))], GREY, 8, 1)


@scene('sinh viên cầm sách suy nghĩ', ['suy nghi', 'can nhac', 'dinh huong', 'tuong lai'])
def _(p):
    a = person(p, -40, 195, 1.0, GREEN, 'think', 'neutral', 'long', lpose='hold')
    book(p, -60, 30, 0.6, BLUE, open_=False)
    bubble(p, 160, -120, 90, 50, None, GREY, think=True)
    lightbulb(p, 160, -115, 0.6)


@scene('bản đồ thành phố có trường', ['vi tri', 'ban do', 'thanh pho', 'o dau', 'dia chi'])
def _(p):
    p.R(-220, -150, 220, 150, GREY, (240, 245, 235), 4)
    p.L([(-220, -20), (220, 10)], GREY, 14, 2)
    p.L([(-60, -150), (-30, 150)], GREY, 14, 2)
    p.L([(100, -150), (130, 150)], GREY, 10, 2)
    p.R(-190, 40, -110, 120, GREEN, LG, 3)
    p.R(150, -130, 200, -60, BLUE, LB, 3)
    pin(p, 50, -40, 1.2, RED)


@scene('xem website tuyển sinh', ['tuyen sinh', 'thong tin tuyen sinh', 'web truong', 'tim hieu truong'])
def _(p):
    chair_desk_person(p, -150, 195, BLUE, 'web')
    mag(p, 180, -90, 0.8)


@scene('cố vấn tư vấn ngành', ['co van', 'tu van nganh', 'chon nganh', 'huong nghiep'])
def _(p):
    person(p, -150, 195, 0.9, BLUE, 'down', 'smile')
    person(p, 150, 195, 0.9, RED, 'present', 'smile', 'long')
    board(p, 0, -110, 0.6, 'IT? KD?')


@scene('cân học phí chất lượng việc làm', ['can bang', 'hoc phi chat luong', 'co hoi viec lam', 'dang tien'])
def _(p):
    scale_(p, 0, 30, 1.3, ('Học phí', 'Việc làm'))
    p.T('Chất lượng', 0, -150, 30, GREEN)


# --- 5. Chi phí, học bổng
@scene('túi tiền và mũ tốt nghiệp', ['dau tu', 'tien hoc', 'chi phi du hoc', 'dau tu cho con'])
def _(p):
    money_bag(p, -100, 40, 1.4)
    gradcap(p, 120, 10, 1.0)


@scene('nhận học bổng', ['nhan hoc bong', 'gianh hoc bong', 'duoc hoc bong', 'hoc bong'])
def _(p):
    person(p, -80, 195, 1.0, BLUE, 'raise', 'wow')
    p.R(40, -40, 240, 60, GREEN, LG)
    p.T('HỌC BỔNG', 140, 10, 36, GREEN)
    star(p, 200, -110, 28)
    star(p, 70, -120, 18)


@scene('giảm học phí', ['giam hoc phi', 'mien giam', 'uu dai', 'giam'])
def _(p):
    p.PG([(-200, -60), (40, -60), (110, 10), (40, 80), (-200, 80)], RED, LR)
    p.E(-160, 10, 14, 14, RED, WHITE, 4)
    p.T('-50%', -50, 10, 64, RED)
    p.L([(150, -100), (150, 90)], GREEN, 10, 1)
    p.L([(110, 40), (150, 90), (190, 40)], GREEN, 10, 1)


@scene('biểu đồ chi phí', ['bieu do chi phi', 'chi phi tung khoan', 'tong chi phi', 'chi phi'])
def _(p):
    bars(p, 0, 160, 1.3, (80, 160, 120, 60), (BLUE, ORANGE, GREEN, RED))


@scene('học phí ký túc xá sinh hoạt phí', ['hoc phi', 'ky tuc xa', 'sinh hoat phi', 'cac khoan phi', 'tien an o'])
def _(p):
    for x, lab, c, f in ((-180, 'Học phí', BLUE, LB), (0, 'Ký túc xá', ORANGE, LO), (180, 'Sinh hoạt', GREEN, LG)):
        p.R(x - 80, -60, x + 80, 60, c, f)
        p.T(lab, x, -25, 28, c)
        coin(p, x, 25, 20)


@scene('tính toán chi phí', ['tinh toan', 'du tru', 'ke hoach tai chinh', 'bao nhieu tien', 'tinh chi phi'])
def _(p):
    person(p, -190, 195, 0.8, PURPLE, 'down', 'neutral')
    person(p, -90, 195, 0.65, BLUE, 'down', 'smile')
    p.R(60, -110, 220, 110, INK, (230, 235, 240))
    p.R(80, -90, 200, -40, GREEN, LG, 4)
    for r in range(3):
        for c in range(3):
            p.R(85 + c * 40, -25 + r * 40, 115 + c * 40, 5 + r * 40, GREY, WHITE, 3)


@scene('học bổng toàn phần', ['toan phan', 'hoc bong toan phan', '100%', 'mien phi hoan toan'])
def _(p):
    trophy(p, -120, 30, 1.6)
    p.T('100%', 120, 0, 80, GREEN)
    star(p, 120, -110, 26)


@scene('học bổng bán phần', ['ban phan', 'hoc bong ban phan', '50%', 'mot phan'])
def _(p):
    p.E(-100, 20, 100, 100, ORANGE, None)
    p.PG([(-100, 20)] + [(-100 + 100 * math.cos(a), 20 + 100 * math.sin(a)) for a in np.linspace(-math.pi / 2, math.pi / 2, 20)],
         ORANGE, LO)
    p.T('50%', 130, 20, 80, ORANGE)


@scene('ống tiết kiệm', ['tiet kiem', 'ong heo', 'de danh', 'so tiet kiem', 'tich luy tien'])
def _(p):
    piggy(p, 0, 70, 1.6)
    coin(p, 0, -100, 26)
    p.L([(0, -60), (0, -30)], ORANGE, 4, 1)


@scene('bảng chi tiêu hàng tháng', ['chi tieu', 'hang thang', 'moi thang', 'sinh hoat phi hang thang'])
def _(p):
    x0, y0, w, h = table_grid(p, 0, 0, 1.2, 5, 2, ('Khoản', 'Tiền'))
    for r, lab in enumerate(('Nhà', 'Ăn', 'Đi lại', 'Khác')):
        p.T(lab, x0 + w / 2, y0 + (r + 1) * h + h / 2, 24, INK)
        coin(p, x0 + w * 1.5, y0 + (r + 1) * h + h / 2, 12)


# --- 6. Ngôn ngữ
@scene('học tiếng anh', ['tieng anh', 'ielts', 'toeic', 'english'])
def _(p):
    board(p, 80, -60, 0.9, 'A B C')
    person(p, -180, 195, 0.85, BLUE, 'raise', 'smile')


@scene('học tiếng trung', ['tieng trung', 'tieng hoa', 'tocfl', 'hsk', 'chu han'])
def _(p):
    p.R(-60, -150, 240, 40, BROWN, (45, 80, 60))
    hanzi(p, 90, -55, 1.0, WHITE)
    person(p, -180, 195, 0.85, RED, 'present', 'smile', 'long')


@scene('học tiếng hàn', ['tieng han', 'topik', 'han ngu', 'hoc tieng han'])
def _(p):
    p.R(-90, -150, 260, 40, BROWN, (45, 80, 60))
    hangul(p, 85, -55, 1.1, WHITE)
    person(p, -190, 195, 0.85, BLUE, 'present', 'smile')


@scene('giáo viên dạy online', ['hoc online', 'day online', 'lop online', 'hoc truc tuyen', 'zoom'])
def _(p):
    laptop(p, 0, 140, 1.8, 'video')
    bubble(p, 170, -120, 70, 30, 'Hi!', BLUE, tail='left')


@scene('tai nghe laptop', ['tai nghe', 'luyen nghe', 'nghe hieu'])
def _(p):
    laptop(p, -60, 140, 1.3, 'web')
    headphones(p, 170, -30, 1.3)


@scene('thẻ từ vựng', ['tu vung', 'flashcard', 'the tu', 'hoc tu moi'])
def _(p):
    for i, (x, y, a, c) in enumerate(((-130, 10, 'Xin chào', BLUE), (20, -30, '안녕', RED), (160, 20, '你好', GREEN))):
        f = {BLUE: LB, RED: LR, GREEN: LG}[c]
        p.R(x - 85, y - 55, x + 85, y + 55, c, f)
    p.T('Xin chào', -130, 10, 30, BLUE)
    hangul(p, 20, -30, 0.3, RED)
    hanzi(p, 160, 20, 0.5, GREEN)


@scene('bảng chữ cái tiếng hàn', ['bang chu cai', 'chu han quoc', 'hangul', 'bang chu'])
def _(p):
    p.R(-230, -120, 230, 120, BROWN, (45, 80, 60))
    hangul(p, 0, -20, 1.4, WHITE)


@scene('hội thoại', ['hoi thoai', 'giao tiep', 'noi chuyen', 'tro chuyen'])
def _(p):
    person(p, -170, 195, 0.85, BLUE, 'present', 'smile')
    person(p, 170, 195, 0.85, RED, 'wave', 'smile', 'long')
    bubble(p, -110, -150, 80, 35, 'Hi!', BLUE, tail='left')
    bubble(p, 110, -110, 80, 35, 'Xin chào!', RED, tail='right')


@scene('luyện phỏng vấn', ['luyen phong van', 'tap phong van', 'phong van tieng', 'chuan bi phong van'])
def _(p):
    person(p, -150, 195, 0.9, BLUE, 'present', 'smile')
    person(p, 150, 195, 0.9, GREEN, 'hold', 'neutral', 'long')
    p.R(110, 15, 190, 75, GREY, WHITE, 3)
    bubble(p, -40, -150, 120, 34, 'Tôi muốn...', BLUE, tail='left')


@scene('lịch học mỗi ngày', ['lich hoc', 'moi ngay', 'thoi gian bieu', 'gio hoc'])
def _(p):
    clock(p, -120, 0, 100)
    calendar(p, 140, 20, 1.1)


# --- 7. Chuẩn bị lên đường
@scene('chuẩn bị vali', ['chuan bi vali', 'soan do', 'xep do', 'dong goi'])
def _(p):
    p.R(-200, 40, 200, 150, ORANGE, LO)
    p.PG([(-200, 40), (-170, -60), (170, -60), (200, 40)], ORANGE, (253, 235, 205))
    p.R(-150, 60, -60, 130, BLUE, LB, 4)
    p.R(-40, 70, 60, 130, RED, LR, 4)
    book(p, 120, 95, 0.5, GREEN, open_=False)


@scene('cân hành lý', ['can hanh ly', 'can nang', 'qua can', 'ky lo', '23kg'])
def _(p):
    p.R(-140, 120, 140, 160, GREY, LGR)
    p.R(-40, 60, 40, 110, INK, WHITE, 4)
    p.T('23kg', 0, 85, 30, RED)
    suitcase(p, 0, 120, 1.1, BLUE)


@scene('vé máy bay', ['ve may bay', 'dat ve', 'mua ve'])
def _(p):
    ticket(p, 0, 0, 2.2)


@scene('danh sách đồ cần mang', ['mang gi', 'do can mang', 'danh sach do', 'mang theo'])
def _(p):
    clipboard(p, -80, 20, 1.2, 4, 2)
    suitcase(p, 160, 150, 0.9)


@scene('ổ cắm quần áo thuốc', ['o cam', 'quan ao', 'thuoc men', 'do dung ca nhan', 'thuoc'])
def _(p):
    p.R(-230, -40, -110, 60, GREY, LGR)
    p.DOT(-190, 10, 8)
    p.DOT(-150, 10, 8)
    p.PG([(-40, -70), (40, -70), (90, -30), (60, 0), (40, -20), (40, 90), (-40, 90), (-40, -20), (-60, 0), (-90, -30)], BLUE, LB)
    pill(p, 170, 0, 1.2)
    pill(p, 190, 60, 0.9)


@scene('tạm biệt gia đình', ['tam biet', 'chia tay', 'gia dinh', 'xa nha', 'bo me'])
def _(p):
    person(p, -200, 195, 0.9, PURPLE, 'wave', 'smile')
    person(p, -100, 195, 0.85, RED, 'wave', 'smile', 'long')
    person(p, 140, 195, 0.9, BLUE, 'wave', 'smile', backpack=True)
    heart(p, 20, -110, 30)


@scene('check-in sân bay', ['check in', 'quay check', 'lam thu tuc', 'gui hanh ly'])
def _(p):
    p.R(-40, 40, 270, 90, BLUE, LB)
    p.R(-40, -150, 270, -120, BLUE, LB)
    p.T('CHECK-IN', 115, -135, 26, BLUE)
    person(p, 150, 40, 0.55, GREY, 'down', 'smile', 'long')
    person(p, -170, 195, 0.9, BLUE, 'pull', 'smile')
    suitcase(p, -60, 195, 0.6)


@scene('thủ tục xuất cảnh', ['xuat canh', 'thu tuc xuat canh', 'hai quan', 'cua khau'])
def _(p):
    p.R(30, -40, 230, 100, GREY, LGR)
    p.R(30, -150, 230, -40, GREY, (240, 240, 245))
    p.T('XUẤT CẢNH', 130, -95, 28, INK)
    person(p, -130, 195, 0.9, BLUE, 'present', 'smile', backpack=True)
    passport(p, -25, 40, 0.4)


@scene('máy bay cất cánh', ['cat canh', 'may bay cat canh', 'bay roi', 'len may bay'])
def _(p):
    p.L([(-260, 160), (260, 160)], GREY, 5, 2)
    a = math.radians(-20)
    plane(p, 40, 10, 1.4)
    cloud(p, -170, -110, 0.8)
    cloud(p, 190, -140, 0.6)


@scene('ghế trên máy bay', ['ghe may bay', 'tren may bay', 'chuyen bay dai', 'ngoi may bay'])
def _(p):
    for x in (-150, 0, 150):
        p.PG([(x - 55, 150), (x - 55, -60), (x - 40, -120), (x + 40, -120), (x + 55, -60), (x + 55, 150)], BLUE, LB)
        p.R(x - 60, 60, x + 60, 100, BLUE, (180, 200, 240), 4)
    p.E(230, -60, 35, 55, GREY, (235, 245, 255), 6)


# --- 8. Cuộc sống
@scene('ký túc xá', ['ky tuc xa', 'ktx', 'cho o', 'nha o sinh vien'])
def _(p):
    building(p, -40, 185, 1.0, ORANGE, 'dorm')
    person(p, 160, 195, 0.75, BLUE, 'wave', 'smile', backpack=True)


@scene('phòng trọ sinh viên', ['phong tro', 'thue nha', 'thue phong', 'nha tro'])
def _(p):
    p.R(-230, -150, 230, 160, BROWN, (250, 245, 235), 4)
    p.R(-200, 60, -20, 130, BLUE, LB)
    p.R(-200, 30, -150, 60, BLUE, WHITE, 3)
    desk(p, 120, 60, 0.6)
    laptop(p, 120, 48, 0.4)
    p.R(40, -120, 180, -30, BLUE, (225, 238, 252), 4)
    p.L([(110, -120), (110, -30)], BLUE, 3, 1)


@scene('căng tin trường', ['cang tin', 'an trua', 'nha an', 'bua an'])
def _(p):
    p.R(-200, 20, 200, 50, BROWN, LO)
    food(p, 'com', -110, 0, 0.9)
    food(p, 'mi', 30, 0, 0.9)
    food(p, 'kimchi', 150, 0, 0.7)
    p.T('CĂNG TIN', 0, -140, 40, ORANGE)


@scene('thư viện', ['thu vien', 'doc sach', 'muon sach', 'tu hoc'])
def _(p):
    for r in range(3):
        p.L([(-230, -100 + r * 90), (230, -100 + r * 90)], BROWN, 7, 1)
        for i in range(12):
            c = (BLUE, RED, GREEN, ORANGE)[(i + r) % 4]
            x = -220 + i * 37
            h = 55 + (i * 7 + r * 5) % 20
            p.R(x, -100 + r * 90 - h, x + 26, -100 + r * 90, c, {BLUE: LB, RED: LR, GREEN: LG, ORANGE: LO}[c], 3)


@scene('lớp học', ['lop hoc', 'gio hoc', 'buoi hoc', 'tren lop'])
def _(p):
    board(p, 40, -90, 1.0, 'Hello!')
    person(p, -200, 195, 0.85, RED, 'present', 'smile', 'long')
    for x in (-40, 80, 200):
        person(p, x, 195, 0.5, BLUE, 'down', 'smile')


@scene('sinh viên nấu ăn', ['nau an', 'tu nau', 'bep', 'nau com'])
def _(p):
    p.R(-60, 60, 240, 100, GREY, LGR)
    p.ARC(100, 50, 70, 35, 0, 180, INK, 6, (200, 205, 210))
    p.L([(170, 50), (240, 30)], INK, 8, 1)
    for i in range(3):
        p.L([(70 + i * 30, 20), (75 + i * 30, -20)], GREY, 3, 3)
    person(p, -170, 195, 0.9, BLUE, 'present', 'smile')


@scene('đi siêu thị', ['sieu thi', 'mua sam', 'di cho', 'mua do'])
def _(p):
    building(p, 120, 175, 0.9, GREEN, 'shop')
    person(p, -200, 195, 0.8, BLUE, 'pull', 'smile', 'long')
    cart(p, -70, 190, 0.9)


@scene('xe bus tàu điện', ['xe bus', 'tau dien', 'tau dien ngam', 'di lai', 'phuong tien cong cong', 'metro'])
def _(p):
    train(p, -20, 0, 1.1)
    bus(p, 120, 170, 0.6)


@scene('giặt quần áo', ['giat do', 'giat quan ao', 'may giat', 'don dep'])
def _(p):
    washer(p, -80, 170, 1.3)
    p.R(90, 60, 230, 170, BLUE, LB)
    p.PG([(110, 60), (150, 20), (180, 40), (210, 60)], RED, LR, 4, 2)


@scene('gọi video về nhà', ['goi video', 'goi ve nha', 'video call', 'goi cho gia dinh', 'lien lac gia dinh'])
def _(p):
    p.R(-110, -150, 110, 150, INK, (230, 235, 245))
    p.E(0, -50, 40, 40, INK, SKIN, 5)
    p.ARC(0, 80, 70, 60, 180, 360, PURPLE, 6, LP)
    heart(p, 170, -90, 30)
    heart(p, 200, -20, 18)


# --- 9. Học tập
@scene('giơ tay phát biểu', ['phat bieu', 'gio tay', 'dat cau hoi', 'tich cuc'])
def _(p):
    person(p, -60, 195, 1.0, BLUE, 'raise', 'smile')
    bubble(p, 150, -120, 80, 40, '!', ORANGE, tail='left')


@scene('học nhóm quốc tế', ['hoc nhom', 'ban quoc te', 'ban be quoc te', 'lam viec nhom'])
def _(p):
    p.R(-200, 60, 200, 90, BROWN, LO)
    for x, sh, hr in ((-150, BLUE, 'short'), (-50, RED, 'long'), (50, GREEN, 'short'), (150, ORANGE, 'long')):
        person(p, x, 60, 0.55, sh, 'down', 'smile', hr)
    book(p, 0, 50, 0.5)


@scene('thuyết trình', ['thuyet trinh', 'trinh bay', 'presentation', 'bao cao'])
def _(p):
    p.R(-40, -150, 240, 50, GREY, WHITE)
    bars(p, 100, 20, 0.5, (40, 70, 110, 150), (BLUE,))
    person(p, -170, 195, 0.95, RED, 'present', 'smile', 'long')


@scene('làm bài kiểm tra', ['bai kiem tra', 'thi', 'ky thi', 'lam bai thi', 'kiem tra'])
def _(p):
    p.R(-150, -150, 150, 160, INK, WHITE)
    p.T('A+', 90, -110, 50, RED)
    for i in range(4):
        y = -60 + i * 50
        p.E(-110, y, 12, 12, GREY, None, 3)
        p.L([(-80, y), (100, y)], GREY, 4, 1)
    p.L([(-118, -60), (-110, -50), (-95, -72)], GREEN, 5, 1)
    p.L([(160, 120), (230, -60)], ORANGE, 12, 1)


@scene('phòng lab', ['phong lab', 'thi nghiem', 'thuc hanh', 'phong thi nghiem'])
def _(p):
    flask(p, 120, 60, 1.6)
    person(p, -150, 195, 0.9, GREY, 'present', 'smile')


@scene('giáo viên giảng bài', ['giao vien', 'giang bai', 'giang vien', 'thay co'])
def _(p):
    board(p, 60, -80, 1.0, '1 + 4')
    person(p, -190, 195, 0.95, PURPLE, 'present', 'smile', 'long')


@scene('nộp bài trên máy tính', ['nop bai', 'bai tap', 'deadline', 'nop online'])
def _(p):
    laptop(p, -30, 140, 1.6, 'check')
    clock(p, 200, -90, 50)


@scene('dự án nhóm', ['du an', 'du an nhom', 'project', 'nhom'])
def _(p):
    p.R(-150, -150, 150, 30, GREY, WHITE)
    for i, (x, y, c, f) in enumerate(((-90, -100, ORANGE, LY), (0, -100, BLUE, LB), (90, -100, GREEN, LG), (-45, -30, RED, LR), (45, -30, ORANGE, LY))):
        p.R(x - 35, y - 28, x + 35, y + 28, c, f, 3)
    person(p, -210, 195, 0.65, BLUE, 'present', 'smile')
    person(p, 210, 195, 0.65, RED, 'wave', 'smile', 'long')


@scene('sinh viên trong thư viện', ['on bai', 'hoc bai', 'chuan bi thi', 'cham hoc'])
def _(p):
    chair_desk_person(p, -100, 195, GREEN, 'web', 'neutral', 'long')
    for i in range(4):
        c = (BLUE, RED, ORANGE, GREEN)[i]
        p.R(160 + i * 25, -140, 182 + i * 25, -60, c, {BLUE: LB, RED: LR, GREEN: LG, ORANGE: LO}[c], 3)
    p.L([(150, -60), (270, -60)], BROWN, 6, 1)


@scene('lễ tốt nghiệp', ['le tot nghiep', 'tot nghiep', 'nhan bang', 'ra truong'])
def _(p):
    person(p, -60, 195, 1.0, INK, 'raise', 'smile', hat='grad')
    diploma(p, 140, 0, 0.8)
    star(p, 150, -120, 26)


# --- 10. Làm thêm
@scene('làm thêm quán cà phê', ['quan ca phe', 'cafe', 'ca phe', 'pha che', 'phuc vu'])
def _(p):
    p.R(-40, 40, 260, 80, BROWN, LO)
    food(p, 'ca phe', 60, 10, 0.7)
    food(p, 'tra sua', 170, 15, 0.6)
    person(p, -150, 195, 0.95, BROWN, 'present', 'smile', 'long')


@scene('làm thêm cửa hàng tiện lợi', ['cua hang tien loi', 'tien loi', 'thu ngan', 'ban hang'])
def _(p):
    building(p, 90, 175, 1.0, GREEN, 'shop')
    person(p, -170, 195, 0.9, GREEN, 'wave', 'smile')


@scene('thực tập văn phòng', ['thuc tap', 'van phong', 'cong ty', 'di lam'])
def _(p):
    building(p, 150, 190, 0.8, BLUE, 'office')
    chair_desk_person(p, -150, 195, BLUE, 'chart')


@scene('lịch làm việc', ['lich lam', 'ca lam', 'gio lam', 'so gio lam', 'gio mot tuan'])
def _(p):
    calendar(p, -80, 20, 1.4)
    clock(p, 150, 0, 70)


@scene('sinh viên nhận lương', ['nhan luong', 'luong', 'thu nhap', 'tien luong', 'kiem tien'])
def _(p):
    person(p, -100, 195, 1.0, BLUE, 'raise', 'wow')
    money(p, 130, 0, 1.0)


@scene('cân bằng học và làm', ['vua hoc vua lam', 'can bang', 'hoc va lam', 'sap xep thoi gian'])
def _(p):
    scale_(p, 0, 40, 1.3, ('Học', 'Làm'))
    book(p, -170, -35, 0.45, BLUE, open_=False)
    p.R(150, -55, 215, -15, BROWN, LO, 4)


@scene('viết cv', ['cv', 'so yeu ly lich', 'ho so xin viec'])
def _(p):
    doc(p, -30, 20, 1.6, BLUE, WHITE, 4, 'CV')
    p.E(-60, -50, 18, 18, INK, SKIN, 4)
    p.L([(120, 90), (220, -70)], ORANGE, 12, 1)


@scene('phỏng vấn part-time', ['part time', 'xin viec', 'phong van xin viec', 'tim viec'])
def _(p):
    desk(p, 0, 100, 0.9)
    person(p, -170, 190, 0.85, BLUE, 'shake', 'smile')
    person(p, 170, 190, 0.85, GREY, 'shake', 'smile')
    doc(p, 0, 70, 0.3, BLUE, WHITE, 2, None)


@scene('thẻ nhân viên', ['the nhan vien', 'nhan vien'])
def _(p):
    p.L([(0, -170), (0, -60)], RED, 5, 1)
    id_card(p, 0, 20, 1.8)


@scene('tích lũy kinh nghiệm', ['kinh nghiem', 'tich luy', 'ky nang', 'phat trien ban than'])
def _(p):
    for i in range(4):
        p.R(-200 + i * 100, 150 - i * 60, -100 + i * 100, 160, BLUE, LB)
    person(p, 150, -40, 0.7, BLUE, 'raise', 'smile')
    star(p, 230, -170, 22)


# --- 11. Khó khăn
@scene('nhớ nhà', ['nho nha', 'nho gia dinh', 'nho que'])
def _(p):
    person(p, -80, 195, 1.0, BLUE, 'think', 'sad')
    bubble(p, 140, -100, 110, 75, None, GREY, think=True)
    building(p, 140, -55, 0.4, ORANGE, 'house')


@scene('sốc văn hóa', ['soc van hoa', 'van hoa khac', 'bo ngo', 'chua quen'])
def _(p):
    person(p, -80, 195, 1.0, BLUE, 'raise', 'wow')
    p.T('!?', 130, -90, 90, ORANGE)


@scene('khó khăn ngôn ngữ', ['kho khan ngon ngu', 'khong hieu', 'bat dong ngon ngu', 'rao can ngon ngu'])
def _(p):
    person(p, -160, 195, 0.9, BLUE, 'think', 'worried')
    person(p, 160, 195, 0.9, RED, 'present', 'neutral', 'long')
    bubble(p, 100, -130, 90, 35, '@#%?', RED, tail='right')
    p.T('???', -150, -150, 50, GREY)


@scene('áp lực học tập', ['ap luc hoc', 'ap luc', 'qua tai', 'cang thang'])
def _(p):
    for i in range(5):
        c = (BLUE, RED, GREEN, ORANGE, PURPLE)[i]
        p.R(60 - i * 6, 160 - i * 40, 230 - i * 6, 195 - i * 40, c, {BLUE: LB, RED: LR, GREEN: LG, ORANGE: LO, PURPLE: LP}[c], 4)
    person(p, -110, 195, 1.0, BLUE, 'think', 'worried')


@scene('áp lực tài chính', ['ap luc tai chinh', 'thieu tien', 'het tien', 'kho khan tai chinh'])
def _(p):
    person(p, -100, 195, 1.0, BLUE, 'think', 'worried')
    p.PG([(80, -40), (200, -40), (210, 60), (70, 60)], BROWN, LO)
    p.T('0$', 140, 10, 46, RED)


@scene('cô đơn', ['co don', 'buon', 'le loi'])
def _(p):
    person(p, 0, 195, 0.9, BLUE, 'down', 'sad')
    cloud(p, 0, -140, 1.0, rain=True)


@scene('trễ deadline', ['tre deadline', 'tre han', 'qua han', 'muon'])
def _(p):
    clock(p, -80, -10, 100, RED)
    calendar(p, 160, 30, 0.9)
    p.T('!', -80, 140, 60, RED)


@scene('ốm ở nước ngoài', ['bi om', 'om dau', 'benh', 'om o nuoc ngoai'])
def _(p):
    p.R(-230, 80, 120, 130, BLUE, LB)
    p.E(-180, 50, 35, 35, INK, SKIN, 5)
    p.R(-140, 30, 110, 85, BLUE, (225, 238, 252))
    thermometer(p, 200, -40, 1.2)
    pill(p, 180, 110, 0.9)


@scene('không quen đồ ăn', ['khong quen do an', 'do an', 'mon an', 'an uong', 'am thuc'])
def _(p):
    person(p, -150, 195, 0.9, BLUE, 'think', 'worried')
    food(p, 'kimchi', 100, 40, 1.2)
    p.T('?', 110, -80, 60, ORANGE)


@scene('lạc đường', ['lac duong', 'lac', 'khong biet duong', 'tim duong'])
def _(p):
    person(p, -110, 195, 1.0, BLUE, 'think', 'worried', backpack=True)
    p.L([(130, 190), (130, -120)], BROWN, 8, 1)
    p.PG([(130, -110), (240, -110), (265, -85), (240, -60), (130, -60)], GREEN, LG)
    p.PG([(130, -40), (30, -40), (5, -15), (30, 10), (130, 10)], BLUE, LB)


# --- 12. Hỗ trợ
@scene('trung tâm hỗ trợ', ['ho tro', 'dong hanh', 'trung tam ho tro', 'giup do', 'tro giup'])
def _(p):
    building(p, -100, 180, 0.8, BLUE, 'house')
    p.PG([(120, -100), (250, -60), (240, 60), (120, 120), (0, 60), (-10, -60)], BLUE, LB)
    p.L([(60, 0), (110, 50), (190, -40)], GREEN, 12, 1)


@scene('bạn bè giúp đỡ', ['ban be', 'giup do nhau', 'ban giup', 'than thien'])
def _(p):
    person(p, -90, 195, 0.95, BLUE, 'shake', 'smile')
    person(p, 90, 195, 0.95, ORANGE, 'shake', 'smile', 'long')
    heart(p, 0, -130, 30)


@scene('giáo viên hướng dẫn', ['huong dan', 'giao vien huong dan', 'nguoi huong dan', 'chi dan'])
def _(p):
    person(p, -150, 195, 1.0, PURPLE, 'present', 'smile')
    person(p, 120, 195, 0.75, BLUE, 'down', 'smile', backpack=True)
    lightbulb(p, 120, -130, 0.6)


@scene('hội sinh viên việt nam', ['hoi sinh vien', 'cong dong', 'nguoi viet'])
def _(p):
    flag(p, 'viet nam', 0, -110, 0.6)
    for x, sh, hr in ((-180, BLUE, 'short'), (-60, RED, 'long'), (60, GREEN, 'short'), (180, ORANGE, 'long')):
        person(p, x, 195, 0.6, sh, 'wave', 'smile', hr)


@scene('tư vấn tâm lý', ['tam ly', 'tu van tam ly', 'chia se', 'tam su'])
def _(p):
    person(p, -150, 195, 0.9, BLUE, 'down', 'sad')
    person(p, 150, 195, 0.9, GREEN, 'present', 'smile', 'long')
    heart(p, 0, -110, 35)


@scene('kế hoạch học tập', ['ke hoach hoc tap', 'ke hoach', 'muc tieu', 'study plan'])
def _(p):
    clipboard(p, -80, 20, 1.2, 3, 1)
    p.E(150, -20, 70, 70, RED, LR)
    p.E(150, -20, 42, 42, RED, WHITE)
    p.DOT(150, -20, 14, RED)
    p.L([(240, -110), (155, -25)], BROWN, 6, 1)


@scene('quản lý chi tiêu', ['quan ly chi tieu', 'quan ly tien', 'chi tieu hop ly'])
def _(p):
    phone(p, -110, 10, 2.2)
    bars(p, -110, 70, 0.28, (50, 80, 120), (GREEN,))
    piggy(p, 140, 60, 1.0)


@scene('ứng dụng bản đồ', ['ung dung ban do', 'google map', 'chi duong', 'dinh vi'])
def _(p):
    phone(p, 0, 10, 3.0)
    p.L([(-55, 80), (-20, 20), (30, 10), (45, -60)], BLUE, 6, 5)
    pin(p, 45, -60, 0.7, RED)


@scene('gọi điện nhờ hỗ trợ', ['goi dien', 'hotline', 'goi ho tro', 'lien he', 'sdt'])
def _(p):
    person(p, -60, 195, 1.0, BLUE, 'phone', 'smile')
    bubble(p, 160, -110, 90, 40, 'Alô!', GREEN, tail='left')


@scene('checklist giải quyết vấn đề', ['giai quyet', 'cach giai quyet', 'giai phap', 'xu ly'])
def _(p):
    clipboard(p, -60, 20, 1.2, 3, 3)
    lightbulb(p, 170, -50, 0.9)


# --- 13. Quốc gia
@scene('quốc kỳ hàn quốc', ['co han quoc', 'quoc ky han', 'han quoc'])
def _(p):
    flag(p, 'han', 0, -20, 1.6)


@scene('quốc kỳ đài loan', ['co dai loan', 'quoc ky dai loan', 'dai loan'])
def _(p):
    flag(p, 'dai loan', 0, -20, 1.6)


@scene('cờ việt nam', ['viet nam', 'co viet nam', 'que huong'])
def _(p):
    flag(p, 'viet nam', 0, -20, 1.6)


@scene('bản đồ hàn quốc', ['ban do han', 'seoul', 'busan', 'nuoc han', 'xu han'])
def _(p):
    map_shape(p, 'han', -40, -10, 1.1, GREEN, LG)
    p.T('Seoul', 110, -40, 34, RED)
    p.L([(60, -40), (-65, -32)], RED, 3, 2)


@scene('bản đồ đài loan', ['ban do dai loan', 'dai bac', 'cao hung', 'dai trung', 'xu dai'])
def _(p):
    map_shape(p, 'dai loan', -40, 0, 1.2, GREEN, LG)
    p.T('Đài Bắc', 120, -130, 34, RED)


@scene('việt nam sang hàn', ['tu viet nam sang han', 'viet nam han quoc', 'bay sang han'])
def _(p):
    map_shape(p, 'viet nam', -170, 20, 0.8, RED, LR)
    map_shape(p, 'han', 170, -10, 0.7, GREEN, LG)
    p.L([(-150, -60), (0, -150), (140, -60)], ORANGE, 5, 12)
    plane(p, 0, -150, 0.4)


@scene('việt nam sang đài loan', ['tu viet nam sang dai loan', 'viet nam dai loan', 'bay sang dai loan'])
def _(p):
    map_shape(p, 'viet nam', -170, 20, 0.8, RED, LR)
    map_shape(p, 'dai loan', 170, 20, 0.8, GREEN, LG)
    p.L([(-150, -60), (0, -150), (150, -60)], ORANGE, 5, 12)
    plane(p, 0, -150, 0.4)


@scene('biểu tượng hàn quốc', ['bieu tuong han', 'cung dien', 'gyeongbok', 'kpop', 'han phuc'])
def _(p):
    p.PG([(-200, -40), (-150, -110), (150, -110), (200, -40)], (40, 110, 90), (150, 210, 190))
    p.R(-150, -40, 150, 120, RED, LR)
    for x in (-110, -40, 40, 110):
        p.L([(x, -40), (x, 120)], RED, 8, 1)
    p.L([(-230, 120), (230, 120)], GREY, 6, 1)


@scene('biểu tượng đài loan', ['taipei 101', 'bieu tuong dai loan', 'thap 101', 'cho dem'])
def _(p):
    for i in range(8):
        w_ = 70 - i * 4
        p.PG([(-w_, 150 - i * 40), (w_, 150 - i * 40), (w_ - 10, 115 - i * 40), (-w_ + 10, 115 - i * 40)], TEAL, LT, 4, 1)
    p.L([(0, -170), (0, -230)], TEAL, 5, 1)


@scene('trường đại học tiêu biểu', ['truong tieu bieu', 'truong top', 'truong noi tieng', 'top'])
def _(p):
    building(p, 0, 175, 1.2, RED, 'uni')
    star(p, 0, -150, 26)


@scene('sinh viên ở hàn quốc', ['sinh vien han', 'cuoc song o han', 'du hoc sinh han'])
def _(p):
    skyline(p, 60, 180, 0.8)
    person(p, -190, 195, 0.85, BLUE, 'wave', 'smile', backpack=True)
    flag(p, 'han', 170, -150, 0.35)


@scene('sinh viên ở đài loan', ['sinh vien dai loan', 'cuoc song o dai loan', 'du hoc sinh dai loan'])
def _(p):
    skyline(p, 60, 180, 0.8)
    person(p, -190, 195, 0.85, RED, 'wave', 'smile', 'long', backpack=True)
    flag(p, 'dai loan', 170, -150, 0.35)


@scene('món ăn hàn quốc', ['mon han', 'kimchi', 'tokbokki', 'do an han'])
def _(p):
    food(p, 'kimchi', -140, 40, 1.2)
    food(p, 'com', 20, 40, 1.0)
    food(p, 'mi', 170, 40, 1.0)


@scene('món ăn đài loan', ['mon dai loan', 'tra sua', 'tra sua tran chau', 'banh bao', 'do an dai loan'])
def _(p):
    food(p, 'tra sua', -120, 40, 1.3)
    food(p, 'banh bao', 90, 60, 1.3)


@scene('tàu điện', ['tau dien', 'metro', 'tau dien ngam', 'tau cao toc'])
def _(p):
    train(p, 0, 60, 1.4)


@scene('thành phố hiện đại', ['thanh pho', 'hien dai', 'do thi', 'phat trien'])
def _(p):
    skyline(p, 0, 170, 1.0)
    cloud(p, -180, -150, 0.6)


@scene('cơ hội việc làm', ['co hoi viec lam', 'viec lam sau', 'tuong lai nghe nghiep', 'sau tot nghiep', 'dinh cu'])
def _(p):
    bars(p, -40, 160, 1.0, (60, 110, 170, 230), (GREEN,))
    p.L([(-160, 50), (-60, 0), (40, -60), (140, -150)], RED, 6, 3)
    p.L([(95, -150), (145, -155), (138, -105)], RED, 6, 1)
    p.R(160, 90, 260, 160, BROWN, LO, 5)
    p.L([(190, 90), (195, 65), (225, 65), (230, 90)], BROWN, 5, 1)


NAMES = [r[0] for r in _RAW]


def has(name):
    return E.norm(name) in _index()


def draw(name, cx, cy, h, color, seed):
    nm, keys, fn = _index()[E.norm(name)]
    p = Pen(cx, cy, h / 380.0, seed)
    fn(p)
    return p.items


def keywords():
    return {k: v[1] for k, v in _index().items()}
