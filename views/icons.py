"""Iconos del POS dibujados con Pillow (sin archivos externos).

Uso:  from icons import icon;  icon('cart', '#023047', 20)  ->  CTkImage
Cada icono se dibuja a 128 px y CTkImage lo reduce, así se ve nítido en pantallas HiDPI.
Requiere:  pip install pillow
"""
import math
from functools import lru_cache
from PIL import Image, ImageDraw
import customtkinter as ctk

_S, _W = 128, 10


def _dot(d, x, y, r, c):
    d.ellipse((x - r, y - r, x + r, y + r), fill=c)


def _line(d, pts, c, w=_W, close=False):
    pts = list(pts) + ([pts[0]] if close else [])
    d.line(pts, fill=c, width=w, joint='curve')
    for x, y in pts:          # puntas y esquinas redondeadas
        _dot(d, x, y, w / 2, c)


def _search(d, c):
    d.ellipse((16, 16, 80, 80), outline=c, width=_W)
    _line(d, [(72, 72), (110, 110)], c, _W + 2)


def _cart(d, c):
    _line(d, [(10, 24), (30, 24), (44, 82), (104, 82), (116, 40), (34, 40)], c)
    _dot(d, 56, 106, 9, c)
    _dot(d, 96, 106, 9, c)


def _trash(d, c):
    _line(d, [(22, 36), (106, 36)], c)
    _line(d, [(50, 36), (50, 20), (78, 20), (78, 36)], c)
    _line(d, [(34, 36), (40, 108), (88, 108), (94, 36)], c)
    _line(d, [(56, 56), (56, 88)], c, 8)
    _line(d, [(72, 56), (72, 88)], c, 8)


def _logout(d, c):
    _line(d, [(58, 18), (20, 18), (20, 110), (58, 110)], c)
    _line(d, [(46, 64), (110, 64)], c)
    _line(d, [(88, 42), (110, 64), (88, 86)], c)


def _info(d, c):
    d.ellipse((12, 12, 116, 116), outline=c, width=_W)
    _dot(d, 64, 38, 6, c)
    _line(d, [(64, 58), (64, 92)], c)


def _plus(d, c):
    _line(d, [(64, 20), (64, 108)], c)
    _line(d, [(20, 64), (108, 64)], c)


def _minus(d, c):
    _line(d, [(20, 64), (108, 64)], c)


def _close(d, c):
    _line(d, [(28, 28), (100, 100)], c)
    _line(d, [(100, 28), (28, 100)], c)


def _check(d, c):
    _line(d, [(22, 68), (52, 96), (106, 34)], c, _W + 2)


def _cash(d, c):
    d.rounded_rectangle((8, 32, 120, 96), radius=10, outline=c, width=_W)
    d.ellipse((46, 46, 82, 82), outline=c, width=8)
    _dot(d, 25, 64, 5, c)
    _dot(d, 103, 64, 5, c)


def _card(d, c):
    d.rounded_rectangle((8, 26, 120, 102), radius=12, outline=c, width=_W)
    d.rectangle((8, 46, 120, 60), fill=c)
    _line(d, [(24, 84), (54, 84)], c, 8)


def _bank(d, c):
    _line(d, [(64, 14), (12, 46), (116, 46)], c, close=True)
    for x in (30, 54, 74, 98):
        _line(d, [(x, 60), (x, 92)], c, 8)
    _line(d, [(12, 110), (116, 110)], c)


def _barcode(d, c):
    for x, w in ((14, 8), (30, 16), (56, 8), (72, 14), (96, 8), (110, 6)):
        d.rectangle((x, 22, x + w, 106), fill=c)


def _calc(d, c):
    d.rounded_rectangle((26, 10, 102, 118), radius=12, outline=c, width=_W)
    d.rectangle((40, 26, 88, 46), fill=c)
    for y in (68, 86, 104):
        for x in (46, 64, 82):
            _dot(d, x, y, 5, c)


def _receipt(d, c):
    _line(d, [(28, 12), (100, 12), (100, 116), (88, 104), (76, 116), (64, 104),
              (52, 116), (40, 104), (28, 116)], c, 8, close=True)
    for x2, y in ((84, 40), (84, 60), (68, 80)):
        _line(d, [(44, y), (x2, y)], c, 8)


def _user(d, c):
    d.ellipse((40, 12, 88, 60), outline=c, width=_W)
    d.arc((18, 70, 110, 170), 180, 360, fill=c, width=_W)


def _box(d, c):
    _line(d, [(64, 12), (112, 36), (112, 92), (64, 116), (16, 92), (16, 36)], c, close=True)
    _line(d, [(16, 36), (64, 60), (112, 36)], c)
    _line(d, [(64, 60), (64, 116)], c)


def _users(d, c):
    clear = (0, 0, 0, 0)
    d.ellipse((64, 18, 104, 58), outline=c, width=_W)           # persona de atrás
    d.arc((52, 70, 132, 150), 180, 360, fill=c, width=_W)
    d.ellipse((18, 10, 74, 66), fill=clear)                     # "recorte" alrededor de la de adelante
    d.pieslice((-2, 64, 94, 160), 180, 360, fill=clear)
    d.ellipse((26, 18, 66, 58), outline=c, width=_W)            # persona de adelante
    d.arc((6, 70, 86, 150), 180, 360, fill=c, width=_W)


def _chart(d, c):
    d.rounded_rectangle((14, 70, 42, 114), radius=6, fill=c)
    d.rounded_rectangle((50, 40, 78, 114), radius=6, fill=c)
    d.rounded_rectangle((86, 14, 114, 114), radius=6, fill=c)


def _gear(d, c):
    for k in range(8):
        a = k * math.pi / 4
        _line(d, [(64 + 36 * math.cos(a), 64 + 36 * math.sin(a)),
                  (64 + 52 * math.cos(a), 64 + 52 * math.sin(a))], c, 16)
    d.ellipse((24, 24, 104, 104), fill=c)
    d.ellipse((46, 46, 82, 82), fill=(0, 0, 0, 0))


def _store(d, c):
    _line(d, [(12, 46), (22, 16), (106, 16), (116, 46)], c, close=True)
    _line(d, [(24, 48), (24, 112), (104, 112), (104, 48)], c)
    _line(d, [(52, 112), (52, 74), (76, 74), (76, 112)], c)


_ICONS = {
    'search': _search, 'cart': _cart, 'trash': _trash, 'logout': _logout, 'info': _info,
    'plus': _plus, 'minus': _minus, 'close': _close, 'check': _check, 'cash': _cash,
    'card': _card, 'bank': _bank, 'barcode': _barcode, 'calc': _calc,
    'receipt': _receipt, 'user': _user,
    'box': _box, 'users': _users, 'chart': _chart, 'gear': _gear, 'store': _store,
}


@lru_cache(maxsize=None)
def icon(name, color='#023047', size=18):
    img = Image.new('RGBA', (_S, _S), (0, 0, 0, 0))
    _ICONS[name](ImageDraw.Draw(img), color)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))