"""Title, Compose (stage 1), Encapsulation (stage 2) and Gateway (stage 3)."""

from __future__ import annotations

import math
import random

import pygame

from network import encapsulation as enc
from network.topology import RECIPIENTS, SOURCE_HOST

from . import settings as S
from . import ui
from .core import Scene
from .widgets import draw_header_fields, draw_nested_stack, draw_packet_bar

WR = pygame.Rect(S.WORK_RECT)
SR = pygame.Rect(S.SIDE_RECT)


def side_panel(surf, title):
    ui.panel(surf, SR)
    ui.text(surf, title, S.FS_MD, S.TEXT, (SR.x + 20, SR.y + 18), bold=True)
    pygame.draw.line(surf, S.BORDER, (SR.x + 20, SR.y + 48), (SR.right - 20, SR.y + 48))
    return SR.y + 62


def info_card(surf, x, y, w, title, body, color=S.ACCENT, size=S.FS_SM):
    lines = ui.wrap(body, size, w - 28)
    h = 40 + len(lines) * (ui.font(size).get_linesize() + 1)
    ui.panel(surf, (x, y, w, h), S.PANEL_ALT, S.BORDER, 10)
    pygame.draw.rect(surf, color, (x, y + 10, 3, h - 20), border_radius=2)
    ui.text(surf, title, S.FS_SM, color, (x + 14, y + 10), bold=True)
    ui.paragraph(surf, body, size, S.TEXT_DIM, x + 14, y + 33, w - 28, gap=5)
    return y + h + 10


# ===========================================================================
# Title
# ===========================================================================
class TitleScene(Scene):
    chrome = False
    pausable = False

    def __init__(self, game):
        super().__init__(game)
        rng = random.Random(3)
        self.nodes = []
        while len(self.nodes) < 22:
            p = (rng.uniform(40, S.WIDTH - 40), rng.uniform(40, S.HEIGHT - 40))
            if all(math.dist(p, q) > 120 for q in self.nodes):
                self.nodes.append(p)
        self.edges = [(i, j) for i in range(len(self.nodes)) for j in range(i + 1, len(self.nodes))
                      if math.dist(self.nodes[i], self.nodes[j]) < 220]
        self.dots = [[rng.randrange(len(self.edges)), rng.random(), rng.uniform(0.15, 0.35)] for _ in range(14)]
        self.rng = rng
        self.help = False
        self.t = 0.0

    def enter(self, reset=False, **kw):
        if reset:
            self.session.reset_mission()
        cx = S.WIDTH // 2
        y = 420
        self.buttons = [
            ui.Button((cx - 130, y, 260, 50), "Play", self.play, "primary", pygame.K_RETURN, hint="Enter"),
            ui.Button((cx - 130, y + 62, 260, 46), "How to Play", self.toggle_help, "secondary", pygame.K_h, hint="H"),
            ui.Button((cx - 130, y + 120, 260, 46), "Quit", self.game.quit, "ghost", pygame.K_q, hint="Q"),
        ]
        self.help_close = ui.Button((S.WIDTH // 2 - 90, 628, 180, 44), "Got it", self.toggle_help, "primary")

    def play(self):
        self.help = False
        self.session.reset_mission()
        self.game.switch("compose")

    def toggle_help(self):
        self.help = not self.help

    def handle(self, e):
        if self.help:
            if self.help_close.handle(e):
                return True
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_h, pygame.K_RETURN):
                self.help = False
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.game.quit()
            return True
        return super().handle(e)

    def update(self, dt):
        super().update(dt)
        self.help_close.update(dt)
        self.t += dt
        for d in self.dots:
            d[1] += d[2] * dt
            if d[1] >= 1:
                d[0] = self.rng.randrange(len(self.edges))
                d[1] = 0.0

    def draw(self, surf):
        for i, j in self.edges:
            pygame.draw.aaline(surf, (24, 38, 60), self.nodes[i], self.nodes[j])
        for idx, t, _ in self.dots:
            i, j = self.edges[idx]
            a, b = self.nodes[i], self.nodes[j]
            p = (ui.lerp(a[0], b[0], t), ui.lerp(a[1], b[1], t))
            ui.circle(surf, (40, 120, 120), p, 3)
        for p in self.nodes:
            ui.circle(surf, (20, 32, 52), p, 6)
            ui.circle(surf, (40, 60, 90), p, 6, 1)
        veil = pygame.Surface((760, 560), pygame.SRCALPHA)
        pygame.draw.ellipse(veil, (*S.BG, 215), veil.get_rect())
        surf.blit(veil, (S.WIDTH // 2 - 380, 90))

        cx = S.WIDTH // 2
        self.game.draw_logo(surf, cx, 170, 2.4)
        ui.text(surf, "PACKET PANIC", S.FS_HERO, S.TEXT, (cx, 260), "center", bold=True)
        ui.text(surf, "THE NETWORK SURVIVAL GAME", S.FS_MD, S.ACCENT, (cx, 310), "center", bold=True)
        ui.text(surf, "Encapsulate a message, route it across an ISP, survive failures and congestion.",
                S.FS_MD, S.TEXT_DIM, (cx, 350), "center")
        self.draw_buttons(surf)
        ui.text(surf, "Computer Networks mini-project  ·  Python + Pygame  ·  a discrete simulation, not real traffic",
                S.FS_XS, S.TEXT_MUTED, (cx, S.HEIGHT - 26), "center")
        if self.help:
            self.draw_help(surf)

    def draw_help(self, surf):
        veil = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        veil.fill((5, 9, 18, 215))
        surf.blit(veil, (0, 0))
        r = pygame.Rect(S.WIDTH // 2 - 430, 34, 860, 656)
        ui.panel(surf, r, S.PANEL, S.BORDER_HI, 14)
        ui.text(surf, "How to play", S.FS_XL, S.TEXT, (r.x + 32, r.y + 26), bold=True)
        ui.text(surf, "You are the network administrator. Get one message safely from Alice to its recipient.",
                S.FS_SM, S.TEXT_DIM, (r.x + 32, r.y + 66))
        steps = [
            ("1  Compose", "Type a message and choose Bob, Charlie or Diana. This is application-layer data."),
            ("2  Encapsulate", "Drag the message into Transport, Network, Data Link, then Physical. Each adds a header."),
            ("3  Gateway", "Decide whether the destination is on the local subnet. Remote traffic goes to the gateway."),
            ("4  Route", "At the ISP, pick the neighbour with the lowest total cost. Survive link failures and congestion."),
            ("5  Deliver", "Watch the destination host remove the headers in reverse order and read the report."),
        ]
        y = r.y + 104
        for title, body in steps:
            ui.text(surf, title, S.FS_MD, S.ACCENT, (r.x + 32, y), bold=True)
            ui.paragraph(surf, body, S.FS_SM, S.TEXT, r.x + 190, y + 1, 630)
            y += 48
        y += 8
        ui.section_title(surf, "Controls", r.x + 32, y)
        y += 26
        controls = [
            ("Mouse", "Click buttons, drag the packet, click links to fail / restore them"),
            ("Space", "Encapsulation: drop the packet into the next layer (keyboard alternative)"),
            ("1 - 4", "Choose an answer / next-hop option"),
            ("F / S / R", "Routing stage: fail a link on the route / traffic surge / restore all links"),
            ("X", "Toggle simulation speed 1x / 2x"),
            ("Esc / P", "Pause, resume or restart"),
        ]
        for k, v in controls:
            ui.pill(surf, k, (r.x + 32, y), S.TEXT, S.PANEL_HI)
            ui.text(surf, v, S.FS_SM, S.TEXT_DIM, (r.x + 150, y + 2))
            y += 30
        self.help_close.draw(surf)


# ===========================================================================
# Stage 1 - Compose
# ===========================================================================
class ComposeScene(Scene):
    stage = 0
    title = "Stage 1 · Create message"

    def enter(self, reset=False, **kw):
        if reset:
            self.session.reset_mission()
        s = self.session
        x, y = WR.x + 28, WR.y
        self.sender = ui.TextInput((x, y + 122, 300, 46), s.sender, "Sender name", 16)
        self.message = ui.TextInput((x, y + 344, 836, 112), s.message, "Type your message...", 120, multiline=True)
        self.inputs = [self.sender, self.message]
        self.cards = {}
        for i, name in enumerate(RECIPIENTS):
            self.cards[name] = pygame.Rect(x + i * 283, y + 210, 270, 92)
        oy = y + 512
        self.btn_ttl_down = ui.Button((x + 122, oy, 36, 36), "-", lambda: self.change_ttl(-1), "secondary")
        self.btn_ttl_up = ui.Button((x + 208, oy, 36, 36), "+", lambda: self.change_ttl(1), "secondary")
        self.btn_random = ui.Button((x + 290, oy, 220, 36), "", self.toggle_random, "secondary", size=S.FS_SM)
        self.btn_seed = ui.Button((x + 522, oy, 200, 36), "", self.toggle_seed, "secondary", size=S.FS_SM)
        self.btn_send = ui.Button((WR.right - 228, WR.bottom - 68, 200, 48), "Send message", self.send,
                                  "primary", icon="arrow")
        self.buttons = [self.btn_ttl_down, self.btn_ttl_up, self.btn_random, self.btn_seed, self.btn_send]
        self.error = ""
        self.message.focused = True
        self.sync_labels()

    def is_typing(self):
        return any(i.focused for i in self.inputs)

    def change_ttl(self, d):
        self.session.ttl = max(2, min(16, self.session.ttl + d))

    def toggle_random(self):
        self.session.random_events = not self.session.random_events
        self.sync_labels()

    def toggle_seed(self):
        self.session.fixed_seed = not self.session.fixed_seed
        self.sync_labels()

    def sync_labels(self):
        s = self.session
        self.btn_random.label = f"Random events: {'On' if s.random_events else 'Off'}"
        self.btn_seed.label = f"Seed: {s.seed} (fixed)" if s.fixed_seed else "Seed: random"

    def send(self):
        s = self.session
        name = self.sender.value.strip()
        msg = self.message.value.strip()
        self.sender.error = not name
        self.message.error = not msg
        if not name or not msg:
            self.error = "Please enter a sender name and a message."
            return
        s.sender, s.message = name, msg
        s.reset_mission()
        s.create_packet()
        s.timer_running = True
        self.game.toasts.push(f"Packet #{s.packet.id} created: application data ready", "info")
        self.game.switch("encapsulate")

    def handle(self, e):
        for inp in self.inputs:
            inp.handle(e)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for name, r in self.cards.items():
                if r.collidepoint(e.pos):
                    self.session.recipient = name
                    return True
        if e.type == pygame.KEYDOWN:
            ctrl = pygame.key.get_mods() & pygame.KMOD_CTRL
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if ctrl or not self.message.focused:
                    self.send()
                    return True
            if e.key == pygame.K_TAB:
                i = next((k for k, inp in enumerate(self.inputs) if inp.focused), -1)
                for inp in self.inputs:
                    inp.focused = False
                self.inputs[(i + 1) % len(self.inputs)].focused = True
                return True
            if not self.is_typing() and e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                names = list(RECIPIENTS)
                i = names.index(self.session.recipient)
                self.session.recipient = names[(i + (1 if e.key == pygame.K_RIGHT else -1)) % len(names)]
                return True
        if self.is_typing() and e.type == pygame.KEYDOWN:
            return True   # don't let letters trigger button hotkeys
        return super().handle(e)

    def update(self, dt):
        super().update(dt)
        for inp in self.inputs:
            inp.update(dt)
        if self.error and self.sender.value.strip() and self.message.value.strip():
            self.error = ""
            self.sender.error = self.message.error = False

    def draw(self, surf):
        s = self.session
        ui.panel(surf, WR)
        x, y = WR.x + 28, WR.y
        ui.text(surf, "Compose a message", S.FS_XL, S.TEXT, (x, y + 24), bold=True)
        ui.text(surf, "Write what Alice wants to send and pick who receives it.", S.FS_MD, S.TEXT_DIM, (x, y + 62))

        ui.section_title(surf, "From", x, y + 100)
        self.sender.draw(surf)
        src = s.src_host
        ui.pill(surf, f"{src.label}  ·  {src.ip}/{src.prefix_len}", (x + 316, y + 145), S.TEXT_DIM, S.PANEL_HI,
                anchor="midleft", bold=False, size=S.FS_SM, pad=(12, 6))

        ui.section_title(surf, "To", x, y + 188)
        for name, r in self.cards.items():
            host = s.network.nodes[RECIPIENTS[name]]
            sel = name == s.recipient
            hov = r.collidepoint(ui.MOUSE)
            ui.panel(surf, r, S.ACCENT_SOFT if sel else (S.PANEL_HI if hov else S.PANEL_ALT),
                     S.ACCENT if sel else S.BORDER_HI, 12, 2 if sel else 1)
            ui.circle(surf, S.ACCENT if sel else S.PANEL_HI, (r.x + 34, r.centery), 20)
            ui.text(surf, name[0], S.FS_LG, (6, 30, 30) if sel else S.TEXT, (r.x + 34, r.centery), "center", True)
            ui.text(surf, name, S.FS_LG, S.TEXT, (r.x + 66, r.y + 14), bold=True)
            ui.text(surf, host.ip, S.FS_SM, S.ACCENT if sel else S.TEXT_DIM, (r.x + 66, r.y + 44), mono=True)
            ui.text(surf, f"{host.label} · {host.network}", S.FS_XS, S.TEXT_MUTED, (r.x + 66, r.y + 66))
            if sel:
                ui.check_mark(surf, S.ACCENT, (r.right - 22, r.y + 22), 6, 3)

        ui.section_title(surf, "Message", x, y + 322)
        self.message.draw(surf)
        n = len(self.message.value)
        col = S.AMBER if n > 100 else S.TEXT_MUTED
        ui.text(surf, f"{n}/120", S.FS_XS, col, (self.message.rect.right, self.message.rect.bottom + 6), "topright")

        oy = y + 512
        ui.section_title(surf, "Options", x, oy - 26)
        ui.text(surf, "Initial TTL", S.FS_SM, S.TEXT_DIM, (x, oy + 18), "midleft")
        ui.panel(surf, (x + 162, oy, 42, 36), S.PANEL_ALT, S.BORDER, 8)
        ui.text(surf, str(s.ttl), S.FS_MD, S.TEXT, (x + 183, oy + 18), "center", True, True)
        self.draw_buttons(surf)
        if self.error:
            ui.text(surf, self.error, S.FS_SM, S.RED, (self.btn_send.rect.x - 16, self.btn_send.rect.centery),
                    "midright", True)
        else:
            ui.text(surf, "Ctrl+Enter to send · Tab switches field · Left/Right picks recipient",
                    S.FS_XS, S.TEXT_MUTED, (x, WR.bottom - 44), "midleft")

        # side panel
        y = side_panel(surf, "Application layer")
        y = info_card(surf, SR.x + 20, y, SR.width - 40, "Layer 7 · Application data",
                      "Your message is application-layer data. PacketChat hands it to the operating "
                      "system, which wraps it in headers layer by layer before it can travel.")
        y += 4
        ui.section_title(surf, "Source host", SR.x + 20, y)
        y += 24
        w = SR.width - 40
        for k, v in (("Host", src.label), ("IP address", f"{src.ip}/{src.prefix_len}"),
                     ("MAC address", src.mac), ("Gateway", src.gateway_ip)):
            y = ui.key_value(surf, k, v, SR.x + 20, y, w)
        y += 12
        dst = s.dst_host
        ui.section_title(surf, "Destination", SR.x + 20, y)
        y += 24
        for k, v in (("Recipient", s.recipient), ("Host", dst.label), ("IP address", dst.ip),
                     ("Network", str(dst.network))):
            y = ui.key_value(surf, k, v, SR.x + 20, y, w, vcolor=S.ACCENT if k == "IP address" else S.TEXT)
        y += 14
        info_card(surf, SR.x + 20, y, w, "Tip: TTL",
                  "Each router decrements TTL by 1. Reaching Bob takes 5 routers - "
                  "set TTL to 3 to watch a packet expire.", S.AMBER, S.FS_XS + 1)


# ===========================================================================
# Stage 2 - Encapsulation (drag and drop)
# ===========================================================================
LAYER_TEXT = {
    "transport": ("Transport", "L4 · Segment", "Adds ports"),
    "network": ("Network", "L3 · Packet", "Adds IP addresses"),
    "datalink": ("Data Link", "L2 · Frame", "Adds MACs + FCS"),
    "physical": ("Physical", "L1 · Bits", "Sends bits"),
}

OSI_ROWS = [
    ("L7", "Application", "PacketChat message", "application"),
    ("L6", "Presentation", "UTF-8 text encoding", "concept"),
    ("L5", "Session", "dialogue (app / TCP)", "concept"),
    ("L4", "Transport", "ports, TCP/UDP", "transport"),
    ("L3", "Network", "IP addresses, routing", "network"),
    ("L2", "Data Link", "MAC addresses, frame", "datalink"),
    ("L1", "Physical", "bits on the medium", "physical"),
]


class EncapsulationScene(Scene):
    stage = 1
    title = "Stage 2 · Encapsulation"

    def enter(self, **kw):
        self.area = pygame.Rect(WR.x + 236, WR.y + 84, 632, 520)
        self.home = (self.area.centerx, self.area.y + 56)
        self.card_pos = list(self.home)
        self.dragging = False
        self.drag_off = (0, 0)
        self.return_anim = None      # (start_pos, t)
        self.containers = {}
        cw, gap = 146, 16
        x0 = self.area.x + (self.area.width - (4 * cw + 3 * gap)) // 2
        for i, layer in enumerate(enc.ORDER):
            self.containers[layer] = pygame.Rect(x0 + i * (cw + gap), self.area.y + 150, cw, 150)
        self.grow = {}
        self.flash = {}              # layer -> (color, t)
        self.choosing = False
        self.info = ("Drag the message into the Transport layer",
                     "Encapsulation works top-down: each layer adds its own header around the data from the layer above.")
        self.info_color = S.ACCENT
        self.bits = []
        self.bit_t = 0.0
        self.t = 0.0
        self.btn_tcp = ui.Button((0, 0, 10, 10), "TCP", lambda: self.choose("TCP"), "primary", pygame.K_t)
        self.btn_udp = ui.Button((0, 0, 10, 10), "UDP", lambda: self.choose("UDP"), "secondary", pygame.K_u)
        self.btn_continue = ui.Button((WR.right - 248, WR.bottom - 64, 224, 46), "Continue to gateway",
                                      self.next_stage, "primary", icon="arrow")
        self.btn_continue.visible = False
        self.buttons = [self.btn_continue]

    @property
    def packet(self):
        return self.session.packet

    def next_stage(self):
        self.game.switch("gateway")

    def card_rect(self):
        n = len(self.packet.headers)
        w = 200 + 64 * n + (40 if "datalink" in [h.layer for h in self.packet.headers] else 0)
        r = pygame.Rect(0, 0, w, 56)
        r.center = (int(self.card_pos[0]), int(self.card_pos[1]))
        return r

    def drop_on(self, layer):
        expected = enc.next_layer(self.packet)
        if expected is None:
            return
        if layer != expected:
            self.flash[layer] = (S.RED, 0.0)
            self.info = (f"Not yet - {LAYER_TEXT[expected][0]} comes next",
                         "Headers are added from the top of the stack down: Transport, then Network, "
                         "then Data Link, then Physical. Each layer wraps what the layer above produced.")
            self.info_color = S.RED
            self.session.add_score("Wrong layer order", -2)
            return
        if layer == "transport":
            self.choosing = True
            return
        self.apply(layer)

    def apply(self, layer, protocol=None):
        s = self.session
        p = self.packet
        if layer == "datalink":
            enc.encapsulate(p, layer, src_mac=s.src_host.mac,
                            dst_mac=s.gateway.iface_to(SOURCE_HOST).mac)
        else:
            enc.encapsulate(p, layer, protocol=protocol)
        self.grow[layer] = 0.0
        self.flash[layer] = (S.GREEN, 0.0)
        s.add_score(f"{LAYER_TEXT[layer][0]} layer applied", 5)
        if layer == "transport":
            if protocol == "TCP":
                body = (f"TCP header added (src port {p.src_port} -> dst port {p.dst_port}). TCP is reliable and "
                        "connection-oriented: sequence numbers, acknowledgements and retransmission.")
            else:
                body = (f"UDP header added (src port {p.src_port} -> dst port {p.dst_port}). UDP is connectionless: "
                        "tiny header, no handshake, no delivery guarantee - fast but unreliable.")
            self.info = (f"Transport: {protocol} segment created", body)
        elif layer == "network":
            self.info = ("Network: IPv4 header added",
                         f"Logical addresses {p.src_ip} -> {p.dst_ip} identify the end hosts. Routers use the "
                         f"destination IP to choose a path. TTL starts at {p.ttl}.")
        elif layer == "datalink":
            self.info = ("Data Link: Ethernet frame built",
                         "Source MAC = Alice's NIC, destination MAC = the default gateway GW-A (the next hop), "
                         "not Bob. MAC addressing only works on the local link.")
        else:
            self.bits = enc.bitstream(p, 320)
            self.bit_t = 0.0
            self.info = ("Physical: frame sent as a bitstream",
                         "The frame is represented as 0s and 1s on the medium. This is a simplified educational "
                         "view - no real electrical signals or Ethernet frames are produced.")
            self.btn_continue.visible = True
        self.info_color = S.LAYER_COLORS[layer]

    def choose(self, protocol):
        if self.choosing:
            self.choosing = False
            self.apply("transport", protocol)

    def handle(self, e):
        if self.choosing:
            if self.btn_tcp.handle(e) or self.btn_udp.handle(e):
                return True
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.choosing = False
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and enc.next_layer(self.packet):
            if self.card_rect().inflate(10, 10).collidepoint(e.pos):
                self.dragging = True
                self.return_anim = None
                self.drag_off = (self.card_pos[0] - e.pos[0], self.card_pos[1] - e.pos[1])
                return True
        if e.type == pygame.MOUSEMOTION and self.dragging:
            self.card_pos = [e.pos[0] + self.drag_off[0], e.pos[1] + self.drag_off[1]]
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.dragging:
            self.dragging = False
            for layer, r in self.containers.items():
                if r.collidepoint(e.pos) or r.collidepoint(self.card_pos):
                    self.drop_on(layer)
                    break
            self.return_anim = (tuple(self.card_pos), 0.0)
            return True
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_SPACE, pygame.K_RETURN):
            nxt = enc.next_layer(self.packet)
            if nxt:
                self.drop_on(nxt)
            elif self.btn_continue.visible:
                self.next_stage()
            return True
        return super().handle(e)

    def update(self, dt):
        super().update(dt)
        self.btn_tcp.update(dt)
        self.btn_udp.update(dt)
        self.t += dt
        for k in self.grow:
            self.grow[k] = min(1.0, self.grow[k] + dt * 2.5)
        for k, (c, t) in list(self.flash.items()):
            if t > 0.9:
                del self.flash[k]
            else:
                self.flash[k] = (c, t + dt)
        if self.return_anim:
            start, t = self.return_anim
            t = min(1.0, t + dt * 4)
            k = ui.ease_out(t)
            self.card_pos = [ui.lerp(start[0], self.home[0], k), ui.lerp(start[1], self.home[1], k)]
            self.return_anim = None if t >= 1 else (start, t)
        if self.bits:
            self.bit_t += dt

    def draw(self, surf):
        p = self.packet
        ui.panel(surf, WR)
        ui.text(surf, "Encapsulate the message", S.FS_XL, S.TEXT, (WR.x + 28, WR.y + 24), bold=True)
        ui.text(surf, "Drag the packet into each layer in order (or press Space). Every layer wraps it with a header.",
                S.FS_SM, S.TEXT_DIM, (WR.x + 28, WR.y + 60))

        self.draw_osi(surf, pygame.Rect(WR.x + 24, WR.y + 96, 196, 436))

        expected = enc.next_layer(p)
        # containers
        for layer, r in self.containers.items():
            color = S.LAYER_COLORS[layer]
            done = layer in [h.layer for h in p.headers] or (layer == "physical" and p.on_wire)
            is_next = layer == expected
            fill = ui.lerp_color(color, S.PANEL, 0.9) if done else S.PANEL_ALT
            border = color if (done or is_next) else S.BORDER
            if is_next and self.dragging and r.collidepoint(ui.MOUSE):
                fill = ui.lerp_color(color, S.PANEL, 0.75)
            ui.panel(surf, r, fill, border, 12, 2 if is_next else 1)
            if is_next and not done:
                pulse = (math.sin(self.t * 4) + 1) / 2
                ui.alpha_rect(surf, r.inflate(8, 8), color, int(25 + 30 * pulse), 14)
            if layer in self.flash:
                c, t = self.flash[layer]
                ui.alpha_rect(surf, r, c, int(120 * (1 - t)), 12)
            pygame.draw.rect(surf, color, (r.x + 14, r.y + 14, 28, 4), border_radius=2)
            name, sub, desc = LAYER_TEXT[layer]
            ui.text(surf, name, S.FS_MD, S.TEXT, (r.x + 14, r.y + 28), bold=True)
            ui.text(surf, sub, S.FS_XS, color, (r.x + 14, r.y + 52), bold=True)
            ui.text(surf, desc, S.FS_XS, S.TEXT_DIM, (r.x + 14, r.y + 74))
            if done:
                ui.circle(surf, S.GREEN_SOFT, (r.centerx, r.bottom - 32), 15)
                ui.check_mark(surf, S.GREEN, (r.centerx, r.bottom - 32), 6, 3)
            elif is_next:
                ui.text(surf, "DROP HERE", S.FS_XS, color, (r.centerx, r.bottom - 30), "center", True)
            else:
                ui.text(surf, "waiting", S.FS_XS, S.TEXT_MUTED, (r.centerx, r.bottom - 30), "center")

        # info card
        ir = pygame.Rect(self.area.x, self.area.y + 322, self.area.width, 96)
        ui.panel(surf, ir, S.PANEL_ALT, S.BORDER, 12)
        pygame.draw.rect(surf, self.info_color, (ir.x, ir.y + 12, 3, ir.height - 24), border_radius=2)
        ui.text(surf, self.info[0], S.FS_MD, self.info_color, (ir.x + 18, ir.y + 12), bold=True)
        ui.paragraph(surf, self.info[1], S.FS_SM, S.TEXT_DIM, ir.x + 18, ir.y + 40, ir.width - 36, max_lines=2)

        # bitstream / wire
        wire = pygame.Rect(self.area.x, ir.bottom + 14, self.area.width - 260 if self.btn_continue.visible else self.area.width, 44)
        ui.panel(surf, wire, (11, 17, 30), S.BORDER, 10)
        if self.bits:
            cw = 9
            max_chars = (wire.width - 24) // cw
            offset = int(self.bit_t * 40)          # bits stream past continuously
            n = len(self.bits)
            for i in range(min(max_chars, n)):
                seg, b = self.bits[(offset + i) % n]
                ui.text(surf, b, S.FS_SM, S.LAYER_COLORS[seg], (wire.x + 12 + i * cw, wire.centery), "midleft", mono=True)
        else:
            ui.text(surf, "Physical medium - the bitstream appears here once the frame is complete",
                    S.FS_XS, S.TEXT_MUTED, wire.center, "center")

        self.draw_buttons(surf)

        # the draggable packet (drawn last so it's on top)
        if expected is not None or self.dragging:
            r = self.card_rect()
            if self.dragging:
                ui.alpha_rect(surf, r.move(4, 8), (0, 0, 0), 90, 12)
            elif r.collidepoint(ui.MOUSE):
                ui.alpha_rect(surf, r.inflate(10, 10), S.ACCENT, 40, 14)
        draw_packet_bar(surf, p, self.card_pos, self.grow)
        if not self.dragging and expected is not None:
            ui.text(surf, "drag me", S.FS_XS, S.TEXT_MUTED, (self.card_pos[0], self.card_pos[1] + 38), "midtop")

        if self.choosing:
            self.draw_choice(surf)
        self.draw_side(surf)

    def draw_osi(self, surf, r):
        ui.panel(surf, r, S.PANEL_ALT, S.BORDER, 12)
        ui.section_title(surf, "OSI model", r.x + 14, r.y + 12)
        p = self.packet
        done_layers = {h.layer for h in p.headers} | ({"physical"} if p.on_wire else set())
        expected = enc.next_layer(p)
        y = r.y + 40
        for code, name, desc, key in OSI_ROWS:
            if key == "application":
                state = "done"
            elif key == "concept":
                state = "concept"
            elif key in done_layers:
                state = "done"
            elif key == expected:
                state = "next"
            else:
                state = "pending"
            color = S.LAYER_COLORS.get(key, S.TEXT_MUTED) if key != "application" else S.LAYER_COLORS["data"]
            if state == "next":
                ui.alpha_rect(surf, (r.x + 6, y - 5, r.width - 12, 46), S.ACCENT, 28, 8)
            cx = r.x + 22
            if state == "done":
                ui.circle(surf, S.GREEN, (cx, y + 9), 7)
                ui.check_mark(surf, S.BG, (cx, y + 9), 3, 2)
            elif state == "concept":
                ui.circle(surf, S.TEXT_MUTED, (cx, y + 9), 6, 1)
            elif state == "next":
                ui.circle(surf, S.ACCENT, (cx, y + 9), 7)
            else:
                ui.circle(surf, S.BORDER_HI, (cx, y + 9), 6, 1)
            tc = S.TEXT if state in ("done", "next") else S.TEXT_DIM
            ui.text(surf, f"{code}  {name}", S.FS_SM, tc, (r.x + 38, y), bold=state != "concept")
            ui.text(surf, desc, S.FS_XS, color if state != "concept" else S.TEXT_MUTED, (r.x + 38, y + 21))
            y += 49
        pygame.draw.line(surf, S.BORDER, (r.x + 14, y + 2), (r.right - 14, y + 2))
        ui.paragraph(surf, "L6 and L5 are shown conceptually - no separate headers here.",
                     S.FS_XS, S.TEXT_MUTED, r.x + 14, y + 10, r.width - 28)

    def draw_choice(self, surf):
        veil = pygame.Surface(WR.size, pygame.SRCALPHA)
        veil.fill((5, 9, 18, 200))
        surf.blit(veil, WR.topleft)
        r = pygame.Rect(0, 0, 600, 300)
        r.center = WR.center
        ui.panel(surf, r, S.PANEL, S.BORDER_HI, 14)
        ui.text(surf, "Choose a transport protocol", S.FS_LG, S.TEXT, (r.x + 28, r.y + 22), bold=True)
        ui.text(surf, f"Both use the same ports: {self.packet.src_port} -> {self.packet.dst_port} (PacketChat)",
                S.FS_SM, S.TEXT_DIM, (r.x + 28, r.y + 54))
        opts = [
            ("TCP", self.btn_tcp, "Reliable, connection-oriented", "Handshake, sequence numbers, ACKs, retransmits lost data."),
            ("UDP", self.btn_udp, "Connectionless, best effort", "Small header, no handshake. Lost data is simply lost."),
        ]
        for i, (name, btn, head, body) in enumerate(opts):
            cr = pygame.Rect(r.x + 28 + i * 280, r.y + 90, 264, 180)
            ui.panel(surf, cr, S.PANEL_ALT, S.BORDER, 12)
            ui.text(surf, name, S.FS_XL, S.ACCENT if i == 0 else S.CYAN, (cr.x + 16, cr.y + 12), bold=True)
            ui.text(surf, head, S.FS_SM, S.TEXT, (cr.x + 16, cr.y + 52), bold=True)
            ui.paragraph(surf, body, S.FS_XS + 1, S.TEXT_DIM, cr.x + 16, cr.y + 76, cr.width - 32)
            btn.rect = pygame.Rect(cr.x + 16, cr.bottom - 54, cr.width - 32, 40)
            btn.label = f"Use {name}"
            btn.hint = name[0]
            btn.draw(surf)

    def draw_side(self, surf):
        p = self.packet
        y = side_panel(surf, "Packet inspector")
        draw_nested_stack(surf, p, (SR.x + 20, y, SR.width - 40, 130))
        y += 138
        size = sum(len(b) for _, b in enc.frame_bytes(p))
        data = len(p.payload.encode())
        ui.text(surf, f"{size} bytes total  ·  {data} B data + {size - data} B headers/trailer",
                S.FS_XS, S.TEXT_DIM, (SR.x + 20, y))
        y += 26
        draw_header_fields(surf, p, SR.x + 20, y, SR.width - 40)


# ===========================================================================
# Stage 3 - Addressing and the local gateway
# ===========================================================================
class GatewayScene(Scene):
    stage = 2
    title = "Stage 3 · Default gateway"

    def enter(self, **kw):
        self.answer = None          # None | "wrong" | "right"
        self.feedback = ""
        self.attempts = 0
        self.arp_t = 0.0
        self.sending = None         # animation progress 0..1
        q = pygame.Rect(WR.x + 24, WR.y + 298, WR.width - 48, 150)
        self.q_rect = q
        self.btn_local = ui.Button((q.x + 20, q.bottom - 52, 300, 40), "Same network - send directly",
                                   lambda: self.answer_q(False), "secondary", pygame.K_1, hint="1", size=S.FS_SM)
        self.btn_remote = ui.Button((q.x + 334, q.bottom - 52, 320, 40), "Different network - use gateway",
                                    lambda: self.answer_q(True), "secondary", pygame.K_2, hint="2", size=S.FS_SM)
        self.btn_send = ui.Button((WR.right - 248, WR.bottom - 64, 224, 46), "Send to GW-A", self.send,
                                  "primary", pygame.K_RETURN, icon="arrow")
        self.btn_send.visible = False
        self.buttons = [self.btn_local, self.btn_remote, self.btn_send]

    def answer_q(self, remote):
        if self.answer == "right":
            return
        s = self.session
        if remote:
            self.answer = "right"
            s.add_score("Correct local/remote decision", 25 if self.attempts == 0 else 10)
            self.feedback = (f"Correct. {s.dst_host.ip} is on {s.dst_host.network}, not {s.src_host.network}. "
                             "Alice must hand the frame to her default gateway.")
            self.btn_local.enabled = self.btn_remote.enabled = False
            self.btn_remote.selected = True
            self.btn_send.visible = True
        else:
            self.answer = "wrong"
            self.attempts += 1
            s.add_score("Wrong local/remote decision", -5)
            self.feedback = ("Not quite. AND each address with the mask 255.255.255.0: the network parts differ "
                             "(192.168.1.0 vs the destination's), so the host is NOT on the local link.")

    def send(self):
        if self.answer == "right" and self.sending is None:
            self.sending = 0.0

    def update(self, dt):
        super().update(dt)
        if self.answer == "right":
            self.arp_t += dt
        if self.sending is not None:
            self.sending += dt * 1.2
            if self.sending >= 1.0 and self.game.pending is None:
                self.session.start_simulation()
                self.game.switch("routing")

    def draw(self, surf):
        s = self.session
        src, gw, dst = s.src_host, s.gateway, s.dst_host
        ui.panel(surf, WR)
        ui.text(surf, "Is the destination local?", S.FS_XL, S.TEXT, (WR.x + 28, WR.y + 24), bold=True)
        ui.text(surf, "A host delivers directly only inside its own subnet. Everything else goes to the default gateway.",
                S.FS_SM, S.TEXT_DIM, (WR.x + 28, WR.y + 60))

        # --- diagram -------------------------------------------------------
        d = pygame.Rect(WR.x + 24, WR.y + 96, WR.width - 48, 190)
        ui.panel(surf, d, (11, 17, 30), S.BORDER, 12)
        lan_a = pygame.Rect(d.x + 18, d.y + 30, 300, 140)
        lan_b = pygame.Rect(d.right - 238, d.y + 30, 220, 140)
        for r, name in ((lan_a, f"LAN A  {src.network}"), (lan_b, f"LAN B  {dst.network}")):
            ui.alpha_rect(surf, r, S.ACCENT, 14, 12)
            ui.dashed_line(surf, S.ACCENT_DIM, r.topleft, r.topright, 1)
            ui.dashed_line(surf, S.ACCENT_DIM, r.bottomleft, r.bottomright, 1)
            ui.dashed_line(surf, S.ACCENT_DIM, r.topleft, r.bottomleft, 1)
            ui.dashed_line(surf, S.ACCENT_DIM, r.topright, r.bottomright, 1)
            ui.text(surf, name, S.FS_XS, S.ACCENT, (r.x + 10, r.y - 20), bold=True)
        pa = (lan_a.x + 60, lan_a.centery)
        pg = (lan_a.right - 60, lan_a.centery)
        cloud = (d.centerx + 30, d.centery + 10)
        pb = (lan_b.centerx, lan_b.centery)
        pygame.draw.line(surf, S.BORDER_HI, pa, pg, 2)
        ui.dashed_line(surf, S.BORDER_HI, pg, cloud, 2)
        ui.dashed_line(surf, S.BORDER_HI, cloud, pb, 2)
        for dx, dy, rr in ((-34, 6, 26), (0, -8, 32), (34, 4, 26), (8, 16, 26)):
            ui.circle(surf, S.PANEL_HI, (cloud[0] + dx, cloud[1] + dy), rr)
        ui.text(surf, "ISP / Internet", S.FS_SM, S.TEXT_DIM, cloud, "center", True)
        self.node(surf, pa, "host", src.label, src.ip)
        self.node(surf, pg, "router", gw.label, s.src_host.gateway_ip)
        self.node(surf, pb, "host", dst.label, dst.ip)
        if self.sending is not None:
            k = ui.ease_out(min(1.0, self.sending))
            pos = (ui.lerp(pa[0], pg[0], k), ui.lerp(pa[1], pg[1], k))
            ui.glow(surf, pos, S.ACCENT, 22)
            ui.circle(surf, S.ACCENT, pos, 7)

        # --- question ------------------------------------------------------
        q = self.q_rect
        ui.panel(surf, q, S.PANEL_ALT, S.BORDER, 12)
        ui.text(surf, f"Is {dst.ip} on Alice's local network?", S.FS_LG, S.TEXT, (q.x + 20, q.y + 14), bold=True)
        mask = src.netmask
        ui.text(surf, f"Alice  {src.ip}  AND  {mask}  =  {src.network.network_address}",
                S.FS_SM, S.TEXT_DIM, (q.x + 20, q.y + 48), mono=True)
        dst_net = str(dst.network.network_address) if self.answer == "right" else "?"
        ui.text(surf, f"Dest   {dst.ip}  AND  {mask}  =  {dst_net}",
                S.FS_SM, S.ACCENT if self.answer == "right" else S.TEXT_DIM, (q.x + 20, q.y + 72), mono=True)
        self.draw_buttons(surf)

        y = q.bottom + 14
        if self.feedback:
            col = S.GREEN if self.answer == "right" else S.RED
            fr = pygame.Rect(q.x, y, q.width, 50)
            ui.panel(surf, fr, S.GREEN_SOFT if self.answer == "right" else S.RED_SOFT, col, 10)
            ui.paragraph(surf, self.feedback, S.FS_SM, S.TEXT, fr.x + 16, fr.y + 9, fr.width - 32, max_lines=2)
            y = fr.bottom + 14

        if self.answer == "right":
            ar = pygame.Rect(q.x, y, q.width - 250, WR.bottom - 20 - y)
            ui.panel(surf, ar, (11, 17, 30), S.BORDER, 10)
            ui.text(surf, "ARP - finding the gateway's MAC address", S.FS_SM, S.VIOLET, (ar.x + 16, ar.y + 12), bold=True)
            lines = [
                (0.3, f"Alice  >  broadcast:  Who has {src.gateway_ip}? Tell {src.ip}"),
                (1.0, f"GW-A   >  Alice:      {src.gateway_ip} is at {gw.iface_to(SOURCE_HOST).mac}"),
            ]
            ly = ar.y + 38
            for t0, ln in lines:
                if self.arp_t > t0:
                    ui.text(surf, ln, S.FS_XS + 1, S.TEXT, (ar.x + 16, ly), mono=True)
                ly += 22
            if self.arp_t > 1.6 and ly + 20 < ar.bottom:
                ui.text(surf, "Frame dst MAC = gateway; IP dst stays the remote host.",
                        S.FS_XS, S.TEXT_DIM, (ar.x + 16, ly + 2))
        self.draw_side(surf)

    def node(self, surf, pos, kind, label, ip):
        if kind == "router":
            ui.circle(surf, S.PANEL_HI, pos, 20)
            ui.circle(surf, S.CYAN, pos, 20, 2)
            ui.draw_icon(surf, "arrow", pos, S.CYAN)
        else:
            r = pygame.Rect(0, 0, 38, 30)
            r.center = pos
            pygame.draw.rect(surf, S.PANEL_HI, r, border_radius=6)
            pygame.draw.rect(surf, S.ACCENT, r, 2, border_radius=6)
        ui.text(surf, label, S.FS_XS, S.TEXT, (pos[0], pos[1] + 26), "midtop", True)
        ui.text(surf, ip, S.FS_XS, S.TEXT_DIM, (pos[0], pos[1] + 44), "midtop", mono=True)

    def draw_side(self, surf):
        s = self.session
        y = side_panel(surf, "Addressing")
        w = SR.width - 40
        y = info_card(surf, SR.x + 20, y, w, "IP address (Layer 3)",
                      "Logical, end-to-end address. Source and destination IP stay the same along the whole path.",
                      S.CYAN, S.FS_XS + 1)
        y = info_card(surf, SR.x + 20, y, w, "MAC address (Layer 2)",
                      "Hardware address valid on one link only. It is rewritten at every router hop.",
                      S.VIOLET, S.FS_XS + 1)
        y = info_card(surf, SR.x + 20, y, w, "Default gateway",
                      "The router a host uses for any destination outside its own subnet.",
                      S.ACCENT, S.FS_XS + 1)
        ui.section_title(surf, "Address table", SR.x + 20, y + 2)
        y += 26
        gw = s.gateway
        for k, v in (("Alice IP", s.src_host.ip), ("Alice MAC", s.src_host.mac),
                     ("Gateway IP", s.src_host.gateway_ip), ("Gateway MAC", gw.iface_to(SOURCE_HOST).mac),
                     ("Dest IP", s.dst_host.ip)):
            y = ui.key_value(surf, k, v, SR.x + 20, y, w)
        ui.paragraph(surf, "The ISP doesn't assign the destination IP - Alice's app wrote it; the ISP only routes it.",
                     S.FS_XS, S.TEXT_MUTED, SR.x + 20, y + 8, w)
