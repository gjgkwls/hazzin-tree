#!/usr/bin/env python3
"""tree.py — 회전하는 ASCII 크리스마스 트리 웹사이트 (파이썬 표준 라이브러리만 사용).

실행:          python3 tree.py          → http://localhost:8000
프레임 미리보기: python3 tree.py --dump 230
"""
import gzip
import json
import math
import os
import random
import re
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COLS, ROWS = 132, 84
FPS = 15
T = 240                      # 총 프레임(16초 루프, 한 바퀴 회전)
F1 = 40                      # 성장 완료
F2 = 95                      # 장식 완료
HY = 75                      # y=0(바닥)이 놓이는 행
SY = 56.0
SX = SY * 1.7                # 모노스페이스 셀 종횡비 보정
CX = COLS / 2
CAM = 2.8
NLIGHT = 270

rng = random.Random(1225)

# <<code-window>>
def cone_r(y):
    """높이 y(0~1)에서의 가지 반경."""
    return 0.02 + 0.46 * (1.0 - y) ** 0.9

def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

LETTERS = 'abcdefghijkmnopqrstuvwxyz'

def build_points():
    foliage, trunk, lights, balls, boxes = [], [], [], [], []
    while len(foliage) < 11500:                    # 잎: 아래가 빽빽한 원뿔
        y = 1 - math.sqrt(rng.random())
        rr = cone_r(y)
        r = rr * (0.30 + 0.70 * rng.random() ** 0.45)
        a = rng.uniform(0, 2 * math.pi)
        yy = y - 0.06 * (r / rr) ** 2 * rng.random()   # 가지 처짐
        foliage.append((r * math.cos(a), max(yy, 0.0), r * math.sin(a),
                        rng.choice(LETTERS), rng.random()))
    foliage.sort(key=lambda p: p[1])
    for _ in range(150):                           # 기둥
        a = rng.uniform(0, 2 * math.pi)
        r = 0.04 * math.sqrt(rng.random())
        trunk.append((r * math.cos(a), rng.uniform(0.0, 0.14), r * math.sin(a)))
    for _ in range(NLIGHT):                        # 전구: 바깥 껍질에
        y = 0.03 + 0.93 * (1 - math.sqrt(rng.random()))
        rr = cone_r(y) * rng.uniform(0.9, 1.0)
        a = rng.uniform(0, 2 * math.pi)
        lights.append((rr * math.cos(a), y, rr * math.sin(a),
                       rng.randrange(T), rng.choice((16, 20, 24, 30))))
    kinds = (['ball'] * 14 + ['small'] * 16        # 오너먼트: 구슬/은방울/별
             + ['bell'] * 10 + ['star'] * 8)
    rng.shuffle(kinds)
    for kind in kinds:
        y = 0.07 + 0.78 * (1 - math.sqrt(rng.random()))
        rr = cone_r(y)
        a = rng.uniform(0, 2 * math.pi)
        cls = rng.choice(('oR', 'oR', 'oB', 'oP'))
        balls.append((rr * math.cos(a), y, rr * math.sin(a), kind, cls))
    for d, az, w, h, dep, top, side, rib in (      # 선물 상자: 카메라 앞쪽에 고정
            (0.55, 3.8, 0.15, 0.12, 0.13, 'r0', 'r1', 'w0'),
            (0.52, 5.6, 0.14, 0.10, 0.12, 'b0', 'b1', 'w0'),
            (0.54, 4.6, 0.12, 0.12, 0.11, 'p0', 'p1', 'w0'),
            (0.58, 4.2, 0.13, 0.09, 0.11, 'si', 's1', 'oR'),   # 은색+빨간 리본
            (0.56, 5.1, 0.12, 0.11, 0.10, 'y1', 't', 'w0')):   # 금색
        bx, bz = d * math.cos(az), d * math.sin(az)
        pts = []
        nx = max(2, int(w / 0.009))                # 셀 간격보다 촘촘한 면 격자
        ny = max(2, int(h / 0.016))
        nz = max(2, int(dep / 0.009))
        for ix in range(nx + 1):
            for iy in range(ny + 1):
                for iz in range(nz + 1):
                    on_top = iy == ny
                    on_side = ix in (0, nx) or iz in (0, nz)
                    if not (on_top or on_side):
                        continue
                    lx = (ix / nx - 0.5) * w
                    ly = iy / ny * h
                    lz = (iz / nz - 0.5) * dep
                    ribbon = abs(lx) < w * 0.09 or abs(lz) < dep * 0.09
                    cl = rib if ribbon else (top if on_top else side)
                    pts.append((bx + lx, ly, bz + lz, rng.choice('#8%&'), cl))
        for _ in range(6):                         # 뚜껑 위 금색 매듭
            pts.append((bx + rng.uniform(-0.012, 0.012),
                        h + rng.uniform(0.0, 0.018),
                        bz + rng.uniform(-0.012, 0.012), '@', 'y'))
        boxes.append(pts)
    garland = []                                   # 금색 띠: 나선으로 4.5바퀴
    for i in range(900):
        t = i / 900
        y = 0.94 - 0.86 * t
        a = 4.5 * 2 * math.pi * t
        rr = cone_r(y) * 1.02 + 0.012
        garland.append((rr * math.cos(a), y + rng.uniform(-0.008, 0.008),
                        rr * math.sin(a), rng.choice('~~~=o'), rng.randrange(T)))
    return foliage, trunk, lights, balls, boxes, garland

def shade(zr, u):
    d = -zr                                        # 카메라 쪽이 밝다
    if d > 0.10 and u > 0.35:
        return 'g0' if u > 0.78 else 'g1'
    if d > -0.05:
        return 'g1' if u > 0.55 else 'g2'
    return 'g2' if u > 0.5 else 'g3'

# 산타+루돌프 비트맵(62x16): 픽셀마다 랜덤 글자가 들어가 실루엣을 이룬다
# r빨강 w흰색 f얼굴 k검정 y금색 b갈색 D진갈색 R코(점멸) s고삐 .빈칸
SANTA_ART = (
    "." * 62,                                                            # 여백
    "." * 6 + "ww" + "." * 54,                                           # 모자 방울
    "." * 7 + "rrrr" + "." * 41 + "b.b..b" + "." * 4,                    # 모자 / 뿔 끝
    "." * 6 + "rrrrrrr" + "." * 40 + "b.bb" + "." * 5,                   # 모자 / 뿔 가지
    "." * 5 + "w" * 9 + "." * 40 + "b.b" + "." * 5,                      # 모자 털선 / 뿔 줄기
    "." * 6 + "fffffkf" + "." * 40 + "bbbbb" + "." * 4,                  # 얼굴+눈 / 머리 윗선
    "." * 5 + "w" * 9 + "." * 38 + "bbbbkb" + "RR" + "." * 2,            # 수염 / 머리+눈+빨간 코
    "." * 6 + "w" * 9 + "." * 34 + "b" * 7 + "." * 6,                    # 수염 / 목
    "." + "DD" + "rrrrr" + "wwww" + "rrrrr" + "." * 16
        + "s.s.s.s.s.s.s" + "b" * 8 + "." * 8,                           # 가슴수염 / 고삐 / 앞가슴
    "DDD" + "r" * 15 + "rrrrr" + "k" + "." + "s.s.s.s" + "." * 6
        + "w" + "." + "b" * 13 + "." * 9,                                # 자루+몸+팔+장갑 / 고삐 / 꼬리+몸통
    "DDD" + "rr" + "kkkk" + "yy" + "kkkk" + "rr" + "." * 10 + "yy"
        + "." * 11 + "b" * 12 + "." * 10,                                # 벨트+금버클 / 썰매 앞코 / 배
    "." + "DD" + "." + "r" * 12 + "." * 10 + "yy" + "." * 13
        + "DD" + "." * 6 + "DD" + "." * 11,                              # 아랫몸 / 썰매 앞코 / 허벅지
    "." + "y" * 27 + "." * 11 + "DD" + "." * 10 + "DD" + "." * 9,        # 썰매 난간 / 정강이
    ".." + "y" * 25 + "." * 10 + "DD" + "." * 14 + "DD" + "." * 7,       # 썰매 몸체 / 발굽
    "." * 4 + "y" * 21 + "." * 37,                                       # 썰매 바닥
    "." * 5 + "yyyy" + "." * 10 + "yyyyy" + "." * 38,                    # 썰매 날
)
_SANTA_LEG = {                                     # 기호 -> (기본색, 그늘색, 그늘 확률)
    'r': ('r0', 'r1', 0.3), 'w': ('w0', 's0', 0.2), 'f': ('sk', 'sk', 0.0),
    'b': ('t', 'td', 0.3), 'D': ('td', 'td', 0.0), 'y': ('y1', 'y1', 0.0),
    'k': ('k', 'k', 0.0), 'R': ('R', 'R', 0.0), 's': ('s1', 's1', 0.0),
}
SANTA_PARTS = []
for _dy, _row in enumerate(SANTA_ART):
    for _dx, _ch in enumerate(_row):
        if _ch != '.':
            _base, _dim, _p = _SANTA_LEG[_ch]
            SANTA_PARTS.append((_dx, _dy, rng.choice(LETTERS),
                                _dim if rng.random() < _p else _base))

ORN_SHAPES = {                                     # 다중 셀 오너먼트 (None = 자기 색)
    'ball': ((0, -2, "'", 'y1'),                   # 고리 + 3x2 구슬(윗면 하이라이트)
             (-1, -1, '(', None), (0, -1, '@', None), (1, -1, ')', None),
             (-1, 0, '\\', None), (0, 0, 'O', None), (1, 0, '/', None)),
    'small': ((0, -1, "'", 'y1'), (0, 0, 'O', None)),
    'bell': ((0, -2, 'o', 'y1'),                   # 은방울: 고리+종머리+치마+추
             (-1, -1, '/', 'si'), (0, -1, 'A', 'si'), (1, -1, '\\', 'si'),
             (-2, 0, '(', 'si'), (-1, 0, '=', 'si'), (0, 0, '=', 'si'),
             (1, 0, '=', 'si'), (2, 0, ')', 'si'), (0, 1, '.', 'y1')),
    'star': ((0, -2, "'", 'y1'),                   # 반짝이 별: 십자 광채
             (0, -1, '|', 'y1'), (-1, 0, '-', 'y1'), (0, 0, '*', 'oG'),
             (1, 0, '-', 'y1'), (0, 1, "'", 'y1')),
}

MSG_ART = (                                        # 필기체 Merry Christmas (figlet Cursive)
    ' _ _ _                      __',
    "' ) ) )                    /  )/            _/_",
    ' / / / _  __  __  __  ,   /   /_  __  o _   /  ______  __.  _',
    "/ ' (_</_/ (_/ (_/ (_/_  (__// /_/ (_<_/_)_<__/ / / <_(_/|_/_)_",
    '                    /',
    "                   '",
)
MSG_W = 63
MSG_COLORS = (                                     # 글자별로 빨강/초록 번갈아
    'r' * 7 + 'g' * 2 + 'r' * 4 + 'g' * 4 + 'r' * 6 + 'g' * 8 + 'r' * 2
    + 'g' * 4 + 'r' * 2 + 'g' * 4 + 'r' * 4 + 'g' * 7 + 'r' * 5 + 'g' * 4)

def draw_santa(f, sg, sc):
    """글자들이 모여 산타와 루돌프가 된다. 루프당 두 번 하늘을 가로지른다."""
    p = (f * 2 % T) / T
    x0 = int(-68 + p * (COLS + 74))
    y0 = int(round(math.sin(2 * math.pi * 3 * p)))
    blink = (f // 3) % 2 == 0
    for dx, dy, ch, cl in SANTA_PARTS:
        if cl == 'R' and not blink:                # 루돌프 코 점멸
            cl = 'r0'
        sx, sy = x0 + dx, y0 + dy
        if 0 <= sx < COLS and 0 <= sy < ROWS:
            sg[sy][sx], sc[sy][sx] = ch, cl
    for j in range(1, 9):                          # 썰매 뒤 반짝이 궤적
        sx, sy = x0 + 2 - 2 * j + f % 2, y0 + 12 + j % 2
        if 0 <= sx < COLS and 0 <= sy < ROWS:
            sg[sy][sx] = '.'
            sc[sy][sx] = 'y1' if (f + j) % 4 < 2 else 's1'

def render(f, scene, sky, ground, snow):
    foliage, trunk, lights, balls, boxes, garland = scene
    th = 2 * math.pi * f / T
    c, s = math.cos(th), math.sin(th)
    glyph = [[' '] * COLS for _ in range(ROWS)]
    cls = [[None] * COLS for _ in range(ROWS)]
    zb = [[9.9] * COLS for _ in range(ROWS)]
    oglyph = [[' '] * COLS for _ in range(ROWS)]   # 선물 오버레이(토글용 별도 레이어)
    ocls = [[None] * COLS for _ in range(ROWS)]
    ozb = [[9.9] * COLS for _ in range(ROWS)]
    sglyph = [[' '] * COLS for _ in range(ROWS)]   # 산타 오버레이
    scls = [[None] * COLS for _ in range(ROWS)]
    draw_santa(f, sglyph, scls)
    bglyph = [[' '] * COLS for _ in range(ROWS)]   # 오너먼트 오버레이
    bcls = [[None] * COLS for _ in range(ROWS)]
    bzb = [[9.9] * COLS for _ in range(ROWS)]
    wglyph = [[' '] * COLS for _ in range(ROWS)]   # 눈 오버레이
    wcls = [[None] * COLS for _ in range(ROWS)]
    for x0, y0, spd, ph, ch, cl in snow:           # 바람에 살랑이며 내린다
        yrow = (y0 + f * spd) % 80
        x = (x0 + int(round(1.5 * math.sin(2 * math.pi * (3 * f / T + ph))))) % COLS
        wglyph[yrow][x], wcls[yrow][x] = ch, cl
    tglyph = [[' '] * COLS for _ in range(ROWS)]   # 문구 오버레이
    tcls = [[None] * COLS for _ in range(ROWS)]
    if f >= F2 - 4:                                # 왼쪽부터 써 내려간다
        vis = (f - (F2 - 4)) * 3
        mx0 = (COLS - MSG_W) // 2
        for dy, row in enumerate(MSG_ART):
            for dx, ch in enumerate(row):
                if ch != ' ' and dx < vis:
                    tglyph[2 + dy][mx0 + dx] = ch
                    tcls[2 + dy][mx0 + dx] = 'mR' if MSG_COLORS[dx] == 'r' else 'mG'

    for x, row, ch, ph, per in sky:                # 밤하늘
        tw = ((f + ph) % per) / per
        if tw < 0.78:
            glyph[row][x], cls[row][x] = ch, ('s0' if tw < 0.5 else 's1')
    for (ry, rx), (ch, cl) in ground.items():      # 바닥
        glyph[ry][rx], cls[ry][rx] = ch, cl

    def plot(x, y, z, ch, cl, bias=0.0):
        xr = x * c + z * s
        zr = (-x * s + z * c) + bias
        k = CAM / (CAM + zr)
        sx = int(CX + xr * SX * k + 0.5)
        sy = int(HY - 0.5 * SY - (y - 0.5) * SY * k + 0.5)
        if 0 <= sx < COLS and 0 <= sy < ROWS and zr < zb[sy][sx]:
            zb[sy][sx] = zr
            glyph[sy][sx], cls[sy][sx] = ch, cl
        return zr

    def plot_gift(x, y, z, ch, cl):                # 회전 없이 고정, 오버레이에
        zr = z - 0.03
        k = CAM / (CAM + zr)
        sx = int(CX + x * SX * k + 0.5)
        sy = int(HY - 0.5 * SY - (y - 0.5) * SY * k + 0.5)
        if 0 <= sx < COLS and 0 <= sy < ROWS and zr < ozb[sy][sx]:
            ozb[sy][sx] = zr
            oglyph[sy][sx], ocls[sy][sx] = ch, cl

    growing = f < F1
    front = 1.10 * smooth(f / F1) if growing else 1.10
    letters = 0
    for x, y, z, ch, u in foliage:                 # 나무가 자란다
        if y > front:
            break
        letters += 1
        xr = x * c + z * s
        zr = -x * s + z * c
        cl = 'w0' if growing and front - y < 0.085 else shade(zr, u)
        k = CAM / (CAM + zr)
        sx = int(CX + xr * SX * k + 0.5)
        sy = int(HY - 0.5 * SY - (y - 0.5) * SY * k + 0.5)
        if 0 <= sx < COLS and 0 <= sy < ROWS and zr < zb[sy][sx]:
            zb[sy][sx] = zr
            glyph[sy][sx], cls[sy][sx] = ch, cl
    for x, y, z in trunk:
        if y < front:
            letters += 1
            plot(x, y, z, '#', 't')

    n_on = 0
    if f >= F1:
        if f >= F1 + 6:                            # 금색 띠가 위에서 아래로 감긴다
            frac = min(1.0, (f - F1 - 6) / 30)
            for gi in range(int(len(garland) * frac)):
                x, y, z, ch, ph = garland[gi]
                tw = (f + ph) % 24
                plot(x, y, z, ch, 'y' if tw < 4 else 'y1', bias=-0.02)
        # 전구가 하나씩 켜진다
        n_on = min(NLIGHT, int(NLIGHT * (f - F1) / (F2 - F1 - 15)))
        for i in range(n_on):
            x, y, z, ph, per = lights[i]
            b = ((f + ph) % per) / per
            ch, cl = ('@', 'Y') if b < 0.18 else (('o', 'y') if b < 0.62 else ('o', 'y1'))
            plot(x, y, z, ch, cl, bias=-0.05)
        for i, (x, y, z, kind, cl) in enumerate(balls):  # 오너먼트 팝(토글 레이어)
            born = F1 + 4 + i
            if f < born:
                continue
            flash = f - born < 3
            xr = x * c + z * s
            zr = (-x * s + z * c) - 0.05
            k = CAM / (CAM + zr)
            sx0 = int(CX + xr * SX * k + 0.5)
            sy0 = int(HY - 0.5 * SY - (y - 0.5) * SY * k + 0.5)
            for dx, dy, gl, pc in ORN_SHAPES[kind]:
                sx, sy = sx0 + dx, sy0 + dy
                if (0 <= sx < COLS and 0 <= sy < ROWS
                        and zr < zb[sy][sx] and zr < bzb[sy][sx]):  # 나무 뒤면 가려진다
                    bzb[sy][sx] = zr
                    bglyph[sy][sx] = gl
                    bcls[sy][sx] = 'W' if flash else (pc or cl)
        FALL = 6
        for i, pts in enumerate(boxes):            # 오너먼트와 동시에 선물이 떨어진다
            born = F1 + 6 + i * 6
            if f < born:
                continue
            t_ = f - born
            if t_ < FALL:
                q = t_ / FALL
                dy = 1.3 * (1 - q * q)             # 중력 가속 낙하
            elif t_ < FALL + 3:
                dy = 0.05 * math.sin(math.pi * (t_ - FALL) / 3)  # 착지 바운스
            else:
                dy = 0.0
            flash = FALL <= t_ < FALL + 2          # 착지 순간 번쩍
            for x, y, z, ch, cl in pts:
                plot_gift(x, y + dy, z, ch, 'W' if flash else cl)
        if n_on > 10:                              # 바닥에 비친 불빛
            for _ in range(20):
                ry = rng.randint(HY + 1, HY + 5)
                rx = int(CX) + rng.randint(-46, 46)
                if (ry, rx) in ground:
                    glyph[ry][rx], cls[ry][rx] = '.', 'y2'

    if f >= F2 - 8:                                # 꼭대기 큰 별
        sy0 = int(HY - 0.5 * SY - (1.08 - 0.5) * SY + 0.5)
        sx0 = int(CX)
        pulse = (f // 4) % 2 == 0
        pat = [(0, 0, '@', 'Y'),                   # 중심
               (-1, 0, '*', 'Y'), (1, 0, '*', 'Y'),
               (-2, 0, '*', 'Y'), (2, 0, '*', 'Y'),
               (-3, 0, '*', 'y'), (3, 0, '*', 'y'),
               (0, -1, '*', 'Y'), (0, 1, '*', 'Y'),
               (-1, -1, '*', 'y'), (1, -1, '*', 'y'),
               (-1, 1, '*', 'y'), (1, 1, '*', 'y'),
               (0, -2, '*', 'y'), (0, 2, '*', 'y')]
        if pulse:                                  # 광선이 번갈아 뻗는다
            pat += [(-5, 0, '-', 'y1'), (5, 0, '-', 'y1'),
                    (-4, 0, '*', 'y1'), (4, 0, '*', 'y1'),
                    (0, -3, '|', 'y1'), (0, 3, "'", 'y1'),
                    (-2, -1, '.', 'y1'), (2, -1, '.', 'y1'),
                    (-2, 1, '.', 'y1'), (2, 1, '.', 'y1')]
        for dx, dy, ch, cl in pat:
            if 0 <= sy0 + dy < ROWS and 0 <= sx0 + dx < COLS:
                glyph[sy0 + dy][sx0 + dx], cls[sy0 + dy][sx0 + dx] = ch, cl

    deg = math.degrees(th) % 360
    return (glyph, cls, oglyph, ocls, sglyph, scls, bglyph, bcls,
            wglyph, wcls, tglyph, tcls, (round(deg, 2), n_on, letters))
# <</code-window>>


def build_sky_ground():
    sky = []
    for _ in range(230):
        sky.append((rng.randrange(COLS), rng.randrange(0, HY - 3),
                    rng.choice('...++*'), rng.randrange(T),
                    rng.choice((40, 60, 80, 120))))
    ground = {}
    for idx, ry in enumerate(range(HY + 1, HY + 7)):
        col = rng.randrange(0, 3)
        while col < COLS:
            run, gap = rng.randint(2, 12), rng.randint(1, 3 + idx * 2)
            for ccol in range(col, min(col + run, COLS)):
                ch = '-' if rng.random() > 0.12 else '.'
                near = idx < 3 and abs(ccol - CX) < 50
                ground[(ry, ccol)] = (ch, 'f0' if near else 'f1')
            col += run + gap
    snow = []                                      # 눈: 80행 주기로 끊김 없이 낙하
    for _ in range(140):
        big = rng.random() < 0.3
        snow.append((rng.randrange(COLS), rng.randrange(80),
                     2 if big else 1, rng.random(),
                     '*' if big else rng.choice('..+'),
                     's0' if big else 's1'))
    return sky, ground, snow


def to_html(glyph, cls):
    def flush(cur, buf):
        txt = ''.join(buf).replace('&', '&amp;').replace('<', '&lt;')
        return f'<span class="{cur}">{txt}</span>' if cur else txt

    rows = []
    for gl, cl in zip(glyph, cls):
        parts, cur, buf = [], None, []
        for ch, cc in zip(gl, cl):
            if cc != cur:
                if buf:
                    parts.append(flush(cur, buf))
                cur, buf = cc, []
            buf.append(ch)
        if buf:
            parts.append(flush(cur, buf))
        rows.append(''.join(parts).rstrip())
    return '\n'.join(rows)


def to_text(glyph):
    return '\n'.join(''.join(row).rstrip() for row in glyph)


# ── 코드 패널: 이 파일 자신의 소스를 하이라이트해서 보여준다 ──
TOKEN = re.compile(
    r"(?P<com>#.*)"
    r"|(?P<str>\"[^\"]*\"|'[^']*')"
    r"|(?P<kw>\b(?:def|return|for|in|if|elif|else|while|import|from|and|or|"
    r"not|None|True|False|with|as|lambda|break|continue|class)\b)"
    r"|(?P<num>\b\d+(?:\.\d+)?\b)"
    r"|(?P<fn>\b[A-Za-z_]\w*(?=\())")
TOKCLS = {'com': 'cc', 'str': 'cs', 'kw': 'ck', 'num': 'cn', 'fn': 'cf'}


def highlight_source():
    src = open(__file__, encoding='utf-8').read()
    body = src.split('# <<code-window>>')[1].split('# <</code-window>>')[0]
    lines = body.strip('\n').split('\n')
    out = []
    for n, line in enumerate(lines, start=24):
        parts, pos = [f'<span class="cl">{n:>4}</span>  '], 0
        for m in TOKEN.finditer(line):
            parts.append(escape(line[pos:m.start()]))
            parts.append(f'<span class="{TOKCLS[m.lastgroup]}">{escape(m.group())}</span>')
            pos = m.end()
        parts.append(escape(line[pos:]))
        out.append(''.join(parts))
    return '\n'.join(out)


PAGE_TMPL = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="파이썬이 글자 하나하나 계산해 그리는, 회전하며 자라나는 ASCII 크리스마스 트리.">
<title>tree.py</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ctext y='13' font-size='13'%3E%F0%9F%8E%84%3C/text%3E%3C/svg%3E">
<style>
/* Hallmark v2.0.0 · direction: custom (user reference: viral ascii-tree reel) · genre: atmospheric · shape: app screen · posture: drenched · surface: absolute · nav: none (full-screen art) · footer: status bar and code panel · hero: the tree itself · signature: python-rendered rotating ascii tree */
/* critique: one idea on one screen; the motion is the content; reduced-motion holds the finished still */
:root{
  --bg:#04070e; --panel:#060a13; --line:#141d2c; --nebula:#081425;
  --star:#8fa3b8; --star-dim:#43536a;
  --g0:#7cd98f; --g1:#3fa05f; --g2:#1f5c39; --g3:#153f28;
  --snow:#eef5f1; --trunk:#8a5a3b;
  --gold:#ffd96a; --gold-dim:#b89a4e; --gold-bloom:#fff3c4;
  --red:#ff5a52; --blue:#6aa8ff; --pink:#ff8fd3;
  --red-dim:#a83e38; --blue-dim:#44709e; --pink-dim:#a85f8e;
  --skin:#f2c99b; --trunk-dim:#5e3d28; --coal:#434e5e;
  --silver:#e8f1fa; --glow-silver:rgba(190,220,255,.55);
  --orn-red:#ff6b63; --orn-blue:#7db8ff; --orn-pink:#ff9ede;
  --glow-blue:rgba(125,184,255,.5); --glow-pink:rgba(255,158,222,.5);
  --glow-green:rgba(124,217,143,.45);
  --glow-scene:rgba(90,170,120,.22); --glow-gold-lo:rgba(255,217,106,.35);
  --glow-gold-hi:rgba(255,217,106,.5); --glow-red:rgba(255,90,82,.4);
  --glow-snow:rgba(255,255,255,.8);
  --floor:#2a3c57; --floor-dim:#182438;
  --hud:#7e94ab; --hud-dim:#44566b;
  --code-txt:#9fb0c7; --code-kw:#ff6b6b; --code-fn:#7aa8ff; --code-num:#ffc46b;
  --code-str:#8fd48a; --code-com:#45526b; --code-ln:#2e3b52;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
html,body{margin:0;height:100%;overflow-x:clip}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{height:100vh;height:100dvh}
body{display:flex;flex-direction:column;background:var(--bg);color-scheme:dark;font-family:var(--mono)}
#stage{flex:1;min-height:0;display:grid;place-items:center;overflow:hidden;
  background:radial-gradient(ellipse 60% 45% at 50% 58%,var(--nebula) 0%,transparent 70%)}
#wrap{position:relative}
#scene,#balls,#gifts,#santa,#msg,#snow{margin:0;font-family:var(--mono);
  font-size:clamp(4px,min(1.26vw,0.95vh),8px);
  font-size:clamp(4px,min(1.26vw,0.95svh),8px);
  line-height:1.05;color:var(--g1);text-shadow:0 0 6px var(--glow-scene)}
#balls,#gifts,#santa,#msg,#snow{position:absolute;inset:0;pointer-events:none}
.w0{color:var(--snow)}
.g0{color:var(--g0)}.g1{color:var(--g1)}.g2{color:var(--g2)}.g3{color:var(--g3)}
.t{color:var(--trunk)}
.Y{color:var(--gold-bloom);text-shadow:0 0 6px var(--gold),0 0 16px var(--glow-gold-hi)}
.y{color:var(--gold);text-shadow:0 0 5px var(--glow-gold-lo)}
.y1{color:var(--gold-dim)}
.y2{color:var(--gold-dim);opacity:.6}
.r0{color:var(--red);text-shadow:0 0 5px var(--glow-red)}
.R{color:var(--red);text-shadow:0 0 6px var(--red),0 0 14px var(--glow-red)}
.b0{color:var(--blue)}.p0{color:var(--pink)}
.r1{color:var(--red-dim)}.b1{color:var(--blue-dim)}.p1{color:var(--pink-dim)}
.sk{color:var(--skin)}.td{color:var(--trunk-dim)}.k{color:var(--coal)}
.oR{color:var(--orn-red);text-shadow:0 0 6px var(--glow-red)}
.oB{color:var(--orn-blue);text-shadow:0 0 6px var(--glow-blue)}
.oP{color:var(--orn-pink);text-shadow:0 0 6px var(--glow-pink)}
.si{color:var(--silver);text-shadow:0 0 7px var(--glow-silver)}
.oG{color:var(--gold);text-shadow:0 0 7px var(--glow-gold-hi)}
.mR{color:var(--red);text-shadow:0 0 7px var(--glow-red)}
.mG{color:var(--g0);text-shadow:0 0 7px var(--glow-green)}
.W{color:var(--snow);text-shadow:0 0 9px var(--glow-snow)}
.s0{color:var(--star)}.s1{color:var(--star-dim)}
.f0{color:var(--floor)}.f1{color:var(--floor-dim)}
.hud{position:absolute;left:6px;bottom:2px;font-size:clamp(7px,1.3vw,11px);line-height:1.55;color:var(--hud)}
.hud .dim{color:var(--hud-dim)}
#li{margin-left:3ch}
.btns{position:absolute;right:6px;bottom:2px;display:flex;flex-direction:column;align-items:flex-end;gap:2px}
.btns button{background:none;border:0;padding:4px;cursor:pointer;
  font-family:var(--mono);font-size:clamp(7px,1.3vw,11px);color:var(--hud)}
.btns button:hover{color:var(--snow)}
.btns button:active{color:var(--gold)}
.btns button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
#bar{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 10px;
  padding:4px 16px;border-top:1px solid var(--line);color:var(--hud-dim);font-size:11px}
#bar span{white-space:nowrap}
#bar .credit{opacity:.65;font-size:10px}
#panel{height:108px;overflow:hidden;background:var(--panel);border-top:1px solid var(--line);color:var(--code-txt);
  padding-bottom:env(safe-area-inset-bottom)}
@media (max-height:700px){#panel{height:64px}}
#code{margin:0;padding:8px 16px;font-family:var(--mono);font-size:10px;line-height:1.55;color:var(--code-txt)}
.ck{color:var(--code-kw)}.cf{color:var(--code-fn)}.cn{color:var(--code-num)}
.cs{color:var(--code-str)}.cc{color:var(--code-com)}.cl{color:var(--code-ln)}
@media (prefers-reduced-motion:reduce){ .Y,.y,.W{text-shadow:none} }
</style>
<div id="stage">
  <div id="wrap">
    <pre id="scene" aria-hidden="true">@@INITIAL@@</pre>
    <pre id="balls" aria-hidden="true">@@BINIT@@</pre>
    <pre id="gifts" aria-hidden="true">@@GINIT@@</pre>
    <pre id="santa" aria-hidden="true">@@SINIT@@</pre>
    <pre id="msg" aria-hidden="true">@@MINIT@@</pre>
    <pre id="snow" aria-hidden="true">@@WINIT@@</pre>
    <div class="hud" role="img" aria-label="파이썬이 렌더링하는 ASCII 크리스마스 트리 애니메이션"><div class="dim">@hajin.2026.11.17 &#8594; 2026</div><div><span id="rot">rotation @@ROT0@@&#176;</span><span id="li">lights @@LI0@@</span></div><div id="le">letters @@LE0@@</div></div>
    <div class="btns"><button id="bgmbtn" type="button" aria-pressed="false">[ bgm: off ]</button><button id="msgbtn" type="button" aria-pressed="true">[ message: on ]</button><button id="snowbtn" type="button" aria-pressed="true">[ snow: on ]</button><button id="santabtn" type="button" aria-pressed="true">[ santa: on ]</button><button id="ballbtn" type="button" aria-pressed="true">[ ornaments: on ]</button><button id="giftbtn" type="button" aria-pressed="true">[ gifts: on ]</button></div>
  </div>
</div>
<audio id="bgma" src="bgm.mp3" loop preload="auto"></audio>
<div id="bar"><span>py tree.py</span><span class="credit">bgm: Jingle Bells, Kevin MacLeod (incompetech.com) CC BY 4.0</span><span>running @ @@FPS@@ fps</span></div>
<div id="panel"><pre id="code">@@CODE@@</pre></div>
<script>
const F=@@FRAMES@@,G=@@GIFTS@@,SA=@@SANTA@@,BA=@@BALLS@@,SN=@@SNOW@@,MG=@@MSGF@@,M=@@META@@,T=@@T@@,FPS=@@FPS@@;
const scene=document.getElementById('scene'),gifts=document.getElementById('gifts'),
      santa=document.getElementById('santa'),balls=document.getElementById('balls'),
      snow=document.getElementById('snow'),msg=document.getElementById('msg'),
      rot=document.getElementById('rot'),
      li=document.getElementById('li'),le=document.getElementById('le'),
      code=document.getElementById('code'),panel=document.getElementById('panel');
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
let i=reduce?T-1:0;
function bindToggle(btn,layer,arr,name){
  let on=true;
  btn.addEventListener('click',()=>{
    on=!on;
    layer.style.display=on?'':'none';
    if(on)layer.innerHTML=arr[i];
    btn.setAttribute('aria-pressed',String(on));
    btn.textContent='[ '+name+': '+(on?'on':'off')+' ]';
  });
  return ()=>on;
}
const giftsOn=bindToggle(document.getElementById('giftbtn'),gifts,G,'gifts');
const santaOn=bindToggle(document.getElementById('santabtn'),santa,SA,'santa');
const ballsOn=bindToggle(document.getElementById('ballbtn'),balls,BA,'ornaments');
const snowOn=bindToggle(document.getElementById('snowbtn'),snow,SN,'snow');
const msgOn=bindToggle(document.getElementById('msgbtn'),msg,MG,'message');
const bgmbtn=document.getElementById('bgmbtn'),bgma=document.getElementById('bgma');
let bgmOn=false;
function syncBgm(){
  bgmbtn.setAttribute('aria-pressed',String(bgmOn));
  bgmbtn.textContent=bgmOn?'[ bgm: on ]':'[ bgm: off ]';
}
function setBgm(on){
  bgmOn=on;
  if(on){bgma.volume=0.6;bgma.play().catch(()=>{bgmOn=false;syncBgm();});}
  else bgma.pause();
  syncBgm();
}
bgmbtn.addEventListener('click',()=>setBgm(!bgmOn));
bgma.volume=0.6;
bgma.play().then(()=>{bgmOn=true;syncBgm();}).catch(()=>{
  const kick=(e)=>{                               // 자동재생이 막히면 첫 상호작용에서 시작
    removeEventListener('pointerdown',kick);
    removeEventListener('keydown',kick);
    if(bgmbtn.contains(e.target))return;          // bgm 버튼 클릭은 버튼 핸들러에 맡긴다
    if(!bgmOn)setBgm(true);
  };
  addEventListener('pointerdown',kick);
  addEventListener('keydown',kick);
});
function show(f){
  scene.innerHTML=F[f];
  if(giftsOn())gifts.innerHTML=G[f];
  if(santaOn())santa.innerHTML=SA[f];
  if(ballsOn())balls.innerHTML=BA[f];
  if(snowOn())snow.innerHTML=SN[f];
  if(msgOn())msg.innerHTML=MG[f];
  rot.textContent='rotation '+M[f][0].toFixed(2).padStart(6,'0')+'\\u00B0';
  li.textContent='lights '+M[f][1];
  le.textContent='letters '+M[f][2].toLocaleString('en-US');
  const over=code.offsetHeight-panel.offsetHeight;
  if(over>0)code.style.transform='translateY(-'+(over*f/(T-1)).toFixed(1)+'px)';
}
show(i);
if(!reduce)setInterval(()=>{i=(i+1)%T;show(i)},1000/FPS);
</script>
"""


def build_page():
    scene = build_points()
    sky, ground, snow = build_sky_ground()
    frames, gift_frames, santa_frames, ball_frames, snow_frames, msg_frames, meta = \
        [], [], [], [], [], [], []
    for f in range(T):
        glyph, cls, og, oc, sg, sc, bg, bc, wg, wc, tg, tc, m = \
            render(f, scene, sky, ground, snow)
        frames.append(to_html(glyph, cls))
        gift_frames.append(to_html(og, oc))
        santa_frames.append(to_html(sg, sc))
        ball_frames.append(to_html(bg, bc))
        snow_frames.append(to_html(wg, wc))
        msg_frames.append(to_html(tg, tc))
        meta.append(m)
        if f % 40 == 0:
            print(f'\r프레임 생성 {f}/{T}', end='', flush=True)
    print(f'\r프레임 생성 {T}/{T}')
    last = meta[-1]
    page = (PAGE_TMPL
            .replace('@@FRAMES@@', json.dumps(frames))
            .replace('@@GIFTS@@', json.dumps(gift_frames))
            .replace('@@SANTA@@', json.dumps(santa_frames))
            .replace('@@BALLS@@', json.dumps(ball_frames))
            .replace('@@SNOW@@', json.dumps(snow_frames))
            .replace('@@MSGF@@', json.dumps(msg_frames))
            .replace('@@META@@', json.dumps(meta))
            .replace('@@INITIAL@@', frames[-1])
            .replace('@@GINIT@@', gift_frames[-1])
            .replace('@@SINIT@@', santa_frames[-1])
            .replace('@@BINIT@@', ball_frames[-1])
            .replace('@@WINIT@@', snow_frames[-1])
            .replace('@@MINIT@@', msg_frames[-1])
            .replace('@@CODE@@', highlight_source())
            .replace('@@ROT0@@', f'{last[0]:06.2f}')
            .replace('@@LI0@@', str(last[1]))
            .replace('@@LE0@@', f'{last[2]:,}')
            .replace('@@T@@', str(T))
            .replace('@@FPS@@', str(FPS)))
    return page


def main():
    if '--build' in sys.argv:                      # 정적 배포용 index.html 생성
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'hazzin-tree', 'index.html')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(build_page())
        print('→', out, f'({os.path.getsize(out) // 1024}KB)')
        return

    if '--dump' in sys.argv:
        idx = sys.argv.index('--dump')
        f = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else T - 1
        scene = build_points()
        sky, ground, snow = build_sky_ground()
        glyph, _, og, _, sg, _, bg, _, wg, _, tg, _, m = \
            render(f % T, scene, sky, ground, snow)
        for lay in (bg, og, sg, wg, tg):           # 미리보기에선 오버레이 합성
            for r in range(ROWS):
                for ccol in range(COLS):
                    if lay[r][ccol] != ' ':
                        glyph[r][ccol] = lay[r][ccol]
        print(to_text(glyph))
        print('meta:', m)
        return

    page = build_page().encode('utf-8')
    page_gz = gzip.compress(page)
    print(f'페이지 {len(page)//1024}KB (gzip {len(page_gz)//1024}KB)')

    bgm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'hazzin-tree', 'bgm.mp3')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/bgm.mp3' and os.path.exists(bgm_path):
                with open(bgm_path, 'rb') as fh:
                    data = fh.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path not in ('/', '/index.html'):
                self.send_error(404)
                return
            gz = 'gzip' in self.headers.get('Accept-Encoding', '')
            body = page_gz if gz else page
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            if gz:
                self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = None
    for port in range(8000, 8011):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    print(f'\U0001F384  http://localhost:{server.server_address[1]}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
