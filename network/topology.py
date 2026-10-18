"""The fixed demo topology used by the game.

    Alice-PC -- GW-A -- ISP-E ==== ISP backbone (ISP-1 .. ISP-5) ==== EDGE-B -- Bob-PC
                                                                  ==== EDGE-C -- Charlie-PC
                                                                  ==== EDGE-D -- Diana-PC

Link costs are chosen so that every recipient has ONE unique shortest path
and at least one alternate path through the backbone (so a link failure on
the backbone never makes the demo impossible).
"""

from .models import Host, Network, Router

# recipient name -> destination host id
RECIPIENTS = {
    "Bob": "BOB",
    "Charlie": "CHARLIE",
    "Diana": "DIANA",
}

SOURCE_HOST = "ALICE"
DECISION_ROUTER = "ISPE"   # where the player makes the main routing decision


def build_demo_network():
    net = Network()

    # --- hosts ---------------------------------------------------------
    net.add_node(Host("ALICE", "Alice-PC", (0.05, 0.50), "192.168.1.10", 24, "192.168.1.1", "Alice"))
    # --- routers -------------------------------------------------------
    net.add_node(Router("GWA", "GW-A", (0.16, 0.50), role="gateway"))
    net.add_node(Router("ISPE", "ISP-E", (0.28, 0.50), role="edge"))
    net.add_node(Router("ISP1", "ISP-1", (0.42, 0.22)))
    net.add_node(Router("ISP2", "ISP-2", (0.42, 0.78)))
    net.add_node(Router("ISP3", "ISP-3", (0.56, 0.50)))
    net.add_node(Router("ISP4", "ISP-4", (0.70, 0.22)))
    net.add_node(Router("ISP5", "ISP-5", (0.70, 0.78)))
    net.add_node(Router("EDGEB", "EDGE-B", (0.83, 0.14), role="edge"))
    net.add_node(Router("EDGEC", "EDGE-C", (0.83, 0.50), role="edge"))
    net.add_node(Router("EDGED", "EDGE-D", (0.83, 0.86), role="edge"))
    net.add_node(Host("BOB", "Bob-PC", (0.95, 0.14), "192.168.3.20", 24, "192.168.3.1", "Bob"))
    net.add_node(Host("CHARLIE", "Charlie-PC", (0.95, 0.50), "192.168.4.30", 24, "192.168.4.1", "Charlie"))
    net.add_node(Host("DIANA", "Diana-PC", (0.95, 0.86), "192.168.5.40", 24, "192.168.5.1", "Diana"))

    def link(a, b, cost, a_ip=None, b_ip=None):
        net.add_link(a, b, cost, delay_ms=cost * 2 + 1, a_ip=a_ip, b_ip=b_ip)

    # Access links (LANs)
    link("ALICE", "GWA", 1, "192.168.1.10", "192.168.1.1")
    # Customer uplink to the ISP
    link("GWA", "ISPE", 2)
    # ISP backbone
    link("ISPE", "ISP1", 2)
    link("ISPE", "ISP2", 3)
    link("ISP1", "ISP3", 2)
    link("ISP2", "ISP3", 2)
    link("ISP1", "ISP4", 3)
    link("ISP2", "ISP5", 3)
    link("ISP3", "ISP4", 2)
    link("ISP3", "ISP5", 3)
    link("ISP4", "EDGEB", 1)
    link("ISP4", "EDGEC", 4)
    link("ISP3", "EDGEC", 3)
    link("ISP5", "EDGEC", 2)
    link("ISP5", "EDGED", 1)
    # Destination LANs
    link("EDGEB", "BOB", 1, "192.168.3.1", "192.168.3.20")
    link("EDGEC", "CHARLIE", 1, "192.168.4.1", "192.168.4.30")
    link("EDGED", "DIANA", 1, "192.168.5.1", "192.168.5.40")

    from .routing import recompute_all_tables
    recompute_all_tables(net)
    return net


def is_access_link(net, link):
    """Links touching a host or the customer uplink are single points of
    failure; random failures never pick them."""
    ends = {link.a, link.b}
    if any(net.nodes[e].is_host for e in ends):
        return True
    return ends == {"GWA", "ISPE"}
