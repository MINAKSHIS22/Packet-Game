"""Packet visualisations shared by several scenes."""

from __future__ import annotations

import pygame

from network import encapsulation as enc

from . import settings as S
from . import ui

HEADER_LABELS = {"datalink": "ETH", "network": "IP", "transport": "L4"}
SEG_W = {"datalink": 64, "network": 64, "transport": 64, "fcs": 40}
DATA_W = 200


def packet_layers(packet):
    return [h.layer for h in packet.headers]


def draw_packet_bar(surf, packet, center, grow=None, height=56, data_w=DATA_W,
                    hide_data=False, alpha_layers=None):
    """[ETH][IP][TCP][   DATA   ][FCS] - outermost header on the left."""
    grow = grow or {}
    layers = packet_layers(packet)
    order = [l for l in ("datalink", "network", "transport") if l in layers]
    segs = []
    for l in order:
        segs.append((l, SEG_W[l] * ui.ease_out(grow.get(l, 1.0))))
    segs.append(("data", data_w))
    if "datalink" in layers:
        segs.append(("fcs", SEG_W["fcs"] * ui.ease_out(grow.get("datalink", 1.0))))
    total = sum(w for _, w in segs)
    x = center[0] - total / 2
    y = center[1] - height / 2
    rect = pygame.Rect(int(x), int(y), int(total), height)
    pygame.draw.rect(surf, S.PANEL_ALT, rect, border_radius=10)
    for i, (name, w) in enumerate(segs):
        if w < 2:
            continue
        r = pygame.Rect(int(x), int(y), int(w) + 1, height)
        color = S.LAYER_COLORS[name]
        if name == "data":
            pygame.draw.rect(surf, (30, 41, 59), r, border_radius=10 if len(segs) == 1 else 0)
            label = "DATA"
            msg = "*" * 8 if hide_data else ui.ellipsize('"' + packet.payload + '"', S.FS_SM, w - 20)
            ui.text(surf, label, S.FS_XS, S.TEXT_MUTED, (r.centerx, r.y + 9), "midtop", True)
            ui.text(surf, msg, S.FS_SM, S.TEXT, (r.centerx, r.bottom - 10), "midbottom")
        else:
            dark = ui.lerp_color(color, S.BG, 0.72)
            radius_l = 10 if i == 0 else 0
            radius_r = 10 if i == len(segs) - 1 else 0
            pygame.draw.rect(surf, dark, r, border_top_left_radius=radius_l,
                             border_bottom_left_radius=radius_l,
                             border_top_right_radius=radius_r,
                             border_bottom_right_radius=radius_r)
            if i:
                pygame.draw.rect(surf, color, (r.x, r.y + 6, 2, height - 12))
            if w > 30:
                lab = "FCS" if name == "fcs" else (packet.protocol if name == "transport" else HEADER_LABELS[name])
                ui.text(surf, lab, S.FS_XS, color, r.center, "center", True)
        x += w
    pygame.draw.rect(surf, S.BORDER_HI, rect, 1, border_radius=10)
    return rect


def draw_nested_stack(surf, packet, rect, hide_data=False):
    """Concentric boxes: Frame > Packet > Segment > Data."""
    rect = pygame.Rect(rect)
    layers = packet_layers(packet)
    order = [l for l in ("datalink", "network", "transport") if l in layers]
    names = {"datalink": "Ethernet frame (L2)", "network": "IPv4 packet (L3)",
             "transport": f"{packet.protocol} {'segment' if packet.protocol == 'TCP' else 'datagram'} (L4)"}
    r = rect.copy()
    for l in order:
        color = S.LAYER_COLORS[l]
        pygame.draw.rect(surf, ui.lerp_color(color, S.PANEL, 0.88), r, border_radius=10)
        pygame.draw.rect(surf, ui.lerp_color(color, S.PANEL, 0.35), r, 1, border_radius=10)
        ui.text(surf, names[l], S.FS_XS, color, (r.x + 10, r.y + 5), bold=True)
        r = r.inflate(-20, -32).move(0, 8)
    if r.height > 10:
        pygame.draw.rect(surf, (30, 41, 59), r, border_radius=8)
        msg = "hidden until delivered" if hide_data else packet.payload
        ui.text(surf, "Application data", S.FS_XS, S.TEXT_MUTED, (r.x + 10, r.y + 5), bold=True)
        ui.text(surf, ui.ellipsize(msg, S.FS_SM, r.width - 20), S.FS_SM, S.TEXT, (r.x + 10, r.y + 22))
    if packet.on_wire:
        ui.pill(surf, "ON THE WIRE", (rect.right - 8, rect.y + 5), S.AMBER, S.AMBER_SOFT, anchor="topright")


def draw_header_fields(surf, packet, x, y, w, compact=False):
    """Field list for every header, outermost first."""
    for h in reversed(packet.headers):
        color = S.LAYER_COLORS[h.layer]
        ui.status_dot(surf, color, (x + 4, y + 9))
        ui.text(surf, f"{h.name} header", S.FS_SM, color, (x + 14, y), bold=True)
        y += 22
        fields = h.fields[:3] if compact else h.fields
        for k, v in fields:
            y = ui.key_value(surf, k, enc.field_value(packet, v), x + 14, y, w - 14, S.FS_XS + 1, key_w=86)
        y += 6
    return y
