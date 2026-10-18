"""Shared game state (Session) and the Scene base class."""

from __future__ import annotations

from network import encapsulation as enc
from network.models import Packet
from network.simulation import SimulationEngine
from network.topology import RECIPIENTS, SOURCE_HOST, build_demo_network


class Session:
    """Everything about the current mission, shared by all scenes."""

    def __init__(self, seed=42):
        # player inputs (kept between missions)
        self.sender = "Alice"
        self.recipient = "Bob"
        self.message = "Hi Bob! Meet me at the library at 5."
        self.ttl = 8
        self.random_events = True
        self.fixed_seed = seed is not None
        self.seed = seed if seed is not None else 42
        self.reset_mission()

    def reset_mission(self):
        self.network = build_demo_network()
        self.packet = None
        self.sim = None
        self.score_log = []          # score events from stages before routing
        self.elapsed = 0.0
        self.timer_running = False
        self.attempt = 1

    # --- packet / simulation ----------------------------------------------
    @property
    def src_host(self):
        return self.network.nodes[SOURCE_HOST]

    @property
    def dst_host(self):
        return self.network.nodes[RECIPIENTS[self.recipient]]

    @property
    def gateway(self):
        return self.network.nodes["GWA"]

    def create_packet(self):
        self.packet = Packet(self.src_host, self.dst_host, self.message,
                             sender_name=self.sender, ttl=self.ttl)
        return self.packet

    def start_simulation(self):
        import random
        seed = self.seed if self.fixed_seed else random.randrange(1_000_000)
        self.sim = SimulationEngine(self.network, self.packet, seed=seed,
                                    random_events=self.random_events)
        return self.sim

    def retransmit(self):
        """Send a fresh copy of the message (as TCP would after a loss)."""
        old = self.packet
        if self.sim:
            self.score_log.extend(self.sim.score_events)
        self.network = build_demo_network()
        if old is not None and old.drop_reason and "TTL" in old.drop_reason:
            self.ttl = max(self.ttl, 8)
        self.create_packet()
        p = self.packet
        enc.encapsulate(p, "transport", protocol=old.protocol if old else "TCP")
        enc.encapsulate(p, "network")
        enc.encapsulate(p, "datalink", src_mac=self.src_host.mac,
                        dst_mac=self.gateway.iface_to(SOURCE_HOST).mac)
        enc.encapsulate(p, "physical")
        self.attempt += 1
        self.start_simulation()

    # --- score / health ---------------------------------------------------
    def add_score(self, label, points):
        self.score_log.append((label, points))

    @property
    def score_events(self):
        return self.score_log + (self.sim.score_events if self.sim else [])

    @property
    def score(self):
        return sum(p for _, p in self.score_events)

    @property
    def health(self):
        return self.sim.health() if self.sim else 100


class Scene:
    stage = None          # index into settings.STAGES (None = no stepper highlight)
    title = ""
    chrome = True         # draw the top status bar
    pausable = True

    def __init__(self, game):
        self.game = game
        self.buttons = []

    @property
    def session(self):
        return self.game.session

    def enter(self, **kwargs):
        pass

    def is_typing(self):
        return False

    def toast_area(self):
        """(x, y, width, grow_up) where alerts are shown for this scene."""
        from . import settings as S
        return (S.WORK_RECT[0] + S.WORK_RECT[2] - 400, S.CONTENT_Y + 12, 386, False)

    def handle(self, e):
        for b in list(self.buttons):
            if b.handle(e):
                return True
        return False

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        pass

    def draw_buttons(self, surf):
        for b in self.buttons:
            b.draw(surf)
