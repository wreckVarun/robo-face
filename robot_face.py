"""
Robo Face - a glowing robot face whose expression you control.

Controls
  Click a button, or press its key     change expression (the face morphs smoothly)
      1 2 3 4 5 6 7 8 9 0              faces 1-10
      Q W E R T Y U I O P              faces 11-20
      Z X C V B                        faces 21-25
  Left / Right arrows                  previous / next expression
  Space                                blink
  A                                    toggle automatic blinking
  Esc                                  quit

Run:  python robot_face.py      (needs: pip install pygame)
"""
import math
import random

import pygame
import pygame.gfxdraw

WIN_W, WIN_H = 900, 810
DISP = pygame.Rect(140, 100, 620, 400)   # the face screen
SCREEN_RADIUS = 46
N = 96                                   # points per outline; every shape uses N so any two can morph
HALF = N // 2
MORPH_TIME = 0.45
BLINK_TIME = 0.16
EYE_X, EYE_Y = 150, -15                  # eye offset from face centre
MOUTH_Y = 70
KEYS = "1234567890qwertyuiopzxcvb"
NOSE_COL = (255, 140, 185)

PINK = (255, 185, 222)
HOT = (255, 120, 170)
MINT = (190, 255, 225)
LAV = (225, 190, 255)
RED = (255, 95, 140)
WHITE = (240, 235, 255)
BLUE = (110, 195, 255)
YELLOW = (255, 225, 130)
BLUSH = (255, 105, 160)


# ---------- small math helpers ----------

def lerp(a, b, t):
    return a + (b - a) * t


def lerp_pts(p, q, t):
    return [(lerp(x0, x1, t), lerp(y0, y1, t)) for (x0, y0), (x1, y1) in zip(p, q)]


def lerp_col(c0, c1, t):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c0, c1))


def scale_col(c, a):
    return tuple(max(0, min(255, int(v * a))) for v in c)


def ease_out_back(t, s=1.4):
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def smoothstep(t):
    return t * t * (3 - 2 * t)


def rotate(pts, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]


def move(pts, dx, dy):
    return [(x + dx, y + dy) for x, y in pts]


def resample(path, n=HALF):
    """n points spread along a polyline, keeping its corners."""
    segs = list(zip(path, path[1:]))
    lens = [math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in segs]
    counts = [max(1, int(round((n - 1) * ln / sum(lens)))) for ln in lens]
    while sum(counts) > n - 1:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n - 1:
        counts[counts.index(max(counts))] += 1
    pts = []
    for (p0, p1), k in zip(segs, counts):
        pts += [(lerp(p0[0], p1[0], j / k), lerp(p0[1], p1[1], j / k)) for j in range(k)]
    return pts + [path[-1]]


def chaikin(pts, rounds=3):
    """Round off the corners of an open polyline."""
    for _ in range(rounds):
        out = [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        pts = out + [pts[-1]]
    return pts


NOTHING = [(0.0, 4.0)] * N    # a polygon squashed to a point: used when a face has no tongue


# ---------- shape builders (each returns N points: top edge left->right, then bottom edge right->left) ----------

def ellipse(rx, ry, cx=0.0, cy=0.0):
    return [(cx + rx * math.cos(math.pi + 2 * math.pi * i / N),
             cy + ry * math.sin(math.pi + 2 * math.pi * i / N)) for i in range(N)]


def clipped_ellipse(rx, ry, y0, slope):
    """Ellipse with everything above the line y = y0 + slope*x shaved off (eyelids)."""
    return [(x, max(y, y0 + slope * x)) for x, y in ellipse(rx, ry)]


def arc_line(r, cx, cy, a0, a1):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / (HALF - 1)),
             cy + r * math.sin(a0 + (a1 - a0) * i / (HALF - 1))) for i in range(HALF)]


def curve(fn):
    """HALF points of a centreline; fn maps u in [0, 1] to (x, y)."""
    return [fn(i / (HALF - 1)) for i in range(HALF)]


def stroke(centerline, width, closed=False):
    """Turn a line of HALF points into a closed ribbon outline of N points."""
    m = len(centerline)
    top, bot = [], []
    for i, (x, y) in enumerate(centerline):
        if closed:
            x0, y0 = centerline[i - 1] if i > 0 else centerline[-2]
            x1, y1 = centerline[i + 1] if i < m - 1 else centerline[1]
        else:
            x0, y0 = centerline[max(i - 1, 0)]
            x1, y1 = centerline[min(i + 1, m - 1)]
        ln = math.hypot(x1 - x0, y1 - y0) or 1.0
        nx, ny = (y1 - y0) / ln * width / 2, -(x1 - x0) / ln * width / 2
        top.append((x + nx, y + ny))
        bot.append((x - nx, y - ny))
    return top + bot[::-1]


def line(x0, y0, x1, y1, width):
    return stroke(resample([(x0, y0), (x1, y1)]), width)


def dash(length, width, tilt=0.0, bow=0.0):
    c = curve(lambda u: (length * (u - 0.5), -bow * (1 - (2 * u - 1) ** 2)))
    return stroke(rotate(c, tilt), width)


def chevron(w, h, width):
    """'>' for the left eye (mirrored to '<' on the right)."""
    return stroke(resample([(-w / 2, -h / 2), (w / 2, 0), (-w / 2, h / 2)]), width)


def ring(ro, ri):
    outer = [(ro * math.cos(math.pi + 2 * math.pi * i / (HALF - 1)),
              ro * math.sin(math.pi + 2 * math.pi * i / (HALF - 1))) for i in range(HALF)]
    inner = [(x * ri / ro, y * ri / ro) for x, y in outer]
    return outer + inner[::-1]


def spiral(r_in, r_out, turns, width):
    c = curve(lambda u: (lerp(r_out, r_in, u) * math.cos(math.pi + turns * 2 * math.pi * u),
                         lerp(r_out, r_in, u) * math.sin(math.pi + turns * 2 * math.pi * u)))
    return stroke(c, width)


def heart_pts(s, cx=0.0, cy=0.0, n=N):
    pts = []
    for i in range(n):
        t = -math.pi / 2 + 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + s * x, cy + s * (y - 3)))
    return pts


def w_mouth(width, depth, thick=7):
    return stroke(curve(lambda u: (width * (u - 0.5),
                                   depth * abs(math.sin(math.pi * (2 * u - 1))) - depth / 2)), thick)


def smile(w, depth, thick):
    return stroke(curve(lambda u: (w * (u - 0.5), depth * (1 - (2 * u - 1) ** 2) - depth / 2)), thick)


def frown(w, depth, thick):
    return stroke(curve(lambda u: (w * (u - 0.5), depth * (2 * u - 1) ** 2 - depth / 2)), thick)


def wave(w, amp, waves, thick):
    return stroke(curve(lambda u: (w * (u - 0.5), amp * math.sin(2 * math.pi * waves * u))), thick)


def open_mouth(w, h):
    top = [(-w / 2 + w * i / (HALF - 1), -h / 3) for i in range(HALF)]
    bot = [(w / 2 * math.cos(math.pi * i / (HALF - 1)),
            -h / 3 + h * math.sin(math.pi * i / (HALF - 1))) for i in range(HALF)]
    return top + bot


def tongue(w, h, dy=6):
    return move(open_mouth(w, h), 0, dy)


def fang(x):
    return resample([(x - 4, 2), (x + 4, 2), (x, 11), (x - 4, 2)], N)


def triangle(s, thick):
    return stroke(resample([(0, -s), (s * 1.1, s * 0.8), (-s * 1.1, s * 0.8), (0, -s)]), thick, closed=True)


# ---------- drawing helpers ----------

def fill_poly(surf, pts, col):
    ip = [(int(round(x)), int(round(y))) for x, y in pts]
    pygame.gfxdraw.filled_polygon(surf, ip, col)
    pygame.gfxdraw.aapolygon(surf, ip, col)


def dot(surf, x, y, r, col):
    x, y, r = int(round(x)), int(round(y)), max(1, int(round(r)))
    pygame.gfxdraw.filled_circle(surf, x, y, r, col)
    pygame.gfxdraw.aacircle(surf, x, y, r, col)


def seg(surf, col, p0, p1, w):
    (x0, y0), (x1, y1) = p0, p1
    ln = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / ln * w / 2, (x1 - x0) / ln * w / 2
    fill_poly(surf, [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], col)
    dot(surf, x0, y0, w / 2, col)
    dot(surf, x1, y1, w / 2, col)


def polyline(surf, col, pts, w):
    for p0, p1 in zip(pts, pts[1:]):
        seg(surf, col, p0, p1, w)


def drop(surf, x, y, r, col):
    fill_poly(surf, [(x - r * 0.9, y - r * 0.3), (x, y - r * 2.3), (x + r * 0.9, y - r * 0.3)], col)
    dot(surf, x, y, r, col)


def star(surf, x, y, r, points, inner, rot, col):
    pts = []
    for k in range(points * 2):
        rad = r if k % 2 == 0 else r * inner
        a = rot + k * math.pi / points - math.pi / 2
        pts.append((x + rad * math.cos(a), y + rad * math.sin(a)))
    fill_poly(surf, pts, col)


# ---------- decorations (each draws at alpha a; ox, oy = face centre on the screen surface) ----------

def blush(lines=3):
    def draw(surf, ox, oy, a, t):
        col = scale_col(BLUSH, a)
        for side in (-1, 1):
            bx, by = ox + side * (EYE_X + 20), oy + EYE_Y + 48
            for k in range(lines):
                dx = (k - (lines - 1) / 2) * 12
                seg(surf, col, (bx + dx - 4, by + 7), (bx + dx + 4, by - 7), 4)
    return draw


def rays(color):
    def draw(surf, ox, oy, a, t):
        col = scale_col(color, a)
        pulse = 3 * math.sin(t * 7)
        for side in (-1, 1):
            cx, cy = ox + side * EYE_X, oy + EYE_Y
            for deg in (-165, -132, -100):
                r = math.radians(deg)
                dx, dy = -side * math.cos(r), math.sin(r)
                r0, r1 = 68 + pulse, 90 + pulse
                seg(surf, col, (cx + dx * r0, cy + dy * r0), (cx + dx * r1, cy + dy * r1), 5)
    return draw


def tears(surf, ox, oy, a, t):
    for side in (-1, 1):
        phase = (t * 0.9 + (0.5 if side > 0 else 0.0)) % 1.0
        r = 7 * min(1.0, phase * 6 + 0.3)
        drop(surf, ox + side * (EYE_X + 20), oy + EYE_Y + 30 + phase * 70, r,
             scale_col(BLUE, a * (1 - phase ** 3)))


def tear_streams(surf, ox, oy, a, t):
    col = scale_col(BLUE, a)
    bottom = surf.get_height() + 10
    for side in (-1, 1):
        x0, y0 = ox + side * EYE_X, oy + EYE_Y + 24
        left, right = [], []
        for k in range(19):
            v = k / 18
            y = lerp(y0, bottom, v)
            wob = 3 * math.sin(t * 9 + v * 9 + side)
            half = 7 + 7 * v
            left.append((x0 - half + wob, y))
            right.append((x0 + half + wob, y))
        fill_poly(surf, left + right[::-1], col)


def anger(surf, ox, oy, a, t):
    col = scale_col((255, 80, 120), a)
    k = 1 + 0.12 * math.sin(t * 9)
    cx, cy = ox + EYE_X + 85, oy + EYE_Y - 88
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        ax, ay = cx + sx * 15 * k, cy + sy * 15 * k
        ang = math.atan2(-sy, -sx)
        pts = [(ax + 10 * k * math.cos(ang + d), ay + 10 * k * math.sin(ang + d))
               for d in (-0.9, -0.45, 0.0, 0.45, 0.9)]
        polyline(surf, col, pts, 4)


def question(surf, ox, oy, a, t):
    col = scale_col(PINK, a)
    qx, qy = ox + EYE_X + 78, oy + EYE_Y - 82 + 3 * math.sin(t * 3)
    pts = [(qx + 11 * math.cos(math.radians(d)), qy - 8 + 11 * math.sin(math.radians(d)))
           for d in range(190, 400, 15)]
    polyline(surf, col, pts + [(qx, qy + 8), (qx, qy + 12)], 5)
    dot(surf, qx, qy + 23, 3.5, col)


def zzz(surf, ox, oy, a, t):
    for k in range(3):
        phase = (t * 0.45 + k / 3) % 1.0
        s = 5 + 6 * phase
        x, y = ox + EYE_X + 45 + phase * 60, oy + EYE_Y - 45 - phase * 75
        col = scale_col(MINT, a * math.sin(math.pi * phase))
        polyline(surf, col, [(x - s, y - s), (x + s, y - s), (x - s, y + s), (x + s, y + s)], 4)


def sweat(surf, ox, oy, a, t):
    drop(surf, ox + EYE_X + 72, oy + EYE_Y - 58 + 4 * math.sin(t * 2), 7, scale_col(BLUE, a))


def floating_hearts(surf, ox, oy, a, t):
    for side in (-1, 1):
        fill_poly(surf, heart_pts(0.75 * (1 + 0.12 * math.sin(t * 7)), ox + side * 232, oy - 108, 40),
                  scale_col(HOT, a))
        phase = (t * 0.4 + (0.5 if side > 0 else 0.0)) % 1.0
        fill_poly(surf, heart_pts(0.45, ox + side * (205 + 8 * math.sin(phase * 7)), oy + 40 - phase * 150, 40),
                  scale_col(HOT, a * math.sin(math.pi * phase)))


def sparkle(color, dx, dy):
    def draw(surf, ox, oy, a, t):
        r = 13 * (0.8 + 0.25 * math.sin(t * 6))
        star(surf, ox + dx, oy + dy, r, 4, 0.28, 0.15 * math.sin(t * 2), scale_col(color, a))
    return draw


def thinking_dots(surf, ox, oy, a, t):
    col = scale_col(PINK, a)
    for i in range(int(t * 2.5) % 4):
        dot(surf, ox + EYE_X + 50 + i * 16, oy + EYE_Y - 72, 4.5, col)


def bulb(surf, ox, oy, a, t):
    col = scale_col(YELLOW, a * (0.88 + 0.12 * math.sin(t * 13)))
    bx, by = ox + EYE_X + 88, oy + EYE_Y - 82
    arc = [(bx + 15 * math.cos(math.radians(d)), by + 15 * math.sin(math.radians(d))) for d in range(120, 421, 15)]
    polyline(surf, col, arc, 4)
    seg(surf, col, arc[0], (bx - 6, by + 21), 4)
    seg(surf, col, arc[-1], (bx + 6, by + 21), 4)
    seg(surf, col, (bx - 6, by + 22), (bx + 6, by + 22), 4)
    seg(surf, col, (bx - 4, by + 28), (bx + 4, by + 28), 4)
    for d in (-165, -125, -90, -55, -15):
        r = math.radians(d)
        seg(surf, col, (bx + 22 * math.cos(r), by + 22 * math.sin(r)),
            (bx + 30 * math.cos(r), by + 30 * math.sin(r)), 3)


def orbit_stars(surf, ox, oy, a, t):
    col = scale_col(YELLOW, a)
    for k in range(3):
        ang = t * 2.2 + k * 2 * math.pi / 3
        star(surf, ox + 175 * math.cos(ang), oy + EYE_Y - 88 + 16 * math.sin(ang), 10, 5, 0.45, t * 3, col)


def pluses(surf, ox, oy, a, t):
    col = scale_col(PINK, a)
    for i, (x, y) in enumerate(((-240, -92), (240, -92), (-276, -28), (276, -28))):
        s = 7 + 2.5 * math.sin(t * 8 + i)
        cx, cy = ox + x, oy + y
        seg(surf, col, (cx - s, cy), (cx + s, cy), 4)
        seg(surf, col, (cx, cy - s), (cx, cy + s), 4)


def eye_dots(surf, ox, oy, a, t):
    for side in (-1, 1):
        dot(surf, ox + side * EYE_X, oy + EYE_Y, 8, scale_col(PINK, a))


# ---------- the 25 expressions (eyes are drawn for the LEFT eye; the right eye is its mirror image) ----------

def E(name, eye, mouth, eye_col=PINK, mouth_col=None, eye_r=None, extras=(), motion=None,
      tongue=None, tongue_col=HOT, ears=(0.0, 1.0)):
    """ears = (tilt outward in radians, height scale): perky, droopy or flattened cat ears."""
    return dict(name=name, eye=eye, eye_r=eye_r or eye, mouth=mouth, eye_col=eye_col,
                mouth_col=mouth_col or eye_col, extras=list(extras), motion=motion,
                tongue=tongue or NOTHING, tongue_col=tongue_col, ears=ears)


happy_eye = stroke(arc_line(34, 0, 22, math.pi + 0.3, 2 * math.pi - 0.3), 15)
x_eye = chevron(40, 52, 13)

EXPRESSIONS = [
    # row 1
    E("Neutral", ellipse(24, 44), w_mouth(50, 12)),
    E("Happy", happy_eye, w_mouth(44, 11), tongue=tongue(14, 15), extras=[blush()], ears=(-0.05, 1.08)),
    E("Excited", x_eye, w_mouth(50, 13), tongue=tongue(18, 18), extras=[blush(), rays(PINK)],
      motion=lambda t: (0, -abs(math.sin(t * 7)) * 5, 1), ears=(-0.1, 1.12)),
    E("Content", dash(56, 13, bow=6), w_mouth(40, 10), extras=[blush()]),
    E("Sleepy", stroke(arc_line(34, 0, -18, math.pi - 0.45, 0.45), 11), w_mouth(24, 6, 5),
      eye_col=MINT, extras=[zzz], motion=lambda t: (0, 6 + 3 * math.sin(t * 1.3), 1), ears=(0.5, 0.85)),
    # row 2
    E("Curious", ellipse(22, 40), triangle(9, 4), eye_r=ellipse(26, 48), extras=[question], ears=(-0.05, 1.1)),
    E("Confused", ellipse(24, 44), ellipse(10, 10, 0, 4), eye_r=ellipse(20, 34), extras=[question],
      motion=lambda t: (3 * math.sin(t * 1.6), 0, 1)),
    E("Surprised", ellipse(28, 50), ellipse(13, 14, 0, 4), eye_col=WHITE, extras=[rays(MINT)], ears=(-0.12, 1.14)),
    E("Worried", clipped_ellipse(38, 36, -6, -0.55), frown(24, 8, 6), extras=[sweat], ears=(0.35, 0.9)),
    E("Sad", clipped_ellipse(28, 42, -14, -0.7), frown(22, 8, 6), eye_col=LAV, extras=[tears], ears=(0.6, 0.8)),
    # row 3
    E("Crying", x_eye, wave(40, 5, 1.5, 6), extras=[tear_streams],
      motion=lambda t: (0, 1.5 * math.sin(t * 22), 1), ears=(0.65, 0.8)),
    E("Angry", clipped_ellipse(38, 34, -4, 0.55), frown(34, 10, 7), eye_col=RED, extras=[anger],
      motion=lambda t: (1.5 * math.sin(t * 45), 0, 1), ears=(0.8, 0.68)),
    E("Blushing", dash(54, 13, tilt=0.15), w_mouth(34, 9), extras=[blush(4)]),
    E("Shy", dash(46, 12, tilt=-0.2), w_mouth(28, 8, 6), extras=[blush(4)],
      motion=lambda t: (0.8 * math.sin(t * 35), 8, 1), ears=(0.4, 0.88)),
    E("Flustered", ring(30, 19), wave(36, 4, 2, 6), extras=[eye_dots, blush()]),
    # row 4
    E("Love", heart_pts(1.9), w_mouth(40, 10), tongue=heart_pts(0.42, 0, 12), eye_col=HOT, extras=[floating_hearts],
      motion=lambda t: (0, 0, 1 + 0.09 * max(0.0, math.sin(t * 6)) ** 4)),
    E("Mischievous", clipped_ellipse(34, 30, -2, 0.45), w_mouth(42, 10), tongue=fang(9), tongue_col=WHITE,
      extras=[sparkle(MINT, EYE_X + 80, EYE_Y - 72)]),
    E("Smug", move(clipped_ellipse(36, 30, 2, 0.1), 6, 4), rotate(w_mouth(32, 8, 6), -0.15),
      eye_r=move(clipped_ellipse(36, 30, 2, 0.1), -6, 4)),
    E("Thinking", move(ellipse(22, 42), 7, -7), move(wave(20, 3, 1, 6), 12, 0),
      eye_r=move(ellipse(22, 42), -7, -7), extras=[thinking_dots]),
    E("Idea", ellipse(25, 46), open_mouth(28, 26), extras=[bulb],
      motion=lambda t: (0, -abs(math.sin(t * 4)) * 3, 1), ears=(-0.1, 1.12)),
    # row 5
    E("Focused", clipped_ellipse(36, 30, -2, 0.3), line(-14, 0, 14, 0, 7), eye_col=(255, 205, 230)),
    E("Dizzy", spiral(3, 34, 1.75, 6), wave(48, 4, 2, 5), extras=[orbit_stars],
      motion=lambda t: (7 * math.sin(t * 2.2), 2 * math.sin(t * 4.4), 1)),
    E("Deadpan", line(-32, 0, 32, 0, 12), line(-16, 0, 16, 0, 8), eye_col=(245, 215, 235)),
    E("Wink", ellipse(24, 44), w_mouth(40, 10), tongue=tongue(14, 15), eye_r=chevron(40, 48, 13),
      extras=[blush(), sparkle(PINK, EYE_X + 82, EYE_Y - 62)]),
    E("Laughing", chevron(42, 54, 13), w_mouth(58, 15, 8), tongue=tongue(24, 24, 8), extras=[blush(), pluses],
      motion=lambda t: (0, -abs(math.sin(t * 10)) * 7, 1), ears=(-0.05, 1.08)),
]
DIZZY = [e["name"] for e in EXPRESSIONS].index("Dizzy")


def snapshot(e):
    return dict(eye=list(e["eye"]), eye_r=list(e["eye_r"]), mouth=list(e["mouth"]), tongue=list(e["tongue"]),
                eye_col=e["eye_col"], mouth_col=e["mouth_col"], tongue_col=e["tongue_col"])


# ---------- app ----------

class FaceApp:
    def __init__(self, window):
        self.window = window
        self.index = 0
        self.src = snapshot(EXPRESSIONS[0])
        self.dst = self.src
        self.t = 1.0
        self.fx = [1.0 if i == 0 else 0.0 for i in range(len(EXPRESSIONS))]
        self.blink = None
        self.auto_blink = True
        self.next_blink = 3.0
        self.time = 0.0
        self.spin = 0.0
        self.twitch = None          # (ear side, progress 0..1)
        self.next_twitch = 2.5
        self.mouse = (0, 0)
        self.keymap = {ord(c): i for i, c in enumerate(KEYS)}
        kp = [pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4, pygame.K_KP5,
              pygame.K_KP6, pygame.K_KP7, pygame.K_KP8, pygame.K_KP9, pygame.K_KP0]
        self.keymap.update({k: i for i, k in enumerate(kp)})

        self.feat = pygame.Surface(DISP.size).convert()
        self.feat.set_colorkey((0, 0, 0))
        fonts = "avenirnext,avenir,helveticaneue,helvetica,arial"
        self.font_big = pygame.font.SysFont(fonts, 32, bold=True)
        self.font = pygame.font.SysFont(fonts, 15, bold=True)
        self.font_small = pygame.font.SysFont(fonts, 14)

        bw, bh, gap = 164, 32, 6
        x0 = (WIN_W - (5 * bw + 4 * gap)) // 2
        self.buttons = [pygame.Rect(x0 + (i % 5) * (bw + gap), DISP.bottom + 78 + (i // 5) * (bh + gap), bw, bh)
                        for i in range(len(EXPRESSIONS))]

        self.background = self._build_background()
        self.bezel = self._build_bezel()
        self.grid = self._build_grid()
        self.gloss = self._build_gloss()

    # ----- static layers -----

    def _screen_mask(self):
        mask = pygame.Surface(DISP.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=SCREEN_RADIUS)
        return mask

    def _build_background(self):
        bg = pygame.Surface((WIN_W, WIN_H)).convert()
        for y in range(WIN_H):
            pygame.draw.line(bg, lerp_col((30, 27, 42), (11, 10, 16), y / WIN_H), (0, y), (WIN_W, y))

        bez = DISP.inflate(44, 44)
        # soft ambient glow + drop shadow behind the device (concentric shapes = smooth gradient)
        halo = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        for i in range(60, 0, -1):
            pygame.draw.ellipse(halo, (190, 90, 190, int(34 * (1 - i / 60) ** 2)), bez.inflate(i * 5, i * 3))
        for i in range(26, 0, -1):
            pygame.draw.rect(halo, (0, 0, 0, int(150 * (1 - i / 26) ** 1.5)),
                             bez.inflate(i * 2, i * 2).move(0, 14), border_radius=72 + i)
        bg.blit(halo, (0, 0))
        return bg

    def _build_bezel(self):
        bg = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        bez = DISP.inflate(44, 44)
        # glossy bezel
        pygame.draw.rect(bg, (27, 26, 35), bez, border_radius=72)
        pygame.draw.rect(bg, (95, 92, 115), bez, width=2, border_radius=72)
        pygame.draw.arc(bg, (165, 160, 190), pygame.Rect(bez.x + 5, bez.y + 5, 134, 134), math.pi / 2, math.pi, 3)
        pygame.draw.line(bg, (120, 116, 140), (bez.x + 72, bez.y + 6), (bez.x + 180, bez.y + 6), 2)
        pygame.draw.rect(bg, (10, 10, 14), DISP.inflate(14, 14), border_radius=54)
        pygame.draw.rect(bg, (6, 5, 10), DISP, border_radius=SCREEN_RADIUS)

        # fluffy cheek tufts on both sides of the frame
        for side in (-1, 1):
            ex = bez.x if side < 0 else bez.right
            y0 = bez.y + 250
            tuft = [(0, 0), (22, 14), (4, 22), (20, 40), (2, 46), (14, 64), (0, 70)]   # (outward, down)
            pts = [(ex + side * (out - 4), y0 + down) for out, down in tuft]
            pts = chaikin(pts, 2)
            pygame.gfxdraw.filled_polygon(bg, [(int(x), int(y)) for x, y in pts], (27, 26, 35))
            pygame.draw.aalines(bg, (95, 92, 115), False, pts)
        return bg

    def _draw_ears(self, win):
        bez = DISP.inflate(44, 44)
        tilt, height = self.ear_mood()
        outer = chaikin([(-84, 34), (-52, -40), (-30, -92), (-14, -102), (4, -94), (38, -42), (84, 34)])
        inner = [(x * 0.56 - 6, y * 0.64 - 12) for x, y in outer]
        fluff = [[(-16, -30), (-10, -58)], [(-2, -32), (-3, -66)], [(12, -30), (6, -54)]]
        for side in (-1, 1):
            a = tilt
            if self.twitch and self.twitch[0] == side:
                a += 0.22 * math.sin(math.pi * 2 * self.twitch[1]) * (1 - self.twitch[1])
            px, py = DISP.centerx + side * 175, bez.y + 38

            def place(pts):
                pts = [(x, y * height) for x, y in pts]
                pts = rotate(pts, -a)
                return [(px + side * -x, py + y) for x, y in pts]

            o, i = place(outer), place(inner)
            pygame.gfxdraw.filled_polygon(win, [(int(x), int(y)) for x, y in o], (32, 30, 42))
            pygame.draw.aalines(win, (110, 106, 132), True, o)
            pygame.gfxdraw.filled_polygon(win, [(int(x), int(y)) for x, y in i], (105, 52, 95))
            pygame.draw.aalines(win, (255, 150, 205), True, i)
            for f in fluff:
                pygame.draw.aalines(win, (225, 205, 235), False, place(chaikin([f[0], ((f[0][0] + f[1][0]) / 2 - 3, (f[0][1] + f[1][1]) / 2), f[1]], 2)))

    def _build_grid(self):
        """Dot-matrix LED texture, multiplied over the glowing features."""
        grid = pygame.Surface(DISP.size).convert()
        grid.fill((255, 255, 255))
        for x in range(0, DISP.w, 4):
            pygame.draw.line(grid, (170, 170, 180), (x, 0), (x, DISP.h))
        for y in range(0, DISP.h, 4):
            pygame.draw.line(grid, (170, 170, 180), (0, y), (DISP.w, y))
        outside = pygame.Surface(DISP.size, pygame.SRCALPHA)
        outside.fill((255, 255, 255, 255))
        pygame.draw.rect(outside, (0, 0, 0, 0), outside.get_rect(), border_radius=SCREEN_RADIUS)
        grid.blit(outside, (0, 0))
        return grid

    def _build_gloss(self):
        gloss = pygame.Surface(DISP.size, pygame.SRCALPHA)
        for y in range(DISP.h // 2):
            pygame.draw.line(gloss, (255, 255, 255, int(12 * (1 - y / (DISP.h / 2)))), (0, y), (DISP.w, y))
        r = SCREEN_RADIUS
        pygame.draw.arc(gloss, (255, 255, 255, 90), pygame.Rect(7, 7, 2 * r, 2 * r), math.pi / 2, math.pi, 3)
        pygame.draw.line(gloss, (255, 255, 255, 60), (r + 6, 8), (r + 70, 8), 2)
        pygame.draw.arc(gloss, (255, 255, 255, 50), pygame.Rect(DISP.w - 2 * r - 7, 7, 2 * r, 2 * r), 1.1, 1.5, 2)
        gloss.blit(self._screen_mask(), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return gloss

    # ----- state -----

    def current(self):
        e = ease_out_back(self.t)
        c = smoothstep(self.t)
        return dict(eye=lerp_pts(self.src["eye"], self.dst["eye"], e),
                    eye_r=lerp_pts(self.src["eye_r"], self.dst["eye_r"], e),
                    mouth=lerp_pts(self.src["mouth"], self.dst["mouth"], e),
                    tongue=lerp_pts(self.src["tongue"], self.dst["tongue"], e),
                    tongue_col=lerp_col(self.src["tongue_col"], self.dst["tongue_col"], c),
                    eye_col=lerp_col(self.src["eye_col"], self.dst["eye_col"], c),
                    mouth_col=lerp_col(self.src["mouth_col"], self.dst["mouth_col"], c))

    def set_expression(self, i):
        i %= len(EXPRESSIONS)
        if i == self.index:
            return
        self.src = self.current()
        self.dst = snapshot(EXPRESSIONS[i])
        self.index = i
        self.t = 0.0

    def start_blink(self):
        if self.blink is None:
            self.blink = 0.0

    def eye_openness(self):
        if self.blink is None:
            return 1.0
        return 1.0 - 0.9 * math.sin(math.pi * self.blink)

    def ear_mood(self):
        """Blend the ear tilt / height of the visible expressions."""
        tot = sum(self.fx) or 1.0
        tilt = sum(f * e["ears"][0] for f, e in zip(self.fx, EXPRESSIONS)) / tot
        height = sum(f * e["ears"][1] for f, e in zip(self.fx, EXPRESSIONS)) / tot
        return tilt, height

    def motion(self):
        """Blend each expression's idle motion (dx, dy, eye scale) by how visible it is."""
        dx = dy = 0.0
        scale = 1.0
        for i, e in enumerate(EXPRESSIONS):
            if e["motion"] and self.fx[i] > 0:
                mdx, mdy, ms = e["motion"](self.time)
                dx += mdx * self.fx[i]
                dy += mdy * self.fx[i]
                scale += (ms - 1) * self.fx[i]
        return dx, dy, scale

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return False
            if ev.key in self.keymap:
                self.set_expression(self.keymap[ev.key])
            elif ev.key == pygame.K_RIGHT:
                self.set_expression(self.index + 1)
            elif ev.key == pygame.K_LEFT:
                self.set_expression(self.index - 1)
            elif ev.key == pygame.K_SPACE:
                self.start_blink()
            elif ev.key == pygame.K_a:
                self.auto_blink = not self.auto_blink
        elif ev.type == pygame.MOUSEMOTION:
            self.mouse = ev.pos
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i, rect in enumerate(self.buttons):
                if rect.collidepoint(ev.pos):
                    self.set_expression(i)
        return True

    def update(self, dt):
        self.time += dt
        self.t = min(1.0, self.t + dt / MORPH_TIME)
        self.spin = (self.spin + dt * 5 + math.pi) % (2 * math.pi) - math.pi
        for i in range(len(self.fx)):
            target = 1.0 if i == self.index else 0.0
            step = dt / 0.3
            self.fx[i] = min(target, self.fx[i] + step) if self.fx[i] < target else max(target, self.fx[i] - step)

        self.next_twitch -= dt
        if self.next_twitch <= 0:
            self.twitch = [random.choice((-1, 1)), 0.0]
            self.next_twitch = random.uniform(2.5, 7.0)
        if self.twitch:
            self.twitch[1] += dt / 0.35
            if self.twitch[1] >= 1.0:
                self.twitch = None

        if self.blink is not None:
            self.blink += dt / BLINK_TIME
            if self.blink >= 1.0:
                self.blink = None
        if self.auto_blink:
            self.next_blink -= dt
            if self.next_blink <= 0:
                self.start_blink()
                # now and then do a quick double blink
                self.next_blink = BLINK_TIME + 0.08 if random.random() < 0.2 else random.uniform(2.5, 5.5)

    # ----- drawing -----

    def draw_features(self, surf):
        st = self.current()
        w, h = surf.get_size()
        mdx, mdy, eye_scale = self.motion()
        hop = -8 * math.sin(math.pi * self.t)                  # little hop while morphing
        ox = w / 2 + mdx
        oy = h / 2 + 4 * math.sin(self.time * 1.8) + hop + mdy
        openness = self.eye_openness()
        spin = self.spin * self.fx[DIZZY]

        for side, pts in ((-1, st["eye"]), (1, st["eye_r"])):
            if spin:
                pts = rotate(pts, spin)
            if side > 0:
                pts = [(-x, y) for x, y in pts]
            ys = [y for _, y in pts]
            cy = (min(ys) + max(ys)) / 2
            pts = [(ox + side * EYE_X + x * eye_scale, oy + EYE_Y + (cy + (y - cy) * openness) * eye_scale)
                   for x, y in pts]
            fill_poly(surf, pts, st["eye_col"])

        fill_poly(surf, [(ox + x, oy + MOUTH_Y + y) for x, y in st["mouth"]], st["mouth_col"])
        xs = [x for x, _ in st["tongue"]]
        if max(xs) - min(xs) > 2:
            fill_poly(surf, [(ox + x, oy + MOUTH_Y + y) for x, y in st["tongue"]], st["tongue_col"])

        # cat nose + whiskers (whiskers droop with the ears)
        nx, ny = ox, oy + MOUTH_Y - 20
        fill_poly(surf, chaikin([(nx - 7, ny - 4), (nx + 7, ny - 4), (nx, ny + 4), (nx - 7, ny - 4)], 2), NOSE_COL)
        wcol = scale_col(st["eye_col"], 0.7)
        droop = self.ear_mood()[0] * 0.35
        for side in (-1, 1):
            for k, ang in enumerate((-0.2, 0.0, 0.2)):
                a = ang + droop + 0.04 * math.sin(self.time * 2.5 + k)
                x0, y0 = ox + side * 205, oy + MOUTH_Y - 12 + k * 8
                seg(surf, wcol, (x0, y0), (x0 + side * 55 * math.cos(a), y0 + 55 * math.sin(a)), 3)

        for i, e in enumerate(EXPRESSIONS):
            if self.fx[i] > 0.01:
                for extra in e["extras"]:
                    extra(surf, ox, oy, self.fx[i], self.time)

    def draw(self):
        win = self.window
        win.blit(self.background, (0, 0))
        self._draw_ears(win)
        win.blit(self.bezel, (0, 0))

        # glowing face: soft coloured bloom added onto the dark screen, crisp shapes on top, LED grid over all
        self.feat.fill((0, 0, 0))
        self.draw_features(self.feat)
        src = self.feat.copy()
        src.set_colorkey(None)
        dim = src.copy()
        dim.fill((130, 130, 130), special_flags=pygame.BLEND_MULT)   # dimmer copy keeps the inner glow pink, not white
        for layer, div, reps in ((src, 14, 2), (dim, 5, 1)):             # wide soft halo + tight inner glow
            small = pygame.transform.smoothscale(layer, (DISP.w // div, DISP.h // div))
            glow = pygame.transform.smoothscale(small, DISP.size)
            for _ in range(reps):
                win.blit(glow, DISP.topleft, special_flags=pygame.BLEND_ADD)
        win.blit(self.feat, DISP.topleft)
        win.blit(self.grid, DISP.topleft, special_flags=pygame.BLEND_MULT)
        win.blit(self.gloss, DISP.topleft)

        # expression name under the screen
        col = self.current()["eye_col"]
        label = self.font_big.render(EXPRESSIONS[self.index]["name"], True, col)
        win.blit(label, label.get_rect(center=(WIN_W // 2, DISP.bottom + 50)))

        # buttons
        for i, rect in enumerate(self.buttons):
            active = i == self.index
            hover = rect.collidepoint(self.mouse)
            ecol = EXPRESSIONS[i]["eye_col"]
            if active:
                glow = pygame.Surface(rect.inflate(16, 16).size, pygame.SRCALPHA)
                pygame.draw.rect(glow, ecol + (40,), glow.get_rect(), border_radius=18)
                win.blit(glow, rect.inflate(16, 16).topleft)
            fill = (62, 38, 66) if active else (48, 44, 62) if hover else (34, 32, 46)
            pygame.draw.rect(win, fill, rect, border_radius=12)
            pygame.draw.rect(win, ecol if active else (70, 66, 88), rect, width=2, border_radius=12)
            key = self.font.render(KEYS[i].upper() if i < len(KEYS) else "", True, ecol if active else (140, 134, 165))
            name = self.font.render(EXPRESSIONS[i]["name"], True, (255, 240, 250) if active else (200, 195, 215))
            win.blit(key, key.get_rect(midleft=(rect.x + 14, rect.centery)))
            win.blit(name, name.get_rect(center=(rect.centerx + 8, rect.centery)))

        hint = "Click a button or press its key  |  Left/Right: cycle  |  Space: blink  |  " \
               "A: auto-blink (%s)  |  Esc: quit" % ("on" if self.auto_blink else "off")
        text = self.font_small.render(hint, True, (130, 125, 150))
        win.blit(text, text.get_rect(center=(WIN_W // 2, WIN_H - 22)))


def main():
    pygame.init()
    window = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Robo Face")
    app = FaceApp(window)
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for ev in pygame.event.get():
            if not app.handle_event(ev):
                running = False
        app.update(dt)
        app.draw()
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
