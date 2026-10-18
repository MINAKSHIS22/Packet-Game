"""Routing tests: Dijkstra, failures, unreachable destinations, tables."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network.routing import (dijkstra, lookup, path_cost, recompute_all_tables,
                             shortest_path)
from network.topology import build_demo_network


class TestDijkstra(unittest.TestCase):
    def setUp(self):
        self.net = build_demo_network()

    def test_1_lowest_cost_route(self):
        path, cost = shortest_path(self.net, "ALICE", "BOB")
        self.assertEqual(path, ["ALICE", "GWA", "ISPE", "ISP1", "ISP4", "EDGEB", "BOB"])
        self.assertEqual(cost, 10)
        self.assertEqual(path_cost(self.net, path), cost)

    def test_each_recipient_has_unique_shortest_path(self):
        expected = {
            "CHARLIE": ["ALICE", "GWA", "ISPE", "ISP1", "ISP3", "EDGEC", "CHARLIE"],
            "DIANA": ["ALICE", "GWA", "ISPE", "ISP2", "ISP5", "EDGED", "DIANA"],
        }
        for dst, exp in expected.items():
            path, _ = shortest_path(self.net, "ALICE", dst)
            self.assertEqual(path, exp)

    def test_2_alternative_route_after_failure(self):
        self.net.link_between("ISP1", "ISP4").active = False
        path, cost = shortest_path(self.net, "ALICE", "BOB")
        self.assertEqual(path, ["ALICE", "GWA", "ISPE", "ISP1", "ISP3", "ISP4", "EDGEB", "BOB"])
        self.assertEqual(cost, 11)
        for a, b in zip(path, path[1:]):
            self.assertTrue(self.net.link_between(a, b).active)

    def test_3_unreachable_destination(self):
        self.net.link_between("ISP4", "EDGEB").active = False
        path, cost = shortest_path(self.net, "ALICE", "BOB")
        self.assertIsNone(path)
        self.assertEqual(cost, float("inf"))
        recompute_all_tables(self.net)
        self.assertIsNone(lookup(self.net.nodes["ISPE"].routing_table, "192.168.3.20"))

    def test_hosts_do_not_forward(self):
        dist, prev = dijkstra(self.net, "BOB")
        self.assertEqual(prev["CHARLIE"], "EDGEC")

    def test_routing_table_and_longest_prefix_match(self):
        isp_e = self.net.nodes["ISPE"]
        self.assertEqual(lookup(isp_e.routing_table, "192.168.3.20").next_hop, "ISP1")
        self.assertEqual(lookup(isp_e.routing_table, "192.168.5.40").next_hop, "ISP2")
        gw = self.net.nodes["GWA"]
        self.assertEqual(lookup(gw.routing_table, "192.168.1.10").kind, "C")
        default = lookup(gw.routing_table, "192.168.3.20")
        self.assertEqual((default.kind, default.next_hop), ("S*", "ISPE"))

    def test_tables_update_after_failure(self):
        self.net.link_between("ISP1", "ISP4").active = False
        recompute_all_tables(self.net)
        self.assertEqual(lookup(self.net.nodes["ISP1"].routing_table, "192.168.3.20").next_hop, "ISP3")


if __name__ == "__main__":
    unittest.main()
