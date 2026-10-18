"""Discrete simulation of the packet's journey.

The engine is updated with a FIXED time step by the game loop, and it is the
only place that changes TTL, hop count, queues or link state. Rendering code
only *reads* this state, so drawing a frame can never forward a packet.

Time model: 1 simulated second of animation = 10 ms of simulated network time
(see MS_PER_SIM_SECOND). Link delays come from Link.delay_ms.
"""

from __future__ import annotations

import math
import random

from .models import PacketStatus
from .routing import (cost_via_neighbor, lookup, recompute_all_tables,
                      shortest_path)
from .topology import DECISION_ROUTER, is_access_link

MS_PER_SIM_SECOND = 10.0
BACKGROUND_RATE = 0.5      # new background packets per core router per second
SURGE_RATE = 10.0          # extra arrivals per second during a traffic surge
SURGE_DURATION = 3.0


class SimEvent:
    def __init__(self, time, kind, text, level="info", points=0):
        self.time = time
        self.kind = kind      # "log" | "alert" | "score"
        self.text = text
        self.level = level    # info | ok | warn | error
        self.points = points


class BackgroundPacket:
    """Cross-traffic from other customers. It only exists to load queues."""

    background = True

    def __init__(self, hops_left):
        self.hops_left = hops_left
        self.came_from = None


class Transit:
    def __init__(self, item, link, frm, to, duration):
        self.item = item
        self.link = link
        self.frm = frm
        self.to = to
        self.elapsed = 0.0
        self.duration = max(duration, 0.05)

    @property
    def progress(self):
        return min(1.0, self.elapsed / self.duration)


class SimulationEngine:
    def __init__(self, network, packet, seed=42, random_events=True,
                 auto_decide=False, decision_routers=(DECISION_ROUTER,),
                 background=True):
        self.network = network
        self.packet = packet
        self.rng = random.Random(seed)
        self.random_events = random_events
        self.auto_decide = auto_decide
        self.decision_routers = set(decision_routers)
        self.background_enabled = background

        self.time = 0.0
        self.state = "ready"          # ready | running | awaiting_decision | finished
        self.transits = []
        self.events = []
        self.score_events = []        # (label, points)
        self.decision = None
        self.decided = set()
        self.plan = []                # currently planned full path
        self.last_hop = None          # most recent forwarding record

        self.failures = 0
        self.random_failure_done = False
        self.failure_cooldown = 3.0
        self.bg_sent = 0
        self.bg_dropped = 0
        self.bg_delivered = 0
        self.drop_penalty = 0.0
        self._congestion_note = {}
        self._bg_score_lost = 0

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def emit(self, kind, text, level="info", points=0):
        self.events.append(SimEvent(self.time, kind, text, level, points))

    def log(self, text, level="info"):
        self.emit("log", text, level)

    def alert(self, text, level="warn"):
        self.emit("alert", text, level)
        self.emit("log", text, level)

    def add_score(self, label, points):
        self.score_events.append((label, points))
        self.emit("score", label, "ok" if points >= 0 else "error", points)

    def label(self, node_id):
        return self.network.nodes[node_id].label

    @property
    def latency_ms(self):
        end = self.packet.delivered_at if self.packet.delivered_at is not None else self.time
        return (end - self.packet.created_at) * MS_PER_SIM_SECOND

    def main_transit(self):
        for t in self.transits:
            if t.item is self.packet:
                return t
        return None

    def upcoming_node(self):
        """Node where the main packet will next be processed."""
        t = self.main_transit()
        return t.to if t else self.packet.current_node

    def remaining_plan(self):
        start = self.upcoming_node()
        if start in self.plan:
            return self.plan[self.plan.index(start):]
        return [start]

    def projected_path(self):
        """Shortest path from the packet's next node using CURRENT tables."""
        path, _ = shortest_path(self.network, self.upcoming_node(), self.packet.dst_host)
        return path or []

    def health(self):
        routers = [r for r in self.network.routers() if r.role == "core"]
        avg_occ = sum(r.occupancy for r in routers) / max(1, len(routers))
        down = sum(1 for l in self.network.links.values() if not l.active)
        h = 100 - 12 * down - 30 * avg_occ - min(30.0, self.drop_penalty)
        return int(max(0, min(100, h)))

    @property
    def loss_rate(self):
        return self.bg_dropped / self.bg_sent if self.bg_sent else 0.0

    # ------------------------------------------------------------------
    # main packet lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """The source host sends the packet to its default gateway."""
        if self.state != "ready":
            return
        p = self.packet
        src = self.network.nodes[p.src_host]
        p.created_at = self.time
        self.plan, _ = shortest_path(self.network, p.src_host, p.dst_host)
        self.plan = self.plan or [p.src_host]
        self.state = "running"
        # Host routing decision: local subnet -> direct, otherwise -> gateway
        gateway = None
        for nb, _ in self.network.neighbors(src.id, active_only=False):
            if self.network.nodes[nb].iface_to(src.id).ip == src.gateway_ip:
                gateway = nb
        if gateway is None:
            self._drop_main("Source host has no default gateway", src.id)
            return
        p.l2 = {"src_mac": src.mac, "dst_mac": self.network.nodes[gateway].iface_to(src.id).mac}
        self.log(f"{src.label} sends to default gateway {self.label(gateway)} ({src.gateway_ip})")
        self._transmit(p, src.id, gateway)

    def _transmit(self, item, frm, to):
        link = self.network.link_between(frm, to)
        if link is None or not link.active:
            if item is self.packet:
                self._drop_main(f"Link {self.label(frm)}-{self.label(to)} is down", frm)
            return False
        if item is self.packet:
            item.status = PacketStatus.IN_TRANSIT
            item.next_hop = to
        else:
            item.came_from = frm
        self.transits.append(Transit(item, link, frm, to, link.delay_ms / MS_PER_SIM_SECOND))
        return True

    def _arrive(self, transit):
        item, node_id = transit.item, transit.to
        node = self.network.nodes[node_id]
        if item is not self.packet:
            self._arrive_background(item, node)
            return
        p = self.packet
        if p.is_final:
            return
        p.hops += 1                       # one more link traversed
        p.current_node = node_id
        p.route.append(node_id)
        p.next_hop = None
        in_iface = node.iface_to(transit.frm).name

        if node.is_host:
            if node.ip == p.dst_ip and p.mark_delivered(self.time):
                self.state = "finished"
                self.alert(f"Delivered to {node.label} ({node.ip}) after {p.hops} hops", "ok")
                self.add_score("Message delivered", 100)
                if p.rerouted:
                    self.add_score("Delivered despite link failure", 50)
            else:
                self._drop_main("Reached a host that is not the destination", node_id)
            return

        # Router: frame accepted only if addressed to this interface's MAC
        if p.l2["dst_mac"] != node.iface_to(transit.frm).mac:
            self._drop_main("Frame not addressed to this router (MAC mismatch)", node_id)
            return
        if not node.enqueue(p):
            self._drop_main(f"Queue overflow at {node.label} (tail drop, "
                            f"{node.queue_capacity}/{node.queue_capacity} full)", node_id)
            return
        p.status = PacketStatus.QUEUED
        self.log(f"Arrived at {node.label} on {in_iface}; queue {len(node.queue)}/{node.queue_capacity}")
        self._maybe_random_failure()

    def _process_main(self, router):
        p = self.packet
        if p.is_final:
            return
        entry = lookup(router.routing_table, p.dst_ip)
        if entry is None:
            self._drop_main(f"No route to {p.dst_ip} at {router.label} (destination unreachable)", router.id)
            return
        planned_next = None
        if router.id in self.plan:
            i = self.plan.index(router.id)
            if i + 1 < len(self.plan):
                planned_next = self.plan[i + 1]
        if router.id in self.decision_routers and router.id not in self.decided:
            self._open_decision(router, "route")
        elif planned_next is not None and planned_next != entry.next_hop:
            self._open_decision(router, "reroute")
        else:
            self._forward(router, entry.next_hop)

    def _forward(self, router, next_id):
        p = self.packet
        if p.is_final:
            return
        link = self.network.link_between(router.id, next_id)
        if link is None or not link.active:
            self._drop_main(f"Outgoing link to {self.label(next_id)} is down", router.id)
            return
        in_iface = router.iface_to(p.route[-2]).name if len(p.route) > 1 else "-"
        if not p.decrement_ttl():
            self._drop_main(f"TTL expired at {router.label} (TTL reached 0)", router.id)
            return
        nxt = self.network.nodes[next_id]
        out = router.iface_to(next_id)
        # Layer 2 is rewritten for the new link; Layer 3 addresses stay the same.
        p.l2 = {"src_mac": out.mac, "dst_mac": nxt.iface_to(router.id).mac}
        record = {
            "router": router.label, "in": in_iface, "out": out.name,
            "next": nxt.label, "ttl": p.ttl, "hops": p.hops,
            "src_mac": p.l2["src_mac"], "dst_mac": p.l2["dst_mac"], "time": self.time,
        }
        p.trace.append(record)
        self.last_hop = record
        router.forwarded += 1
        self.log(f"{router.label}: TTL {p.ttl + 1}->{p.ttl}, {in_iface} -> {out.name}, next {nxt.label}")
        self._transmit(p, router.id, next_id)

    def _drop_main(self, reason, node_id):
        if self.packet.mark_dropped(reason, node_id):
            self.state = "finished"
            self.alert(f"Packet dropped: {reason}", "error")
            self.add_score("Packet lost", -50)

    # ------------------------------------------------------------------
    # routing decisions (player)
    # ------------------------------------------------------------------
    def _open_decision(self, router, kind, attempts=0):
        p = self.packet
        entry = lookup(router.routing_table, p.dst_ip)
        prev = p.route[-2] if len(p.route) > 1 else None
        options = []
        for nb, link in self.network.neighbors(router.id, active_only=False):
            if self.network.nodes[nb].is_host and nb != p.dst_host:
                continue
            lc, rem = cost_via_neighbor(self.network, router.id, nb, p.dst_host)
            options.append({
                "node": nb, "label": self.label(nb), "active": link.active,
                "link_cost": link.cost, "remaining": rem,
                "total": lc + rem, "is_prev": nb == prev,
            })
        options.sort(key=lambda o: o["label"])
        self.decision = {
            "router": router.id, "kind": kind, "options": options,
            "correct": entry.next_hop if entry else None, "entry": entry,
            "attempts": attempts, "feedback": None,
        }
        self.state = "awaiting_decision"
        if kind == "route":
            self.log(f"{router.label}: choose the next hop for {p.dst_ip}")
        else:
            self.alert(f"Reroute needed at {router.label}: planned path is broken", "warn")
        if self.auto_decide:
            self.choose_next_hop(self.decision["correct"])

    def choose_next_hop(self, node_id):
        """Player's answer. Returns (correct, explanation)."""
        d = self.decision
        if d is None:
            return False, "No decision pending"
        router = self.network.nodes[d["router"]]
        opt = next((o for o in d["options"] if o["node"] == node_id), None)
        best = next((o for o in d["options"] if o["node"] == d["correct"]), None)
        if opt is None or best is None:
            return False, "Invalid choice"
        if node_id == d["correct"]:
            pts = 25 if d["attempts"] == 0 else 10
            if d["kind"] == "reroute":
                self.packet.rerouted = True
            self.add_score("Correct next hop" if d["kind"] == "route" else "Correct reroute", pts)
            msg = (f"Correct. Via {opt['label']}: {opt['link_cost']} + {opt['remaining']} = "
                   f"{opt['total']}, the lowest total cost. Routing table: "
                   f"{d['entry'].destination} -> {opt['label']} ({d['entry'].interface}).")
            self.decided.add(router.id)
            self.decision = None
            self.state = "running"
            # new plan = path so far + fresh shortest path from here
            tail, _ = shortest_path(self.network, router.id, self.packet.dst_host)
            self.plan = self.packet.route[:-1] + (tail or [router.id])
            self.log(msg, "ok")
            self._forward(router, node_id)
            return True, msg

        d["attempts"] += 1
        self.add_score("Wrong next hop", -5)
        if not opt["active"]:
            msg = f"The link to {opt['label']} is DOWN - nothing can be forwarded on it."
        elif opt["is_prev"]:
            msg = (f"{opt['label']} is where the packet came from. Sending it back "
                   f"could create a routing loop and waste TTL.")
        elif opt["total"] == math.inf:
            msg = f"{opt['label']} has no remaining path to the destination."
        else:
            msg = (f"Via {opt['label']}: {opt['link_cost']} + {opt['remaining']} = {opt['total']}. "
                   f"Another neighbour offers a lower total - Dijkstra picks the minimum.")
        d["feedback"] = msg
        return False, msg

    # ------------------------------------------------------------------
    # link failures
    # ------------------------------------------------------------------
    def safe_failure_candidates(self):
        """Backbone links on the remaining path whose loss keeps the
        destination reachable from the packet's next node."""
        remaining = self.remaining_plan()
        current = self.main_transit()
        start = self.upcoming_node()
        out = []
        for a, b in zip(remaining, remaining[1:]):
            link = self.network.link_between(a, b)
            if link is None or not link.active or is_access_link(self.network, link):
                continue
            if current is not None and current.link is link:
                continue
            link.active = False
            path, _ = shortest_path(self.network, start, self.packet.dst_host)
            link.active = True
            if path:
                out.append(link)
        return out

    def fail_link(self, link_id, cause="manual"):
        link = self.network.links[link_id]
        if not link.active:
            return False, "Link is already down"
        t = self.main_transit()
        if t is not None and t.link is link:
            return False, "The packet is on that link right now - try another"
        link.active = False
        self.failures += 1
        self.failure_cooldown = 4.0
        recompute_all_tables(self.network)
        a, b = self.label(link.a), self.label(link.b)
        on_path = any(self.network.link_between(x, y) is link
                      for x, y in zip(self.remaining_plan(), self.remaining_plan()[1:]))
        extra = " Packet's route affected - Dijkstra recalculated." if on_path else " Routes recalculated."
        self.alert(f"Link {a}-{b} FAILED ({cause}).{extra}", "error")
        # lose background packets that were on the wire
        lost = [tr for tr in self.transits if tr.link is link and tr.item is not self.packet]
        for tr in lost:
            self.transits.remove(tr)
        self._refresh_decision()
        return True, f"Link {a}-{b} failed"

    def fail_next_route_link(self, cause="manual"):
        cands = self.safe_failure_candidates()
        if not cands:
            return False, "No safe link to fail on the remaining route"
        link = cands[0] if cause == "manual" else self.rng.choice(cands)
        return self.fail_link(link.id, cause)

    def restore_link(self, link_id):
        link = self.network.links[link_id]
        if link.active:
            return False
        link.active = True
        recompute_all_tables(self.network)
        self.alert(f"Link {self.label(link.a)}-{self.label(link.b)} restored", "ok")
        self._refresh_decision()
        return True

    def restore_all(self):
        restored = [l for l in self.network.links.values() if not l.active]
        for l in restored:
            l.active = True
        if restored:
            recompute_all_tables(self.network)
            self.alert(f"{len(restored)} link(s) restored", "ok")
            self._refresh_decision()
        return len(restored)

    def toggle_link(self, link_id):
        if self.network.links[link_id].active:
            return self.fail_link(link_id, "manual")
        self.restore_link(link_id)
        return True, "Link restored"

    def _refresh_decision(self):
        """Link state changed while the player is deciding: rebuild the options."""
        if self.decision is None:
            return
        router = self.network.nodes[self.decision["router"]]
        kind = self.decision["kind"]
        if kind == "reroute":
            entry = lookup(router.routing_table, self.packet.dst_ip)
            i = self.plan.index(router.id) if router.id in self.plan else -1
            planned = self.plan[i + 1] if 0 <= i < len(self.plan) - 1 else None
            if entry is not None and entry.next_hop == planned:
                # the original path works again - no reroute needed any more
                self.decision = None
                self.state = "running"
                self.log(f"{router.label}: original route restored, forwarding normally", "ok")
                self._forward(router, planned)
                return
        self._open_decision(router, kind, self.decision["attempts"])

    def _maybe_random_failure(self):
        if (not self.random_events or self.random_failure_done
                or self.failure_cooldown > 0 or self.state != "running"):
            return
        if self.rng.random() < 0.35:
            ok, _ = self.fail_next_route_link(cause="random event")
            if ok:
                self.random_failure_done = True

    # ------------------------------------------------------------------
    # congestion
    # ------------------------------------------------------------------
    def surge(self, router_id):
        router = self.network.nodes[router_id]
        if not router.is_router:
            return
        router.surge_time = SURGE_DURATION
        self.alert(f"Traffic surge at {router.label}: many flows arriving at once", "warn")
        for _ in range(router.queue_capacity):
            self._inject_background(router)

    def _inject_background(self, router):
        self.bg_sent += 1
        if not router.enqueue(BackgroundPacket(self.rng.randint(1, 2))):
            self._background_dropped(router)

    def _background_dropped(self, router):
        self.bg_dropped += 1
        self.drop_penalty += 3
        if self._bg_score_lost < 20:
            self._bg_score_lost += 1
            self.score_events.append(("Background packet lost", -1))
        last = self._congestion_note.get(router.id, -99)
        if self.time - last > 2.0:
            self._congestion_note[router.id] = self.time
            self.alert(f"Congestion at {router.label}: queue full, tail-drop discarding packets", "warn")

    def _arrive_background(self, item, node):
        item.hops_left -= 1
        if node.is_host or item.hops_left <= 0:
            self.bg_delivered += 1
            return
        if not node.enqueue(item):
            self._background_dropped(node)

    def _process_background(self, item, router):
        choices = [nb for nb, _ in self.network.neighbors(router.id)
                   if self.network.nodes[nb].is_router
                   and self.network.nodes[nb].role != "gateway" and nb != item.came_from]
        if not choices:
            self.bg_delivered += 1
            return
        self._transmit(item, router.id, self.rng.choice(choices))

    # ------------------------------------------------------------------
    # fixed-step update
    # ------------------------------------------------------------------
    def update(self, dt):
        if self.state in ("ready", "awaiting_decision", "finished"):
            return
        self.time += dt
        self.failure_cooldown = max(0.0, self.failure_cooldown - dt)
        self.drop_penalty = max(0.0, self.drop_penalty - 2.0 * dt)

        # 1. background traffic arrivals
        if self.background_enabled:
            for r in self.network.routers():
                rate = 0.0
                if r.role == "core":
                    rate += BACKGROUND_RATE
                if r.surge_time > 0:
                    r.surge_time = max(0.0, r.surge_time - dt)
                    rate += SURGE_RATE
                if rate and self.rng.random() < rate * dt:
                    self._inject_background(r)

        # 2. move packets along links
        for t in list(self.transits):
            t.elapsed += dt
            if t.elapsed >= t.duration and t in self.transits:
                self.transits.remove(t)
                self._arrive(t)
                if self.state != "running":
                    return

        # 3. routers forward from their queues (FIFO, service_rate per second)
        for r in self.network.routers():
            if not r.queue:
                r.service_timer = 0.0
                continue
            r.service_timer += dt
            interval = 1.0 / r.service_rate
            while r.queue and r.service_timer >= interval:
                r.service_timer -= interval
                item = r.queue.popleft()
                if item is self.packet:
                    self._process_main(r)
                    if self.state != "running":
                        return
                else:
                    self._process_background(item, r)
