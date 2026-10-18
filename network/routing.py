"""Routing: Dijkstra's shortest-path algorithm and routing tables.

The algorithm is implemented by hand (no graph library) so it can be
explained in a viva:

    1. dist[source] = 0, every other dist = infinity
    2. Repeatedly take the unvisited node with the smallest dist (min-heap)
    3. For every active link (u, v): if dist[u] + cost < dist[v], update it
       and remember prev[v] = u
    4. Follow prev[] backwards from the destination to rebuild the path

Routing tables are derived from Dijkstra (this is how link-state protocols
such as OSPF work: every router knows the topology and computes its own
shortest-path tree). Tables are recomputed instantly whenever a link changes
state - real networks need some convergence time.
"""

from __future__ import annotations

import heapq
import ipaddress
import math


def dijkstra(network, source):
    """Return (dist, prev) dictionaries for all nodes, using active links only."""
    dist = {node_id: math.inf for node_id in network.nodes}
    prev = {node_id: None for node_id in network.nodes}
    dist[source] = 0
    heap = [(0, source)]            # (distance so far, node id)
    visited = set()

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        # Hosts are end systems: they never forward traffic for others.
        if u != source and network.nodes[u].is_host:
            continue
        for v, link in network.neighbors(u, active_only=True):
            new_dist = d + link.cost
            if new_dist < dist[v]:
                dist[v] = new_dist
                prev[v] = u
                heapq.heappush(heap, (new_dist, v))
    return dist, prev


def shortest_path(network, source, target):
    """Return (path, cost). path is None if the target is unreachable."""
    dist, prev = dijkstra(network, source)
    if dist[target] == math.inf:
        return None, math.inf
    path = []
    node = target
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    return path, dist[target]


def path_cost(network, path):
    return sum(network.link_between(a, b).cost for a, b in zip(path, path[1:]))


class RouteEntry:
    """One row of a router's routing table."""

    def __init__(self, destination, next_hop, next_hop_ip, interface, metric, kind):
        self.destination = ipaddress.ip_network(destination)
        self.next_hop = next_hop          # neighbour node id
        self.next_hop_ip = next_hop_ip    # neighbour's interface IP ("" if connected)
        self.interface = interface        # outgoing interface name
        self.metric = metric
        self.kind = kind                  # "C" connected, "O" learned (link-state), "S*" default

    @property
    def prefix_len(self):
        return self.destination.prefixlen

    def __repr__(self):
        return f"{self.destination} via {self.next_hop} ({self.interface}) metric {self.metric}"


def build_routing_table(network, router_id):
    router = network.nodes[router_id]
    table = []
    covered = set()

    # 1. Directly connected LANs
    for neighbor_id, link in network.neighbors(router_id, active_only=True):
        node = network.nodes[neighbor_id]
        if node.is_host:
            iface = router.iface_to(neighbor_id)
            table.append(RouteEntry(node.network, neighbor_id, "", iface.name, 0, "C"))
            covered.add(node.network)

    # 2. A customer gateway just uses a default route towards its ISP.
    if router.role == "gateway":
        for neighbor_id, link in network.neighbors(router_id, active_only=True):
            if network.nodes[neighbor_id].is_router:
                iface = router.iface_to(neighbor_id)
                nh_ip = network.nodes[neighbor_id].iface_to(router_id).ip
                table.append(RouteEntry("0.0.0.0/0", neighbor_id, nh_ip, iface.name, link.cost, "S*"))
        return table

    # 3. Remote LANs learned from the shortest-path tree
    dist, prev = dijkstra(network, router_id)
    for host in network.hosts():
        if host.network in covered or dist[host.id] == math.inf:
            continue          # no route = destination unreachable
        first_hop = host.id
        while prev[first_hop] != router_id:
            first_hop = prev[first_hop]
        iface = router.iface_to(first_hop)
        nh_ip = network.nodes[first_hop].iface_to(router_id).ip
        table.append(RouteEntry(host.network, first_hop, nh_ip, iface.name, dist[host.id], "O"))
        covered.add(host.network)

    table.sort(key=lambda e: (e.kind != "C", int(e.destination.network_address)))
    return table


def recompute_all_tables(network):
    for router in network.routers():
        router.routing_table = build_routing_table(network, router.id)


def lookup(table, dst_ip):
    """Longest-prefix match. Returns the best RouteEntry or None."""
    address = ipaddress.ip_address(dst_ip)
    best = None
    for entry in table:
        if address in entry.destination:
            if best is None or entry.prefix_len > best.prefix_len:
                best = entry
    return best


def cost_via_neighbor(network, router_id, neighbor_id, target):
    """Total cost of reaching target if router_id sends to neighbor_id first.

    Used to explain routing decisions to the player:
    total = cost(router -> neighbour) + shortest distance(neighbour -> target)
    The neighbour's distance is computed without going back through router_id.
    """
    link = network.link_between(router_id, neighbor_id)
    if link is None or not link.active:
        return math.inf, math.inf
    if neighbor_id == target:
        return link.cost, 0
    saved = [l for l in network.adj[router_id] if l.active]
    for l in saved:
        l.active = False
    try:
        dist, _ = dijkstra(network, neighbor_id)
        remaining = dist[target]
    finally:
        for l in saved:
            l.active = True
    return link.cost, remaining
