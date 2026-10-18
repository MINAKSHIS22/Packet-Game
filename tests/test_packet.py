"""Packet, encapsulation, forwarding, TTL, queue and simulation tests."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network import encapsulation as enc
from network.models import Packet, PacketStatus, Router
from network.simulation import SimulationEngine
from network.topology import build_demo_network

DT = 1 / 60


def make_packet(net, dst="BOB", ttl=8, protocol="TCP"):
    src, dest = net.nodes["ALICE"], net.nodes[dst]
    p = Packet(src, dest, "Hello Bob!", ttl=ttl)
    enc.encapsulate(p, "transport", protocol=protocol)
    enc.encapsulate(p, "network")
    gw = net.nodes["GWA"]
    enc.encapsulate(p, "datalink", src_mac=src.mac, dst_mac=gw.iface_to("ALICE").mac)
    enc.encapsulate(p, "physical")
    return p


def run(sim, seconds=60):
    sim.start()
    for _ in range(int(seconds / DT)):
        sim.update(DT)
        if sim.state == "finished":
            break
    return sim


def quiet_sim(net, packet, **kw):
    kw.setdefault("auto_decide", True)
    kw.setdefault("random_events", False)
    kw.setdefault("background", False)
    return SimulationEngine(net, packet, **kw)


class TestEncapsulation(unittest.TestCase):
    def test_9_headers_added_in_order(self):
        net = build_demo_network()
        p = make_packet(net)
        self.assertEqual([h.layer for h in p.headers], ["transport", "network", "datalink"])
        self.assertEqual([h.name for h in p.headers], ["TCP", "IPv4", "Ethernet"])
        self.assertTrue(p.on_wire)
        self.assertIsNone(enc.next_layer(p))

    def test_out_of_order_rejected(self):
        net = build_demo_network()
        p = Packet(net.nodes["ALICE"], net.nodes["BOB"], "hi")
        with self.assertRaises(enc.EncapsulationError):
            enc.encapsulate(p, "network")
        with self.assertRaises(enc.EncapsulationError):
            enc.encapsulate(p, "transport", protocol="ICMP")

    def test_10_decapsulation_reverse_order(self):
        net = build_demo_network()
        p = make_packet(net, protocol="UDP")
        removed = [enc.decapsulate(p).name for _ in range(3)]
        self.assertEqual(removed, ["Ethernet", "IPv4", "UDP"])
        self.assertEqual(p.payload, "Hello Bob!")
        with self.assertRaises(enc.EncapsulationError):
            enc.decapsulate(p)

    def test_bitstream_contains_all_segments(self):
        net = build_demo_network()
        p = make_packet(net)
        names = [n for n, _ in enc.frame_bytes(p)]
        self.assertEqual(names, ["eth", "ip", "l4", "data", "fcs"])
        bits = enc.bitstream(p)
        self.assertTrue(all(b in "01" for _, b in bits))
        self.assertEqual(len(bits) % 8, 0)


class TestForwarding(unittest.TestCase):
    def test_4_ttl_decrements_once_per_router(self):
        net = build_demo_network()
        p = make_packet(net, ttl=8)
        sim = run(quiet_sim(net, p))
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        routers_on_path = [n for n in p.route if net.nodes[n].is_router]
        self.assertEqual(len(routers_on_path), 5)
        self.assertEqual(len(p.trace), 5)
        self.assertEqual(p.ttl, 8 - 5)
        ttls = [rec["ttl"] for rec in p.trace]
        self.assertEqual(ttls, [7, 6, 5, 4, 3])

    def test_5_ttl_expiry_drops_packet(self):
        net = build_demo_network()
        p = make_packet(net, ttl=3)
        run(quiet_sim(net, p))
        self.assertEqual(p.status, PacketStatus.DROPPED)
        self.assertIn("TTL expired", p.drop_reason)
        self.assertEqual(p.ttl, 0)            # never negative
        self.assertEqual(p.drop_node, "ISP1")  # third router on the path

    def test_6_hops_independent_of_ttl(self):
        net = build_demo_network()
        p = make_packet(net, ttl=8)
        run(quiet_sim(net, p))
        # 6 links traversed (incl. final link to Bob), only 5 routers decremented TTL
        self.assertEqual(p.hops, 6)
        self.assertEqual(p.initial_ttl - p.ttl, 5)

    def test_7_ip_addresses_unchanged(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = quiet_sim(net, p)
        sim.start()
        seen = set()
        for _ in range(4000):
            sim.update(DT)
            seen.add((p.src_ip, p.dst_ip))
            if sim.state == "finished":
                break
        self.assertEqual(seen, {("192.168.1.10", "192.168.3.20")})

    def test_8_mac_addresses_change_per_link(self):
        net = build_demo_network()
        p = make_packet(net)
        run(quiet_sim(net, p))
        pairs = [(r["src_mac"], r["dst_mac"]) for r in p.trace]
        self.assertEqual(len(set(pairs)), len(pairs))
        path = p.route
        for rec, (a, b) in zip(p.trace, zip(path[1:], path[2:])):
            self.assertEqual(rec["src_mac"], net.nodes[a].iface_to(b).mac)
            self.assertEqual(rec["dst_mac"], net.nodes[b].iface_to(a).mac)

    def test_11_full_queue_tail_drop(self):
        r = Router("R", "R", (0, 0), queue_capacity=3)
        self.assertTrue(all(r.enqueue(i) for i in range(3)))
        self.assertFalse(r.enqueue("overflow"))
        self.assertEqual(len(r.queue), 3)
        self.assertEqual(r.dropped, 1)

    def test_11b_main_packet_dropped_by_congestion(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = quiet_sim(net, p)
        # fill GW-A's queue so the arriving packet is tail-dropped
        gw = net.nodes["GWA"]
        gw.service_rate = 0.001
        for i in range(gw.queue_capacity):
            gw.enqueue(f"bg{i}")
        run(sim)
        self.assertEqual(p.status, PacketStatus.DROPPED)
        self.assertIn("Queue overflow", p.drop_reason)

    def test_12_final_packet_not_processed_again(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = run(quiet_sim(net, p))
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        hops, delivered_at, scores = p.hops, p.delivered_at, list(sim.score_events)
        self.assertFalse(p.mark_delivered(999))
        self.assertFalse(p.mark_dropped("late"))
        for _ in range(600):
            sim.update(DT)
        self.assertEqual((p.hops, p.delivered_at, p.status), (hops, delivered_at, PacketStatus.DELIVERED))
        self.assertEqual(sim.score_events, scores)


class TestSimulationScenarios(unittest.TestCase):
    def test_reroute_after_link_failure(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = quiet_sim(net, p)
        sim.start()
        sim.fail_link(net.link_between("ISP1", "ISP4").id)
        for _ in range(4000):
            sim.update(DT)
            if sim.state == "finished":
                break
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        self.assertIn("ISP3", p.route)
        self.assertNotIn(("ISP1", "ISP4"), list(zip(p.route, p.route[1:])))

    def test_player_decision_wrong_then_right(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = SimulationEngine(net, p, random_events=False, background=False)
        sim.start()
        for _ in range(4000):
            sim.update(DT)
            if sim.state == "awaiting_decision":
                break
        self.assertEqual(sim.decision["router"], "ISPE")
        ok, msg = sim.choose_next_hop("ISP2")
        self.assertFalse(ok)
        ok, msg = sim.choose_next_hop("GWA")
        self.assertFalse(ok)
        self.assertIn("loop", msg)
        ok, _ = sim.choose_next_hop("ISP1")
        self.assertTrue(ok)
        run_rest = [sim.update(DT) for _ in range(4000) if sim.state != "finished"]
        self.assertEqual(p.status, PacketStatus.DELIVERED)

    def test_restore_cancels_pending_reroute(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = SimulationEngine(net, p, random_events=False, background=False)
        sim.start()
        for _ in range(4000):
            sim.update(DT)
            if sim.decision and sim.decision["router"] == "ISPE":
                sim.choose_next_hop(sim.decision["correct"])
                sim.fail_link(net.link_between("ISP1", "ISP4").id)   # fails while heading to ISP-1
            if sim.decision and sim.decision["kind"] == "reroute":
                break
        self.assertEqual(sim.decision["router"], "ISP1")
        sim.restore_all()
        self.assertIsNone(sim.decision)
        for _ in range(4000):
            sim.update(DT)
            if sim.state == "finished":
                break
        self.assertEqual(p.status, PacketStatus.DELIVERED)
        self.assertFalse(p.rerouted)
        self.assertIn("ISP4", p.route)

    def test_manual_failure_never_breaks_reachability(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = quiet_sim(net, p)
        sim.start()
        for _ in range(3):
            sim.fail_next_route_link()
        for _ in range(6000):
            sim.update(DT)
            if sim.state == "finished":
                break
        self.assertEqual(p.status, PacketStatus.DELIVERED)

    def test_seeded_runs_are_reproducible(self):
        def once():
            net = build_demo_network()
            p = make_packet(net)
            sim = run(SimulationEngine(net, p, seed=7, auto_decide=True), 120)
            return p.route, p.status, sim.bg_sent
        self.assertEqual(once(), once())

    def test_surge_causes_background_drops(self):
        net = build_demo_network()
        p = make_packet(net)
        sim = quiet_sim(net, p, background=True)
        sim.start()
        sim.surge("ISP3")
        sim.surge("ISP3")
        self.assertGreater(sim.bg_dropped, 0)
        self.assertLess(sim.health(), 100)


if __name__ == "__main__":
    unittest.main()
