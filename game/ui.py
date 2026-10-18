"""Reusable UI components and drawing helpers (buttons, inputs, panels...).

All drawing uses Pygame primitives and system fonts, so the game needs no
asset files.
"""

from __future__ import annotations

import math

import pygame

from . import settings as S

# Mouse position in VIRTUAL (1280x720) coordinates - updated by Game every frame.
MOUSE = [0, 0]

_SANS = "segoeui,inter,helveticaneue,helvetica,arial,dejavusans,liberationsans"
_MONO = "consolas,jetbrainsmono,cascadiamono,menlo,dejavusansmono,liberationmono,couriernew"
_fonts = {}
_text_cache = {}


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _fonts:
        try:
            f = pygame.font.SysFont(_MONO if mono else _SANS, size, bold=bold)
        except Exception:
            f = pygame.font.Font(None, int(size * 1.3))
        _fonts[key] = f
    return _fonts[key]


def render(text, size, color, bold=False, mono=False):
    key = (text, size, color, bold, mono)
    surf = _text_cache.get(key)
    if surf is None:
        if len(_text_cache) > 3000:
            _text_cache.clear()
        surf = font(size, bold, mono).render(text, True, color)
        _text_cache[key] = surf
    return surf


def text(surf, s, size, color, pos, anchor="topleft", bold=False, mono=False):
    img = render(str(s), size, color, bold, mono)
    rect = img.get_rect()
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))
    surf.blit(img, rect)
    return rect


def text_width(s, size, bold=False, mono=False):
    return font(size, bold, mono).size(str(s))[0]


def ellipsize(s, size, width, bold=False, mono=False):
    s = str(s)
    if text_width(s, size, bold, mono) <= width:
        return s
    while s and text_width(s + "...", size, bold, mono) > width:
        s = s[:-1]
    return s + "..."


def wrap(s, size, width, bold=False, mono=False):
    lines = []
    for para in str(s).split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if text_width(trial, size, bold, mono) <= width:
                line = trial
            else:
                if line:
                    lines.append(line)
                # break very long words
                while text_width(w, size, bold, mono) > width and len(w) > 1:
                    cut = len(w)
                    while cut > 1 and text_width(w[:cut], size, bold, mono) > width:
                        cut -= 1
                    lines.append(w[:cut])
                    w = w[cut:]
                line = w
        lines.append(line)
    return lines


def paragraph(surf, s, size, color, x, y, width, gap=5, bold=False, mono=False, max_lines=None):
    lh = font(size, bold, mono).get_linesize() + gap - 4
    lines = wrap(s, size, width, bold, mono)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1] + " ...", size, width, bold, mono)
    for line in lines:
        text(surf, line, size, color, (x, y), bold=bold, mono=mono)
        y += lh
    return y


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------
def panel(surf, rect, fill=S.PANEL, border=S.BORDER, radius=12, width=1):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, width, border_radius=radius)
    return rect


def alpha_rect(surf, rect, color, alpha, radius=10):
    rect = pygame.Rect(rect)
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (*color, alpha), layer.get_rect(), border_radius=radius)
    surf.blit(layer, rect.topleft)


def glow(surf, center, color, radius, strength=90):
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(4, 0, -1):
        r = int(radius * i / 4)
        a = int(strength * (1 - i / 5) / 2)
        pygame.draw.circle(layer, (*color, a), (radius, radius), r)
    surf.blit(layer, (int(center[0]) - radius, int(center[1]) - radius))


def circle(surf, color, center, r, width=0):
    pygame.draw.circle(surf, color, (int(center[0]), int(center[1])), int(r), width)


def line(surf, color, a, b, width=1):
    if width <= 1:
        pygame.draw.aaline(surf, color, a, b)
    else:
        pygame.draw.line(surf, color, a, b, width)


def dashed_line(surf, color, a, b, width=2, dash=8, gap=6):
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay)
    if length == 0:
        return
    dx, dy = (bx - ax) / length, (by - ay) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        pygame.draw.line(surf, color, (ax + dx * pos, ay + dy * pos), (ax + dx * end, ay + dy * end), width)
        pos += dash + gap


def check_mark(surf, color, center, size=7, width=2):
    x, y = center
    pts = [(x - size, y), (x - size * 0.3, y + size * 0.7), (x + size, y - size * 0.7)]
    pygame.draw.lines(surf, color, False, pts, width)


def cross_mark(surf, color, center, size=6, width=2):
    x, y = center
    pygame.draw.line(surf, color, (x - size, y - size), (x + size, y + size), width)
    pygame.draw.line(surf, color, (x - size, y + size), (x + size, y - size), width)


def pill(surf, s, pos, fg, bg=None, size=S.FS_XS, anchor="topleft", bold=True, pad=(9, 3)):
    w = text_width(s, size, bold) + pad[0] * 2
    h = font(size, bold).get_height() + pad[1] * 2
    rect = pygame.Rect(0, 0, w, h)
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))
    pygame.draw.rect(surf, bg or S.PANEL_HI, rect, border_radius=h // 2)
    text(surf, s, size, fg, rect.center, "center", bold)
    return rect


def status_dot(surf, color, center, r=4):
    circle(surf, color, center, r)


def section_title(surf, s, x, y, color=S.TEXT_MUTED):
    text(surf, s.upper(), S.FS_XS, color, (x, y), bold=True)
    return y + 22


def key_value(surf, key, value, x, y, w, size=S.FS_SM, vcolor=S.TEXT, mono=True, key_w=None):
    text(surf, key, size, S.TEXT_DIM, (x, y))
    kw = key_w if key_w is not None else 108
    v = ellipsize(value, size, w - kw, mono=mono)
    text(surf, v, size, vcolor, (x + w, y), "topright", mono=mono)
    return y + font(size).get_linesize() + 3


def meter(surf, rect, frac, color, bg=S.PANEL_HI):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, bg, rect, border_radius=rect.height // 2)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        fill = rect.copy()
        fill.width = max(rect.height, int(rect.width * frac))
        pygame.draw.rect(surf, color, fill, border_radius=rect.height // 2)


def health_color(value):
    return S.GREEN if value >= 70 else S.AMBER if value >= 40 else S.RED


def grid_background(surf, offset=0.0):
    surf.fill(S.BG)
    step = 32
    off = int(offset) % step
    w, h = surf.get_size()
    for x in range(-off, w, step):
        pygame.draw.line(surf, S.BG_GRID, (x, 0), (x, h))
    for y in range(-off, h, step):
        pygame.draw.line(surf, S.BG_GRID, (0, y), (w, y))


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def mouse_in(rect):
    return pygame.Rect(rect).collidepoint(MOUSE)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
class Button:
    STYLES = {
        # fill, hover fill, text, border
        "primary": (S.ACCENT, (94, 234, 212), (6, 30, 30), None),
        "secondary": (S.PANEL_HI, (36, 52, 80), S.TEXT, S.BORDER_HI),
        "ghost": (S.PANEL, S.PANEL_HI, S.TEXT_DIM, S.BORDER),
        "danger": (S.RED_SOFT, (88, 26, 46), S.RED, (110, 36, 58)),
        "warn": (S.AMBER_SOFT, (80, 58, 18), S.AMBER, (100, 72, 22)),
    }

    def __init__(self, rect, label, on_click=None, style="primary", hotkey=None,
                 icon=None, enabled=True, size=S.FS_MD, hint=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.style = style
        self.hotkey = hotkey
        self.icon = icon
        self.enabled = enabled
        self.size = size
        self.hint = hint          # small hotkey hint shown on the right
        self.hover = 0.0
        self.visible = True
        self.selected = False

    def handle(self, e):
        if not (self.visible and self.enabled):
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            if self.on_click:
                self.on_click()
            return True
        if e.type == pygame.KEYDOWN and self.hotkey is not None and e.key == self.hotkey:
            if self.on_click:
                self.on_click()
            return True
        return False

    def update(self, dt):
        target = 1.0 if (self.enabled and self.visible and self.rect.collidepoint(MOUSE)) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)

    def draw(self, surf):
        if not self.visible:
            return
        fill, hover_fill, fg, border = self.STYLES[self.style]
        if not self.enabled:
            fill, fg, border = S.PANEL_ALT, S.TEXT_MUTED, S.BORDER
            hover_fill = fill
        if self.selected:
            fill, border, fg = S.ACCENT_SOFT, S.ACCENT, S.TEXT
            hover_fill = S.ACCENT_SOFT
        color = lerp_color(fill, hover_fill, self.hover)
        r = self.rect.move(0, -int(self.hover * 1))
        pygame.draw.rect(surf, color, r, border_radius=10)
        if border:
            pygame.draw.rect(surf, border, r, 1, border_radius=10)
        if self.icon and not self.label:
            draw_icon(surf, self.icon, r.center, fg)
            return
        cx = r.centerx
        if self.hint:
            text(surf, self.hint, S.FS_XS, lerp_color(fg, color, 0.45), (r.right - 10, r.centery), "midright", True)
            cx -= 8
        if self.icon:
            content = 16 + 8 + text_width(self.label, self.size, True)
            start = cx - content // 2
            draw_icon(surf, self.icon, (start + 8, r.centery), fg)
            text(surf, self.label, self.size, fg, (start + 24, r.centery), "midleft", bold=True)
        else:
            text(surf, self.label, self.size, fg, (cx, r.centery), "center", bold=True)


def draw_icon(surf, name, center, color):
    x, y = center
    if name == "pause":
        pygame.draw.rect(surf, color, (x - 6, y - 7, 4, 14), border_radius=1)
        pygame.draw.rect(surf, color, (x + 2, y - 7, 4, 14), border_radius=1)
    elif name == "play":
        pygame.draw.polygon(surf, color, [(x - 5, y - 7), (x - 5, y + 7), (x + 7, y)])
    elif name == "restart":
        rect = pygame.Rect(x - 7, y - 7, 14, 14)
        pygame.draw.arc(surf, color, rect, 0.6, 5.6, 2)
        pygame.draw.polygon(surf, color, [(x + 3, y - 9), (x + 9, y - 4), (x + 2, y - 2)])
    elif name == "close":
        cross_mark(surf, color, center, 5, 2)
    elif name == "bolt":
        pygame.draw.polygon(surf, color, [(x + 2, y - 8), (x - 5, y + 1), (x, y + 1), (x - 2, y + 8), (x + 5, y - 1), (x, y - 1)])
    elif name == "wave":
        pts = [(x - 8 + i, y + math.sin(i / 2.2) * 4) for i in range(17)]
        pygame.draw.lines(surf, color, False, pts, 2)
    elif name == "link":
        pygame.draw.line(surf, color, (x - 7, y + 5), (x + 7, y - 5), 2)
        circle(surf, color, (x - 7, y + 5), 3)
        circle(surf, color, (x + 7, y - 5), 3)
    elif name == "arrow":
        pygame.draw.line(surf, color, (x - 7, y), (x + 6, y), 2)
        pygame.draw.polygon(surf, color, [(x + 7, y), (x + 1, y - 5), (x + 1, y + 5)])


class TextInput:
    def __init__(self, rect, value="", placeholder="", max_len=40, multiline=False):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.placeholder = placeholder
        self.max_len = max_len
        self.multiline = multiline
        self.focused = False
        self.blink = 0.0
        self.error = False

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            was = self.focused
            self.focused = self.rect.collidepoint(e.pos)
            return self.focused and not was
        if not self.focused:
            return False
        if e.type == pygame.TEXTINPUT:
            for ch in e.text:
                if len(self.value) < self.max_len and ch.isprintable():
                    self.value += ch
            self.error = False
            self.blink = 0
            return True
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE:
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    self.value = self.value.rstrip()
                    self.value = self.value[: self.value.rfind(" ") + 1] if " " in self.value else ""
                else:
                    self.value = self.value[:-1]
                self.blink = 0
                return True
        return False

    def update(self, dt):
        self.blink += dt

    def draw(self, surf):
        border = S.RED if self.error else (S.ACCENT if self.focused else S.BORDER_HI)
        pygame.draw.rect(surf, S.PANEL_ALT, self.rect, border_radius=10)
        pygame.draw.rect(surf, border, self.rect, 2 if self.focused else 1, border_radius=10)
        pad = 14
        inner_w = self.rect.width - pad * 2
        caret_on = self.focused and int(self.blink * 2) % 2 == 0
        if not self.value:
            text(surf, self.placeholder, S.FS_MD, S.TEXT_MUTED,
                 (self.rect.x + pad, self.rect.y + (12 if self.multiline else self.rect.height // 2)),
                 "topleft" if self.multiline else "midleft")
            if caret_on:
                x = self.rect.x + pad
                y0 = self.rect.y + 12 if self.multiline else self.rect.centery - 10
                pygame.draw.line(surf, S.ACCENT, (x, y0), (x, y0 + 20), 2)
            return
        if self.multiline:
            lines = wrap(self.value, S.FS_MD, inner_w)
            lh = font(S.FS_MD).get_linesize() + 2
            max_lines = max(1, (self.rect.height - 20) // lh)
            lines = lines[-max_lines:]
            y = self.rect.y + 12
            for ln in lines:
                text(surf, ln, S.FS_MD, S.TEXT, (self.rect.x + pad, y))
                y += lh
            if caret_on:
                x = self.rect.x + pad + text_width(lines[-1], S.FS_MD) + 2
                pygame.draw.line(surf, S.ACCENT, (x, y - lh + 2), (x, y - 4), 2)
        else:
            shown = self.value
            while text_width(shown, S.FS_MD) > inner_w and shown:
                shown = shown[1:]
            r = text(surf, shown, S.FS_MD, S.TEXT, (self.rect.x + pad, self.rect.centery), "midleft")
            if caret_on:
                pygame.draw.line(surf, S.ACCENT, (r.right + 2, self.rect.centery - 10),
                                 (r.right + 2, self.rect.centery + 10), 2)


class Toasts:
    """Small, non-blocking alerts that slide in and fade out."""

    def __init__(self):
        self.items = []

    def push(self, message, level="info", duration=3.6):
        self.items.append({"text": message, "level": level, "t": 0.0, "dur": duration})
        self.items = self.items[-3:]

    def update(self, dt):
        for it in self.items:
            it["t"] += dt
        self.items = [it for it in self.items if it["t"] < it["dur"]]

    def draw(self, surf, x, y, width, grow_up=False):
        items = list(reversed(self.items)) if grow_up else self.items
        for it in items:
            t = it["t"]
            a = min(1.0, t * 5, (it["dur"] - t) * 3)
            color = S.LEVEL_COLORS[it["level"]]
            lines = wrap(it["text"], S.FS_SM, width - 44, bold=True)[:2]
            h = 16 + len(lines) * 20
            if grow_up:
                y -= h
            rect = pygame.Rect(x + int((1 - ease_out(min(1, t * 4))) * 30), y, width, h)
            alpha_rect(surf, rect, S.PANEL_ALT, int(240 * a), 10)
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(layer, (*color, int(255 * a)), layer.get_rect(), 1, border_radius=10)
            pygame.draw.rect(layer, (*color, int(255 * a)), (0, 8, 4, h - 16), border_radius=2)
            surf.blit(layer, rect.topleft)
            ty = rect.y + 8
            for ln in lines:
                img = render(ln, S.FS_SM, S.TEXT, True)
                img = img.copy()
                img.set_alpha(int(255 * a))
                surf.blit(img, (rect.x + 18, ty))
                ty += 20
            y = y - 8 if grow_up else y + h + 8
