"""Routing & forwarding (stages 4-7), Decapsulation (stage 8) and the report."""

from __future__ import annotations

import math

import pygame

from network import encapsulation as enc
from network.models import PacketStatus
from network.routing import lookup

from . import settings as S
from . import ui
from .core import Scene
from .scenes_setup import SR, WR, info_card, side_panel
from .widgets import draw_nested_stack, draw_packet_bar


def point_segment_distance(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ===========================================================================
# Stages 4-7 - ISP routing, forwarding, failures and congestion
# ===========================================================================
class RoutingScene(Scene):
    stage = 3
    title = "Stage 4 · Routing & forwarding"

    def enter(self, **kw):
        self.canvas = pygame.Rect(WR.x + 12, WR.y + 58, WR.width - 24, WR.height - 58 - 66)
        self.speed = 1
        self.selected = None
        self.event_index = 0
        self.log = []
        self.finish_t = 0.0
        self.t = 0.0
        self.decision_key = None
        self.option_rects = []
        self.last_result = None
        y = WR.bottom - 54
        x = WR.x + 12
        self.btn_fail = ui.Button((x, y, 176, 40), "Fail route link", self.fail_link, "danger",
                                  pygame.K_f, icon="bolt", size=S.FS_SM, hint="F")
        self.btn_surge = ui.Button((x + 186, y, 156, 40), "Traffic surge", self.surge, "warn",
                                   pygame.K_s, icon="wave", size=S.FS_SM, hint="S")
        self.btn_restore = ui.Button((x + 352, y, 156, 40), "Restore links", self.restore, "secondary",
                                     pygame.K_r, icon="link", size=S.FS_SM, hint="R")
        self.btn_speed = ui.Button((x + 518, y, 110, 40), "Speed 1x", self.toggle_speed, "secondary",
                                   pygame.K_x, size=S.FS_SM, hint="X")
        self.btn_random = ui.Button((x + 638, y, 180, 40), "", self.toggle_random, "ghost",
                                    pygame.K_e, size=S.FS_SM, hint="E")
        self.buttons = [self.btn_fail, self.btn_surge, self.btn_restore, self.btn_speed, self.btn_random]
        self.sync_labels()
        sim = self.sim
        if sim.state == "ready":
            sim.start()
        self.game.toasts.push(f"Packet #{self.session.packet.id} leaving {self.session.src_host.label}", "info")

    @property
    def sim(self):
        return self.session.sim

    def toast_area(self):
        # bottom-left of the map: the emptiest region, so alerts never hide the route
        return (self.canvas.x + 12, self.canvas.bottom - 34, 330, True)

    @property
    def net(self):
        return self.session.network

    # -- controls ---------------------------------------------------------
    def sync_labels(self):
        self.btn_speed.label = f"Speed {self.speed}x"
        self.btn_random.label = f"Random events: {'On' if self.sim.random_events else 'Off'}"

    def fail_link(self):
        if self.sim.state == "finished":
            return
        ok, msg = self.sim.fail_next_route_link("manual")
        if not ok:
            self.game.toasts.push(msg, "info")

    def surge(self):
        if self.sim.state == "finished":
            return
        target = self.selected
        if target is None:
            path = self.sim.projected_path()
            target = next((n for n in path if self.net.nodes[n].is_router), None)
            self.game.toasts.push("Tip: click a router first to choose where the surge hits", "info", 3)
        if target:
            self.sim.surge(target)

    def restore(self):
        if not self.sim.restore_all():
            self.game.toasts.push("All links are already up", "info", 2)

    def toggle_speed(self):
        self.speed = 2 if self.speed == 1 else 1
        self.sync_labels()

    def toggle_random(self):
        self.sim.random_events = not self.sim.random_events
        self.sync_labels()

    # -- geometry ---------------------------------------------------------
    def pos(self, node_id):
        nx, ny = self.net.nodes[node_id].pos
        c = self.canvas
        return (c.x + 50 + nx * (c.width - 100), c.y + 40 + ny * (c.height - 100))

    def link_at(self, p):
        best, best_d = None, 9.0
        for link in self.net.links.values():
            d = point_segment_distance(p, self.pos(link.a), self.pos(link.b))
            if d < best_d:
                best, best_d = link, d
        return best

    def node_at(self, p):
        for nid in self.net.nodes:
            if math.dist(p, self.pos(nid)) < 26:
                return nid
        return None

    # -- events -----------------------------------------------------------
    def handle(self, e):
        sim = self.sim
        if sim.decision is not None:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for rect, node in self.option_rects:
                    if rect.collidepoint(e.pos):
                        self.choose(node)
                        return True
            if e.type == pygame.KEYDOWN and pygame.K_1 <= e.key <= pygame.K_9:
                i = e.key - pygame.K_1
                options = sim.decision["options"]
                if i < len(options):
                    self.choose(options[i]["node"])
                    return True
        if super().handle(e):
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.canvas.collidepoint(e.pos):
            node = self.node_at(e.pos)
            if node is not None:
                self.selected = node if self.net.nodes[node].is_router and self.selected != node else None
                return True
            link = self.link_at(e.pos)
            if link is not None and sim.state != "finished":
                ok, msg = sim.toggle_link(link.id)
                if not ok:
                    self.game.toasts.push(msg, "info")
                return True
            self.selected = None
        return False

    def choose(self, node):
        ok, msg = self.sim.choose_next_hop(node)
        self.last_result = (ok, msg)
        if ok:
            self.game.toasts.push("Correct next hop - forwarding resumes", "ok", 2.5)

    def update(self, dt):
        super().update(dt)
        self.t += dt
        sim = self.sim
        for _ in range(self.speed):
            sim.update(dt)
        # consume new simulation events
        while self.event_index < len(sim.events):
            ev = sim.events[self.event_index]
            self.event_index += 1
            if ev.kind == "alert":
                self.game.toasts.push(ev.text, ev.level)
            elif ev.kind == "log":
                self.log.append((ev.time, ev.text, ev.level))
        self.log = self.log[-60:]
        # rebuild option buttons when a new decision appears
        key = None
        if sim.decision:
            key = (sim.decision["router"], sim.decision["kind"],
                   tuple(o["active"] for o in sim.decision["options"]))
        if key != self.decision_key:
            self.decision_key = key
            self.last_result = None
        if sim.state == "finished":
            self.finish_t += dt
            if self.finish_t > 1.8 and self.game.pending is None:
                if sim.packet.status == PacketStatus.DELIVERED:
                    self.game.switch("decap")
                else:
                    self.game.switch("report")

    # -- drawing ----------------------------------------------------------
    def draw(self, surf):
        sim = self.sim
        p = sim.packet
        ui.panel(surf, WR)
        ui.text(surf, "ISP routing", S.FS_LG, S.TEXT, (WR.x + 20, WR.y + 18), bold=True)
        ui.pill(surf, f"to {p.dst_ip}  ({p.recipient_name})", (WR.x + 150, WR.y + 31), S.ACCENT, S.ACCENT_SOFT,
                anchor="midleft", size=S.FS_SM)
        stats = (f"sim time {sim.time * 10:5.1f} ms   ·   background {sim.bg_sent} sent, "
                 f"{sim.bg_dropped} lost ({sim.loss_rate * 100:.0f}%)")
        ui.text(surf, stats, S.FS_XS, S.TEXT_DIM, (WR.right - 20, WR.y + 31), "midright", mono=True)

        c = self.canvas
        ui.panel(surf, c, (11, 17, 30), S.BORDER, 12)
        # ISP region
        r = pygame.Rect(0, 0, 0, 0)
        xs = [self.pos(n)[0] for n in ("ISPE", "ISP1", "ISP4")]
        r.x, r.width = int(xs[0] - 42), int(xs[2] - xs[0] + 84)
        r.y, r.height = c.y + 12, c.height - 24
        ui.alpha_rect(surf, r, S.CYAN, 10, 18)
        ui.text(surf, "ISP BACKBONE  ·  AS 64500", S.FS_XS, (60, 110, 140), (r.centerx, r.y + 10), "midtop", True)
        ui.text(surf, "CUSTOMER LAN", S.FS_XS, (60, 90, 110), (self.pos("ALICE")[0] + 30, c.y + 22), "midtop", True)

        self.draw_links(surf)
        self.draw_nodes(surf)
        self.draw_packets(surf)
        self.draw_legend(surf)
        self.draw_buttons(surf)
        if sim.decision is not None:
            self.draw_decision_side(surf)
        else:
            self.draw_inspector_side(surf)

    def draw_legend(self, surf):
        c = self.canvas
        x, y = c.x + 14, c.bottom - 26
        for color, label, dashed in ((S.ACCENT, "travelled", False), (S.CYAN, "planned route", False),
                                     (S.RED, "failed link", True), (S.AMBER, "congested", False)):
            if dashed:
                ui.dashed_line(surf, color, (x, y + 8), (x + 22, y + 8), 2, 5, 4)
            else:
                pygame.draw.line(surf, color, (x, y + 8), (x + 22, y + 8), 3)
            x = ui.text(surf, label, S.FS_XS, S.TEXT_DIM, (x + 28, y)).right + 18
        ui.text(surf, "click a link to fail/restore it  ·  click a router to inspect it",
                S.FS_XS, S.TEXT_MUTED, (c.right - 14, y), "topright")

    def route_links(self):
        sim, p = self.sim, self.sim.packet
        travelled = set()
        for a, b in zip(p.route, p.route[1:]):
            l = self.net.link_between(a, b)
            if l:
                travelled.add(l.id)
        planned = set()
        if not p.is_final:
            t = sim.main_transit()
            if t:
                planned.add(t.link.id)
            path = sim.projected_path()
            for a, b in zip(path, path[1:]):
                l = self.net.link_between(a, b)
                if l:
                    planned.add(l.id)
        return travelled, planned

    def draw_links(self, surf):
        travelled, planned = self.route_links()
        hover = self.link_at(ui.MOUSE) if self.canvas.collidepoint(ui.MOUSE) and not self.node_at(ui.MOUSE) else None
        for link in self.net.links.values():
            a, b = self.pos(link.a), self.pos(link.b)
            if not link.active:
                ui.dashed_line(surf, S.RED, a, b, 3, 9, 6)
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                ui.circle(surf, S.RED_SOFT, mid, 11)
                ui.circle(surf, S.RED, mid, 11, 2)
                ui.cross_mark(surf, S.RED, mid, 4, 2)
                continue
            if link.id in planned:
                pygame.draw.line(surf, ui.lerp_color(S.CYAN, S.BG, 0.6), a, b, 9)
                pygame.draw.line(surf, S.CYAN, a, b, 3)
            elif link.id in travelled:
                pygame.draw.line(surf, S.ACCENT, a, b, 4)
            else:
                pygame.draw.line(surf, S.BORDER_HI if link is not hover else S.TEXT_DIM, a, b, 2)
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            hi = link.id in planned or link is hover
            ui.circle(surf, S.PANEL_HI if hi else S.PANEL, mid, 10)
            ui.circle(surf, S.CYAN if link.id in planned else S.BORDER_HI, mid, 10, 1)
            ui.text(surf, str(link.cost), S.FS_XS, S.TEXT if hi else S.TEXT_DIM, mid, "center", True)

    def draw_nodes(self, surf):
        sim = self.sim
        dec_router = sim.decision["router"] if sim.decision else None
        hover = self.node_at(ui.MOUSE) if self.canvas.collidepoint(ui.MOUSE) else None
        for node in self.net.nodes.values():
            x, y = self.pos(node.id)
            if node.is_host:
                is_dst = node.id == sim.packet.dst_host
                is_src = node.id == sim.packet.src_host
                col = S.ACCENT if (is_dst or is_src) else S.BORDER_HI
                r = pygame.Rect(0, 0, 46, 34)
                r.center = (x, y)
                pygame.draw.rect(surf, S.PANEL_HI, r, border_radius=7)
                pygame.draw.rect(surf, col, r, 2, border_radius=7)
                pygame.draw.rect(surf, ui.lerp_color(col, S.PANEL_HI, 0.6), r.inflate(-14, -14), border_radius=3)
                ui.text(surf, node.label, S.FS_XS, S.TEXT if (is_dst or is_src) else S.TEXT_DIM, (x, y + 22), "midtop", True)
                ui.text(surf, node.ip, S.FS_XS - 1, S.TEXT_MUTED, (x, y + 38), "midtop", mono=True)
                continue
            occ = node.occupancy
            ring = S.GREEN if occ < 0.5 else (S.AMBER if not node.is_full else S.RED)
            if node.id == dec_router:
                pulse = (math.sin(self.t * 5) + 1) / 2
                ui.glow(surf, (x, y), S.ACCENT, 44, int(60 + 60 * pulse))
            if node.is_full or occ >= 0.75:
                ui.glow(surf, (x, y), S.AMBER if not node.is_full else S.RED, 40, 70)
            ui.circle(surf, S.PANEL_HI if node.id != hover else (40, 56, 86), (x, y), 21)
            ui.circle(surf, ring, (x, y), 21, 2)
            if node.id == self.selected:
                ui.circle(surf, S.TEXT, (x, y), 27, 1)
            # router glyph: four arrows
            for ang in (0, 90, 180, 270):
                rad = math.radians(ang)
                dx, dy = math.cos(rad), math.sin(rad)
                pygame.draw.line(surf, S.TEXT_DIM, (x + dx * 4, y + dy * 4), (x + dx * 11, y + dy * 11), 2)
            ui.text(surf, node.label, S.FS_XS, S.TEXT, (x, y + 25), "midtop", True)
            # queue bar
            qx = x - node.queue_capacity * 3
            for i in range(node.queue_capacity):
                filled = i < len(node.queue)
                col = (S.GREEN if occ < 0.5 else S.AMBER if not node.is_full else S.RED) if filled else S.PANEL_HI
                pygame.draw.rect(surf, col, (qx + i * 6, y + 43, 4, 6), border_radius=1)

    def draw_packets(self, surf):
        sim = self.sim
        p = sim.packet
        main_pos = None
        for t in sim.transits:
            a, b = self.pos(t.frm), self.pos(t.to)
            k = t.progress
            pos = (ui.lerp(a[0], b[0], k), ui.lerp(a[1], b[1], k))
            if t.item is p:
                main_pos = pos
            else:
                ui.circle(surf, (110, 125, 150), pos, 3)
        if main_pos is None and not (p.status == PacketStatus.DROPPED):
            x, y = self.pos(p.current_node)
            ang = self.t * 3
            main_pos = (x + math.cos(ang) * 30, y + math.sin(ang) * 30) if self.net.nodes[p.current_node].is_router else (x, y - 28)
        if main_pos is not None:
            ui.glow(surf, main_pos, S.ACCENT, 26, 120)
            ui.circle(surf, S.ACCENT, main_pos, 8)
            ui.circle(surf, S.TEXT, main_pos, 3)
            ui.pill(surf, f"TTL {p.ttl}", (main_pos[0], main_pos[1] - 14), S.BG, S.ACCENT, anchor="midbottom", size=S.FS_XS - 1)
        elif p.drop_node:
            x, y = self.pos(p.drop_node)
            ui.circle(surf, S.RED, (x, y - 34), 9)
            ui.cross_mark(surf, S.BG, (x, y - 34), 4, 2)

    # -- side panel -------------------------------------------------------
    def draw_inspector_side(self, surf):
        sim, p = self.sim, self.sim.packet
        y = side_panel(surf, "Packet inspector")
        x, w = SR.x + 20, SR.width - 40
        status_col = {PacketStatus.DELIVERED: S.GREEN, PacketStatus.DROPPED: S.RED,
                      PacketStatus.QUEUED: S.AMBER}.get(p.status, S.CYAN)
        t = sim.main_transit()
        where = (f"{self.net.nodes[t.frm].label} -> {self.net.nodes[t.to].label}" if t
                 else f"at {self.net.nodes[p.current_node].label}")
        ui.pill(surf, p.status.replace("_", " "), (x, y), status_col, ui.lerp_color(status_col, S.PANEL, 0.82))
        ui.text(surf, where, S.FS_SM, S.TEXT, (x + w, y + 2), "topright", True)
        y += 32
        ui.text(surf, "TTL", S.FS_SM, S.TEXT_DIM, (x, y))
        ttl_col = S.GREEN if p.ttl > 3 else (S.AMBER if p.ttl > 1 else S.RED)
        ui.meter(surf, (x + 108, y + 6, w - 160, 8), p.ttl / max(1, p.initial_ttl), ttl_col)
        ui.text(surf, f"{p.ttl}/{p.initial_ttl}", S.FS_SM, ttl_col, (x + w, y), "topright", True, True)
        y += 24
        y = ui.key_value(surf, "Hops (links)", str(p.hops), x, y, w)
        y = ui.key_value(surf, "Src IP", p.src_ip, x, y, w, vcolor=S.CYAN)
        y = ui.key_value(surf, "Dst IP", p.dst_ip, x, y, w, vcolor=S.CYAN)
        y = ui.key_value(surf, "Src MAC", p.l2["src_mac"] or "-", x, y, w, vcolor=S.VIOLET)
        y = ui.key_value(surf, "Dst MAC", p.l2["dst_mac"] or "-", x, y, w, vcolor=S.VIOLET)
        lh = sim.last_hop
        hop_txt = f"{lh['router']}: {lh['in']} -> {lh['out']}, next {lh['next']}" if lh else "-"
        y = ui.key_value(surf, "Last forward", hop_txt, x, y, w, mono=False, key_w=96)

        # router status
        y += 8
        pygame.draw.line(surf, S.BORDER, (x, y), (x + w, y))
        y += 10
        rid = self.selected or (self.node_at(ui.MOUSE) if self.canvas.collidepoint(ui.MOUSE) else None)
        if rid is None or not self.net.nodes[rid].is_router:
            rid = p.current_node if self.net.nodes[p.current_node].is_router else (t.to if t else "ISPE")
            if not self.net.nodes[rid].is_router:
                rid = "ISPE"
        router = self.net.nodes[rid]
        ui.section_title(surf, f"Router status · {router.label}", x, y)
        y += 24
        occ_col = S.GREEN if router.occupancy < 0.5 else (S.AMBER if not router.is_full else S.RED)
        ui.text(surf, "Queue", S.FS_SM, S.TEXT_DIM, (x, y))
        ui.meter(surf, (x + 108, y + 6, w - 160, 8), router.occupancy, occ_col)
        ui.text(surf, f"{len(router.queue)}/{router.queue_capacity}", S.FS_SM, occ_col, (x + w, y), "topright", True, True)
        y += 22
        ui.text(surf, f"service {router.service_rate:.0f} pkt/s · forwarded {router.forwarded} · dropped {router.dropped}",
                S.FS_XS, S.TEXT_MUTED, (x, y))
        y += 22
        y = self.draw_table(surf, router, x, y, w, mask_match=False)

        # event log
        y += 8
        pygame.draw.line(surf, S.BORDER, (x, y), (x + w, y))
        y += 10
        ui.section_title(surf, "Event log", x, y)
        y += 22
        lines_space = (SR.bottom - 12 - y) // 18
        entries = self.log[-max(0, lines_space):] if lines_space > 0 else []
        for tm, txt, level in entries:
            ui.status_dot(surf, S.LEVEL_COLORS[level], (x + 3, y + 8), 3)
            ui.text(surf, ui.ellipsize(txt, S.FS_XS, w - 14), S.FS_XS, S.TEXT_DIM, (x + 12, y))
            y += 18

    def draw_table(self, surf, router, x, y, w, mask_match):
        p = self.sim.packet
        match = lookup(router.routing_table, p.dst_ip)
        cols = (x, x + 132, x + 214, x + w)
        for cx, h, anchor in ((cols[0], "Network", "topleft"), (cols[1], "Next hop", "topleft"),
                              (cols[2], "If", "topleft"), (cols[3], "Cost", "topright")):
            ui.text(surf, h, S.FS_XS, S.TEXT_MUTED, (cx, y), anchor, True)
        y += 20
        for e in router.routing_table:
            is_match = e is match
            if is_match:
                ui.alpha_rect(surf, (x - 6, y - 2, w + 12, 20), S.ACCENT, 34, 5)
            col = S.TEXT if is_match else S.TEXT_DIM
            nh = "connected" if e.kind == "C" else self.net.nodes[e.next_hop].label
            if mask_match and is_match:
                nh, iface = "?", "?"
            else:
                iface = e.interface
            ui.text(surf, str(e.destination), S.FS_XS, col, (cols[0], y), mono=True)
            ui.text(surf, nh, S.FS_XS, col, (cols[1], y), bold=is_match)
            ui.text(surf, iface, S.FS_XS, col, (cols[2], y), mono=True)
            ui.text(surf, str(e.metric), S.FS_XS, col, (cols[3], y), "topright", mono=True)
            y += 19
        if not router.routing_table:
            ui.text(surf, "(empty)", S.FS_XS, S.TEXT_MUTED, (x, y))
            y += 19
        return y

    def draw_decision_side(self, surf):
        sim = self.sim
        d = sim.decision
        p = sim.packet
        router = self.net.nodes[d["router"]]
        ui.panel(surf, SR, S.PANEL, S.ACCENT_DIM)
        x, w = SR.x + 20, SR.width - 40
        y = SR.y + 18
        title = "Routing decision" if d["kind"] == "route" else "Reroute required"
        ui.text(surf, title, S.FS_LG, S.ACCENT if d["kind"] == "route" else S.AMBER, (x, y), bold=True)
        y += 30
        ui.text(surf, f"at {router.label}  ·  packet to {p.dst_ip}", S.FS_SM, S.TEXT_DIM, (x, y))
        y += 26
        if d["kind"] == "route":
            body = ("Dijkstra ranks neighbours by total cost = link cost + the neighbour's distance to the "
                    "destination. Pick the lowest.")
        else:
            body = ("A link on the planned path failed. Routes were recomputed with Dijkstra - choose the "
                    "new lowest-cost next hop.")
        y = ui.paragraph(surf, body, S.FS_XS + 1, S.TEXT, x, y, w) + 6

        self.option_rects = []
        for i, o in enumerate(d["options"]):
            r = pygame.Rect(x, y, w, 50)
            self.option_rects.append((r, o["node"]))
            hov = r.collidepoint(ui.MOUSE) and o["active"]
            fill = S.PANEL_HI if hov else S.PANEL_ALT
            border = S.ACCENT if hov else S.BORDER_HI
            if not o["active"]:
                fill, border = S.RED_SOFT, (90, 30, 46)
            ui.panel(surf, r, fill, border, 10)
            ui.pill(surf, str(i + 1), (r.x + 12, r.centery), S.TEXT, S.BORDER, anchor="midleft")
            ui.text(surf, o["label"], S.FS_MD, S.TEXT if o["active"] else S.RED, (r.x + 44, r.y + 7), bold=True)
            if not o["active"]:
                sub = "link DOWN"
            elif o["remaining"] == math.inf:
                sub = f"link cost {o['link_cost']}  ·  no path onward"
            else:
                sub = f"link cost {o['link_cost']}  ·  then {o['remaining']} to destination"
            ui.text(surf, sub, S.FS_XS, S.TEXT_DIM if o["active"] else S.RED, (r.x + 44, r.y + 29))
            if o["is_prev"]:
                ui.pill(surf, "came from", (r.right - 8, r.y + 7), S.AMBER, S.AMBER_SOFT, anchor="topright", size=S.FS_XS - 2)
            y += 56
        if d.get("feedback"):
            fr = pygame.Rect(x, y + 2, w, 74)
            ui.panel(surf, fr, S.RED_SOFT, S.RED, 10)
            ui.paragraph(surf, d["feedback"], S.FS_XS + 1, S.TEXT, fr.x + 12, fr.y + 8, fr.width - 24, max_lines=3)
            y = fr.bottom + 8
        else:
            y += 6
        pygame.draw.line(surf, S.BORDER, (x, y), (x + w, y))
        y += 10
        ui.section_title(surf, f"{router.label} routing table", x, y)
        y += 22
        y = self.draw_table(surf, router, x, y, w, mask_match=True)
        y += 8
        if y < SR.bottom - 50:
            ui.paragraph(surf, f"TTL {p.ttl}/{p.initial_ttl}  ·  hops so far {p.hops}  ·  simulation paused for your decision",
                         S.FS_XS, S.TEXT_MUTED, x, y, w)


# ===========================================================================
# Stage 8 - Destination host: decapsulation
# ===========================================================================
class DecapsulationScene(Scene):
    stage = 4
    title = "Stage 5 · Decapsulation"

    def enter(self, **kw):
        s = self.session
        p = s.packet
        self.ttl_at_arrival = p.ttl
        self.removed = []
        self.anim = None             # progress of the current layer's checks
        self.reveal_t = None
        self.auto = False
        self.auto_wait = 0.0
        self.btn_next = ui.Button((WR.x + 24, WR.bottom - 64, 280, 46), "Process next layer", self.next_step,
                                  "primary", pygame.K_SPACE, hint="Space")
        self.btn_auto = ui.Button((WR.x + 316, WR.bottom - 64, 170, 46), "Auto-play", self.toggle_auto, "secondary",
                                  pygame.K_a, hint="A")
        self.game.toasts.items.clear()
        self.btn_report = ui.Button((WR.right - 248, WR.bottom - 64, 224, 46), "View delivery report",
                                    lambda: self.game.switch("report"), "primary", pygame.K_RETURN, icon="arrow")
        self.btn_report.visible = False
        self.buttons = [self.btn_next, self.btn_auto, self.btn_report]
        s.timer_running = False

    def checks_for(self, layer):
        s, p = self.session, self.session.packet
        dst = s.dst_host
        if layer == "datalink":
            return [f"Bits from the wire reassembled into a frame",
                    f"Dst MAC {p.l2['dst_mac']} = {dst.label} NIC",
                    "FCS (CRC-32) check passed - no bit errors",
                    "EtherType 0x0800 -> hand payload to IPv4"]
        if layer == "network":
            return [f"Dst IP {p.dst_ip} is this host's address",
                    f"Src IP {p.src_ip} unchanged since Alice sent it",
                    f"Arrived with TTL {self.ttl_at_arrival} (started at {p.initial_ttl})",
                    f"Protocol {enc.PROTO_NUMBERS[p.protocol]} -> hand payload to {p.protocol}"]
        tcp = p.protocol == "TCP"
        return [f"Dst port {p.dst_port} -> PacketChat application",
                "Sequence number in order, ACK sent back to Alice" if tcp else "UDP: no ACK, delivered as-is",
                "Payload handed to the application"]

    def next_step(self):
        p = self.session.packet
        if self.anim is not None or not p.headers:
            return
        self.anim = 0.0

    def toggle_auto(self):
        self.auto = not self.auto
        self.btn_auto.label = "Pause auto" if self.auto else "Auto-play"
        if self.auto:
            self.next_step()

    def update(self, dt):
        super().update(dt)
        p = self.session.packet
        if self.anim is not None:
            self.anim += dt * 0.8
            if self.anim >= 1.0:
                self.anim = None
                self.removed.append(enc.decapsulate(p))
                if not p.headers:
                    self.reveal_t = 0.0
                    self.btn_next.enabled = False
                    self.btn_auto.enabled = False
                    self.btn_report.visible = True
                self.auto_wait = 0.0
        elif self.auto and p.headers:
            self.auto_wait += dt
            if self.auto_wait > 0.5:
                self.next_step()
        if self.reveal_t is not None:
            self.reveal_t += dt

    def draw(self, surf):
        s, p = self.session, self.session.packet
        ui.panel(surf, WR)
        ui.text(surf, f"Delivered to {s.dst_host.label}", S.FS_XL, S.TEXT, (WR.x + 28, WR.y + 24), bold=True)
        ui.text(surf, "The destination host removes the headers in reverse order: Ethernet, then IP, then "
                f"{p.protocol}.", S.FS_SM, S.TEXT_DIM, (WR.x + 28, WR.y + 60))

        stack_r = pygame.Rect(WR.x + 28, WR.y + 100, 400, 250)
        if p.headers:
            draw_nested_stack(surf, p, stack_r, hide_data=True)
            if self.anim is not None:
                layer = p.headers[-1].layer
                ui.alpha_rect(surf, stack_r, S.LAYER_COLORS[layer], int(60 * math.sin(self.anim * math.pi)), 10)
        else:
            ui.panel(surf, stack_r, S.GREEN_SOFT, S.GREEN, 12)
            ui.text(surf, "Application data recovered", S.FS_MD, S.GREEN, (stack_r.x + 18, stack_r.y + 16), bold=True)
            k = self.reveal_t or 0
            shown = p.payload[: int(k * 40)]
            ui.paragraph(surf, f'"{shown}"', S.FS_LG, S.TEXT, stack_r.x + 18, stack_r.y + 52, stack_r.width - 36)
            ui.text(surf, f"From {p.sender_name} to {p.recipient_name}", S.FS_SM, S.TEXT_DIM,
                    (stack_r.x + 18, stack_r.bottom - 32))

        # current protocol data unit, shrinking as headers are removed
        pdu = {"datalink": "Ethernet frame", "network": "IP packet", "transport": f"{p.protocol} segment"}
        name = pdu[p.headers[-1].layer] if p.headers else "Application data"
        ui.section_title(surf, f"Current PDU  ·  {name}", stack_r.x, stack_r.bottom + 24)
        draw_packet_bar(surf, p, (stack_r.centerx, stack_r.bottom + 86), data_w=170, hide_data=bool(p.headers))
        ui.text(surf, "frame  >  packet  >  segment  >  data", S.FS_XS, S.TEXT_MUTED,
                (stack_r.centerx, stack_r.bottom + 126), "midtop", mono=True)

        # processing steps column
        col = pygame.Rect(WR.x + 452, WR.y + 100, WR.width - 452 - 28, 430)
        layers = [("datalink", "Layer 2 · Ethernet"), ("network", "Layer 3 · IPv4"), ("transport", f"Layer 4 · {p.protocol}")]
        y = col.y
        removed_layers = [h.layer for h in self.removed]
        current = p.headers[-1].layer if p.headers else None
        for layer, title in layers:
            color = S.LAYER_COLORS[layer]
            done = layer in removed_layers
            active = layer == current and self.anim is not None
            checks = self.checks_for(layer)
            h = 40 + (len(checks) * 22 if (done or active) else 0)
            r = pygame.Rect(col.x, y, col.width, h)
            ui.panel(surf, r, S.PANEL_ALT if not done else ui.lerp_color(color, S.PANEL, 0.9),
                     color if (done or active) else S.BORDER, 10)
            ui.text(surf, title, S.FS_MD, color if (done or active) else S.TEXT_DIM, (r.x + 16, r.y + 10), bold=True)
            if done:
                ui.pill(surf, "HEADER REMOVED", (r.right - 12, r.y + 10), S.GREEN, S.GREEN_SOFT, anchor="topright")
            elif layer == current and self.anim is None:
                ui.pill(surf, "NEXT", (r.right - 12, r.y + 10), S.ACCENT, S.ACCENT_SOFT, anchor="topright")
            if done or active:
                n_shown = len(checks) if done else int(self.anim * (len(checks) + 1))
                cy = r.y + 40
                for i, chk in enumerate(checks[:n_shown]):
                    ui.check_mark(surf, S.GREEN, (r.x + 24, cy + 8), 4, 2)
                    ui.text(surf, chk, S.FS_SM - 1, S.TEXT, (r.x + 38, cy))
                    cy += 22
            y += h + 10
        if self.reveal_t is not None:
            ui.paragraph(surf, "Only the destination host went all the way up to the application. "
                         "Routers on the path never opened the TCP/UDP segment or the data.",
                         S.FS_SM, S.TEXT_DIM, col.x, y + 6, col.width)

        self.draw_buttons(surf)
        self.draw_side(surf)

    def draw_side(self, surf):
        s, p = self.session, self.session.packet
        y = side_panel(surf, "Who processes which layers?")
        w = SR.width - 40
        routers = [s.network.nodes[n].label for n in p.route if s.network.nodes[n].is_router]
        y = info_card(surf, SR.x + 20, y, w, "Routers on the path: L1-L3 only",
                      f"{', '.join(routers)} each received the frame, checked the MAC, read the destination IP, "
                      "decremented TTL and built a NEW frame for the next link.", S.CYAN, S.FS_XS + 1)
        y = info_card(surf, SR.x + 20, y, w, f"{s.dst_host.label}: L1-L7",
                      "The destination host strips every header and delivers the data to the "
                      "application listening on the destination port.", S.GREEN, S.FS_XS + 1)
        ui.section_title(surf, "Removed so far", SR.x + 20, y + 4)
        y += 28
        if not self.removed:
            ui.text(surf, "nothing yet", S.FS_SM, S.TEXT_MUTED, (SR.x + 20, y))
        for h in self.removed:
            ui.status_dot(surf, S.LAYER_COLORS[h.layer], (SR.x + 25, y + 9))
            ui.text(surf, f"{h.name} header", S.FS_SM, S.TEXT, (SR.x + 38, y))
            y += 24


# ===========================================================================
# Final report (delivered or dropped)
# ===========================================================================
DROP_EXPLAIN = {
    "TTL": ("Why TTL exists",
            "TTL stops packets circulating forever in routing loops. Every router subtracts 1; at 0 the packet "
            "is discarded and a real router would send ICMP Time Exceeded. Use a TTL larger than the number "
            "of routers on the path (5 to Bob)."),
    "Queue": ("Congestion loss",
              "The router's buffer was full, so tail-drop discarded the arriving packet. TCP would notice the "
              "missing ACK and retransmit; UDP would not. This is congestion, not a broken link."),
    "route": ("Destination unreachable",
              "After the failures there was no path left, so the routing table had no entry for the destination. "
              "Restore a link and retransmit."),
}


class ReportScene(Scene):
    stage = 4
    title = "Mission report"
    pausable = False

    def enter(self, **kw):
        s = self.session
        s.timer_running = False
        self.game.toasts.items.clear()
        p = s.packet
        self.delivered = p.status == PacketStatus.DELIVERED
        bx = WR.right - 24
        y = WR.bottom - 64
        if self.delivered:
            self.buttons = [
                ui.Button((bx - 220, y, 220, 46), "Send another message", lambda: self.game.switch("compose"),
                          "primary", pygame.K_RETURN),
                ui.Button((bx - 380, y, 150, 46), "Main menu", self.game.to_menu, "ghost", pygame.K_m),
            ]
        else:
            self.buttons = [
                ui.Button((bx - 220, y, 220, 46), "Retransmit packet", self.retransmit, "primary",
                          pygame.K_RETURN),
                ui.Button((bx - 400, y, 170, 46), "New message", lambda: self.game.switch("compose"), "secondary"),
                ui.Button((bx - 560, y, 150, 46), "Main menu", self.game.to_menu, "ghost", pygame.K_m),
            ]

    def retransmit(self):
        self.session.retransmit()
        self.session.timer_running = True
        self.game.toasts.push(f"Retransmitting (attempt {self.session.attempt}) on a restored network", "info")
        self.game.switch("routing")

    def draw(self, surf):
        s = self.session
        p = s.packet
        sim = s.sim
        ui.panel(surf, WR)
        color = S.GREEN if self.delivered else S.RED
        banner = pygame.Rect(WR.x + 24, WR.y + 22, WR.width - 48, 92)
        ui.panel(surf, banner, ui.lerp_color(color, S.PANEL, 0.86), color, 12)
        if self.delivered:
            ui.circle(surf, color, (banner.x + 46, banner.centery), 24)
            ui.check_mark(surf, S.BG, (banner.x + 46, banner.centery), 10, 4)
            head = "Packet delivered"
            sub = f"{p.sender_name} -> {p.recipient_name}  ·  \"{p.payload}\""
        else:
            ui.circle(surf, color, (banner.x + 46, banner.centery), 24)
            ui.cross_mark(surf, S.BG, (banner.x + 46, banner.centery), 9, 4)
            head = "Packet dropped"
            sub = p.drop_reason or "unknown reason"
        ui.text(surf, head, S.FS_XL, color, (banner.x + 88, banner.y + 16), bold=True)
        ui.paragraph(surf, sub, S.FS_SM, S.TEXT, banner.x + 88, banner.y + 54, banner.width - 110, max_lines=2)

        # stat cards
        route = " > ".join(s.network.nodes[n].label for n in p.route)
        reroute = "Yes" if p.rerouted else "No"
        stats = [
            ("Hop count", f"{p.hops}", "links traversed, incl. final link"),
            ("TTL", f"{p.initial_ttl} -> {p.ttl}", f"{p.initial_ttl - p.ttl} routers forwarded it"),
            ("Latency", f"{sim.latency_ms:.1f} ms", "simulated (links + queues)"),
            ("Rerouted", reroute, f"{sim.failures} link failure(s)"),
            ("Protocol", p.protocol, f"ports {p.src_port} -> {p.dst_port}"),
            ("Background loss", f"{sim.bg_dropped}/{sim.bg_sent}", "congestion drops (other traffic)"),
        ]
        cw = (WR.width - 48 - 2 * 12) // 3
        for i, (k, v, sub) in enumerate(stats):
            r = pygame.Rect(WR.x + 24 + (i % 3) * (cw + 12), WR.y + 130 + (i // 3) * 100, cw, 88)
            ui.panel(surf, r, S.PANEL_ALT, S.BORDER, 10)
            ui.text(surf, k.upper(), S.FS_XS, S.TEXT_MUTED, (r.x + 16, r.y + 12), bold=True)
            ui.text(surf, v, S.FS_XL, S.TEXT, (r.x + 16, r.y + 30), bold=True)
            ui.text(surf, sub, S.FS_XS, S.TEXT_DIM, (r.x + 16, r.y + 64))

        y = WR.y + 342
        ui.section_title(surf, "Route taken", WR.x + 24, y)
        y = ui.paragraph(surf, route, S.FS_SM, S.ACCENT, WR.x + 24, y + 22, WR.width - 48, mono=True)
        if not self.delivered:
            key = next((k for k in DROP_EXPLAIN if k in (p.drop_reason or "")), "route")
            t, body = DROP_EXPLAIN[key]
            info_card(surf, WR.x + 24, y + 10, WR.width - 48, t, body, S.AMBER, S.FS_SM)
        else:
            info_card(surf, WR.x + 24, y + 10, WR.width - 48, "What happened",
                      "IP addresses stayed the same end to end, MAC addresses were rewritten on every link, "
                      "TTL dropped by one at each router, and Dijkstra chose the lowest-cost path"
                      + (" - and recomputed it when a link failed." if p.rerouted else "."), S.ACCENT, S.FS_SM)
        self.draw_buttons(surf)
        self.draw_side(surf)

    def draw_side(self, surf):
        s = self.session
        y = side_panel(surf, "Score breakdown")
        x, w = SR.x + 20, SR.width - 40
        grouped = {}
        for label, pts in s.score_events:
            n, total = grouped.get(label, (0, 0))
            grouped[label] = (n + 1, total + pts)
        for label, (n, total) in grouped.items():
            name = f"{label}  x{n}" if n > 1 else label
            ui.text(surf, ui.ellipsize(name, S.FS_SM, w - 60), S.FS_SM, S.TEXT_DIM, (x, y))
            ui.text(surf, f"{total:+d}", S.FS_SM, S.GREEN if total >= 0 else S.RED, (x + w, y), "topright", True, True)
            y += 24
            if y > SR.bottom - 190:
                break
        pygame.draw.line(surf, S.BORDER, (x, y + 4), (x + w, y + 4))
        y += 14
        ui.text(surf, "Total score", S.FS_MD, S.TEXT, (x, y), bold=True)
        ui.text(surf, str(s.score), S.FS_XL, S.ACCENT, (x + w, y - 6), "topright", True)
        y += 44
        health = s.health
        ui.text(surf, "Network health", S.FS_SM, S.TEXT_DIM, (x, y))
        ui.meter(surf, (x, y + 26, w - 60, 10), health / 100, ui.health_color(health))
        ui.text(surf, f"{health}%", S.FS_MD, ui.health_color(health), (x + w, y + 20), "topright", True)
        y += 56
        won = self.delivered and health >= 50
        verdict = "Mission complete" if won else ("Delivered - network degraded" if self.delivered else "Mission failed")
        ui.text(surf, verdict, S.FS_LG, S.GREEN if won else (S.AMBER if self.delivered else S.RED), (x, y), bold=True)
        ui.text(surf, f"Attempt {s.attempt}  ·  time {int(s.elapsed) // 60:02d}:{int(s.elapsed) % 60:02d}",
                S.FS_XS, S.TEXT_MUTED, (x, y + 30))
