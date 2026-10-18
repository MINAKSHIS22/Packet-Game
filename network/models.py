"""Core data models for the network simulation.

Everything here is plain Python (no Pygame), so it can be unit-tested
independently of the user interface.

This is an *educational, discrete simulation*: the objects below model the
information a real network carries (addresses, TTL, queues, link costs) but
they do not send real frames or bits.
"""

from __future__ import annotations

import ipaddress
import itertools
from collections import deque


class PacketStatus:
    CREATED = "CREATED"            # application data exists
    ENCAPSULATED = "ENCAPSULATED"  # headers added, ready to send
    IN_TRANSIT = "IN_TRANSIT"      # travelling on a link
    QUEUED = "QUEUED"              # waiting in a router queue
    DELIVERED = "DELIVERED"        # reached the destination host
    DROPPED = "DROPPED"            # discarded (TTL, queue overflow, no route)

    FINAL = (DELIVERED, DROPPED)


class Interface:
    """One network interface (NIC/port) of a node, facing one neighbour."""

    def __init__(self, name, mac, ip, neighbor, link_id):
        self.name = name          # e.g. "eth1"
        self.mac = mac            # Layer 2 address (local link only)
        self.ip = ip              # Layer 3 address of this interface
        self.neighbor = neighbor  # node id on the other side of the link
        self.link_id = link_id

    def __repr__(self):
        return f"Interface({self.name}, {self.mac}, {self.ip} -> {self.neighbor})"


class Node:
    """Base class for hosts and routers."""

    kind = "node"

    def __init__(self, node_id, label, pos):
        self.id = node_id
        self.label = label
        self.pos = pos            # normalised (0..1, 0..1) position on the map
        self.interfaces = {}      # neighbour id -> Interface

    def iface_to(self, neighbor_id):
        return self.interfaces[neighbor_id]

    @property
    def is_router(self):
        return self.kind == "router"

    @property
    def is_host(self):
        return self.kind == "host"


class Host(Node):
    kind = "host"

    def __init__(self, node_id, label, pos, ip, prefix_len, gateway_ip, owner=""):
        super().__init__(node_id, label, pos)
        self.ip = ip
        self.prefix_len = prefix_len
        self.gateway_ip = gateway_ip
        self.owner = owner  # person using this host, e.g. "Bob"

    @property
    def network(self):
        return ipaddress.ip_interface(f"{self.ip}/{self.prefix_len}").network

    @property
    def netmask(self):
        return str(self.network.netmask)

    @property
    def mac(self):
        # A host in this topology has exactly one NIC.
        return next(iter(self.interfaces.values())).mac

    def is_local(self, ip):
        """True if `ip` is on this host's own subnet (ip AND mask == network)."""
        return ipaddress.ip_address(ip) in self.network


class Router(Node):
    kind = "router"

    def __init__(self, node_id, label, pos, role="core",
                 queue_capacity=8, service_rate=4.0):
        super().__init__(node_id, label, pos)
        self.role = role                      # gateway | edge | core
        self.routing_table = []               # list of routing.RouteEntry
        self.queue = deque()                  # FIFO queue of waiting packets
        self.queue_capacity = queue_capacity  # bounded buffer size
        self.service_rate = service_rate      # packets forwarded per sim-second
        self.service_timer = 0.0
        self.forwarded = 0
        self.dropped = 0
        self.surge_time = 0.0                 # seconds of extra load remaining

    @property
    def occupancy(self):
        return len(self.queue) / self.queue_capacity

    @property
    def is_full(self):
        return len(self.queue) >= self.queue_capacity

    def enqueue(self, item):
        """Tail-drop policy: accept if there is room, otherwise reject."""
        if self.is_full:
            self.dropped += 1
            return False
        self.queue.append(item)
        return True


class Link:
    """A bidirectional point-to-point link."""

    def __init__(self, link_id, a, b, cost, delay_ms, bandwidth_mbps=100):
        self.id = link_id
        self.a = a
        self.b = b
        self.cost = cost                  # routing metric used by Dijkstra
        self.delay_ms = delay_ms          # simulated propagation + transmission
        self.bandwidth_mbps = bandwidth_mbps
        self.active = True

    def other(self, node_id):
        return self.b if node_id == self.a else self.a

    def connects(self, x, y):
        return {x, y} == {self.a, self.b}

    def __repr__(self):
        state = "up" if self.active else "DOWN"
        return f"Link({self.a}-{self.b}, cost={self.cost}, {state})"


class Network:
    """Graph of nodes and links stored as an adjacency list."""

    def __init__(self):
        self.nodes = {}
        self.links = {}
        self.adj = {}             # node id -> list[Link]
        self._order = []

    # -- construction -----------------------------------------------------
    def add_node(self, node):
        self.nodes[node.id] = node
        self.adj[node.id] = []
        self._order.append(node.id)
        return node

    def add_link(self, a, b, cost, delay_ms, a_ip=None, b_ip=None, bandwidth_mbps=100):
        link_id = len(self.links) + 1
        link = Link(link_id, a, b, cost, delay_ms, bandwidth_mbps)
        self.links[link_id] = link
        self.adj[a].append(link)
        self.adj[b].append(link)
        # Point-to-point router links get a 10.0.<id>.0/30 subnet.
        a_ip = a_ip or f"10.0.{link_id}.1"
        b_ip = b_ip or f"10.0.{link_id}.2"
        for node_id, ip, other in ((a, a_ip, b), (b, b_ip, a)):
            node = self.nodes[node_id]
            index = len(node.interfaces)
            node_no = self._order.index(node_id) + 1
            mac = f"02:50:50:00:{node_no:02X}:{index:02X}"
            node.interfaces[other] = Interface(f"eth{index}", mac, ip, other, link_id)
        return link

    # -- queries ----------------------------------------------------------
    def neighbors(self, node_id, active_only=True):
        """[(neighbour_id, link), ...] for links touching node_id."""
        return [(l.other(node_id), l) for l in self.adj[node_id]
                if l.active or not active_only]

    def link_between(self, x, y):
        for link in self.adj[x]:
            if link.connects(x, y):
                return link
        return None

    def routers(self):
        return [n for n in self.nodes.values() if n.is_router]

    def hosts(self):
        return [n for n in self.nodes.values() if n.is_host]

    def host_by_ip(self, ip):
        for h in self.hosts():
            if h.ip == ip:
                return h
        return None

    def active_link_count(self):
        return sum(1 for l in self.links.values() if l.active)


class Packet:
    """The player's message as it travels through the network."""

    _ids = itertools.count(1)

    def __init__(self, src_host, dst_host, payload, sender_name="Alice",
                 protocol="TCP", ttl=8, created_at=0.0, background=False):
        self.id = next(Packet._ids)
        self.sender_name = sender_name
        self.src_host = src_host.id
        self.dst_host = dst_host.id
        self.src_ip = src_host.ip
        self.dst_ip = dst_host.ip
        self.recipient_name = dst_host.owner
        self.payload = payload               # application-layer data (str)
        self.protocol = protocol             # "TCP" or "UDP"
        self.src_port = 49152                # client ephemeral port
        self.dst_port = 5000                 # PacketChat application port
        self.headers = []                    # encapsulation stack (inner -> outer)
        self.on_wire = False                 # physical-layer representation done
        self.l2 = {"src_mac": None, "dst_mac": None}  # current frame header
        self.ttl = ttl
        self.initial_ttl = ttl
        self.hops = 0                        # links traversed (incl. last one)
        self.current_node = src_host.id
        self.route = [src_host.id]           # path actually taken so far
        self.next_hop = None
        self.created_at = created_at         # simulated time (seconds)
        self.delivered_at = None
        self.status = PacketStatus.CREATED
        self.drop_reason = None
        self.drop_node = None
        self.rerouted = False
        self.background = background
        self.trace = []                      # per-forwarding records

    @property
    def is_final(self):
        return self.status in PacketStatus.FINAL

    def mark_delivered(self, time):
        """Returns False if the packet was already delivered/dropped."""
        if self.is_final:
            return False
        self.status = PacketStatus.DELIVERED
        self.delivered_at = time
        return True

    def mark_dropped(self, reason, node=None):
        if self.is_final:
            return False
        self.status = PacketStatus.DROPPED
        self.drop_reason = reason
        self.drop_node = node
        return True

    def decrement_ttl(self):
        """Called once per router forwarding event. Never goes negative.

        Returns True if the packet may still be forwarded.
        """
        if self.ttl > 0:
            self.ttl -= 1
        return self.ttl > 0
