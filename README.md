<<<<<<< HEAD
# Packet Panic — The Network Survival Game

A Computer Networks mini-project built with **Python 3 + Pygame**.
You play a network administrator who must get one message from Alice to Bob, Charlie or Diana: encapsulate it, send it to the default gateway, route it across an ISP backbone with Dijkstra's algorithm, survive link failures and congestion, and watch the destination host decapsulate it.

> **Honesty note:** this is a *discrete, educational simulation* of networking behaviour. It does not capture or send real packets, and the headers/bitstream are representations — not a production router or protocol stack.

---

## 1. Installation and running

Requires **Python 3.8+** (tested logic on 3.13). Works on Windows, macOS and Linux.

```bash
# 1. go into the project folder
cd packet_panic

# 2. (optional but recommended) create a virtual environment
python -m venv venv
# Windows:      venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

# 3. install the only dependency
pip install -r requirements.txt

# 4. run the game
python main.py
```

Shortcut: on Windows double-click `run_windows.bat`; on macOS/Linux run `./run_mac_linux.sh`. Both install Pygame and start the game.

Options:

```bash
python main.py              # fixed seed 42 -> identical random events every run (best for demos)
python main.py --seed 7     # a different, still reproducible run
python main.py --random     # new random events every mission
```

Run the tests (no Pygame window needed):

```bash
python -m unittest discover -s tests -v
```

On macOS/Linux use `python3` instead of `python` if needed.

---

## 2. Abstract

Packet Panic turns the journey of a single message through a network into an interactive game. The player creates application data, wraps it layer by layer (TCP/UDP → IP → Ethernet → bits), decides whether the destination is local or remote, picks next hops using routing-table and cost reasoning, and reacts to link failures and congested router queues. The destination host finally strips the headers in reverse order and reveals the original message, followed by a delivery report (route, hops, TTL, latency, reroutes).

## 3. Problem statement

Encapsulation, routing, TTL and congestion are usually taught as static diagrams, so students rarely *see* how the same packet keeps its IP addresses while its MAC addresses change at every hop, or how a routing protocol recovers from a failed link. This project makes those mechanisms visible and interactive.

## 4. Objectives

- Visualise encapsulation and decapsulation across the OSI/TCP-IP layers.
- Show local vs remote delivery, the default gateway and ARP.
- Implement Dijkstra's shortest-path algorithm and derive routing tables from it.
- Simulate per-router forwarding: TTL decrement, hop counting, MAC rewriting.
- Demonstrate link failure + rerouting and queue congestion + tail-drop loss.
- Keep the code small and explainable for a viva.

## 5. Technologies

| Item | Use |
|---|---|
| Python 3 | all logic |
| Pygame | window, drawing, input |
| `heapq`, `ipaddress`, `struct`, `zlib`, `random` (stdlib) | Dijkstra priority queue, subnet maths / longest-prefix match, byte layouts, CRC-32 FCS, seeded events |
| `unittest` (stdlib) | tests |

No database, internet connection, external API or asset files are needed.

---

## 6. System architecture

```
packet_panic/
├── main.py                  entry point (argument parsing)
├── requirements.txt
├── network/                 PURE PYTHON - no Pygame, fully unit-tested
│   ├── models.py            Host, Router, Link, Interface, Network, Packet
│   ├── topology.py          the fixed demo topology (14 nodes, 18 links)
│   ├── routing.py           Dijkstra, routing tables, longest-prefix match
│   ├── encapsulation.py     headers, encapsulate/decapsulate, bitstream
│   └── simulation.py        SimulationEngine: forwarding, TTL, queues, failures
├── game/                    Pygame user interface
│   ├── settings.py          design system: layout grid, colours, type scale
│   ├── ui.py                Button, TextInput, Toasts, drawing helpers
│   ├── widgets.py           packet bar / nested stack / header field views
│   ├── core.py              Session (shared state, score) + Scene base class
│   ├── game.py              Game loop, scene switching, scaling, top bar, pause
│   ├── scenes_setup.py      Title, Compose, Encapsulation, Gateway scenes
│   └── scenes_network.py    Routing, Decapsulation, Report scenes
└── tests/
    ├── test_routing.py
    └── test_packet.py
```

**Separation of concerns.** The `network` package knows nothing about Pygame. The UI only *reads* simulation state when drawing; only `SimulationEngine.update()` changes TTL, queues or link state. The game loop uses a **fixed time step** (1/60 s), so behaviour is identical at any frame rate.

**Scene flow:** Title → Compose → Encapsulate → Gateway → Routing (stages 4–7) → Decapsulation → Report (→ Retransmit on loss).

---

## 7. Data structures and algorithms

| Concept | Implementation |
|---|---|
| Topology | **Adjacency list**: `Network.adj[node_id] -> [Link, ...]` |
| Link | endpoints, `cost` (routing metric), `delay_ms`, `bandwidth_mbps`, `active` |
| Router | id, screen position, interfaces (name/MAC/IP per neighbour), routing table, **bounded FIFO queue** (`deque`, capacity 8), service rate 4 pkt/s |
| Packet | id, src/dst host + IP, payload, protocol + ports, header stack, L2 header, TTL, hops, current node, route, next hop, creation time, status, drop reason |
| Shortest path | **Dijkstra** with a min-heap (`heapq`) — `routing.dijkstra()` |
| Route lookup | **Longest-prefix match** over the routing table — `routing.lookup()` |
| Queue policy | **Tail drop**: arriving packet is discarded when the queue is full |

### Dijkstra (`network/routing.py`)

```
dist[source] = 0, all others = infinity
heap = [(0, source)]
while heap not empty:
    d, u = pop smallest
    skip if u already visited; mark visited
    for each ACTIVE link (u, v):
        if d + cost < dist[v]: dist[v] = d + cost, prev[v] = u, push (dist[v], v)
path = follow prev[] back from destination
```
Complexity: O((V + E) log V). Hosts are end systems and never used as transit nodes.

**Routing tables** are built per router from its own Dijkstra tree (link-state style, like OSPF): for every remote LAN, the *next hop* is the first node on the shortest path. The customer gateway GW-A uses a **default route** `0.0.0.0/0 → ISP-E`. When any link changes state, all tables are recomputed instantly (real networks need convergence time — a stated simplification).

### Demo topology and costs

| Link | Cost | Link | Cost |
|---|---|---|---|
| Alice-PC – GW-A (LAN 192.168.1.0/24) | 1 | ISP-2 – ISP-5 | 3 |
| GW-A – ISP-E (customer uplink) | 2 | ISP-3 – ISP-4 | 2 |
| ISP-E – ISP-1 | 2 | ISP-3 – ISP-5 | 3 |
| ISP-E – ISP-2 | 3 | ISP-3 – EDGE-C | 3 |
| ISP-1 – ISP-3 | 2 | ISP-4 – EDGE-B | 1 |
| ISP-2 – ISP-3 | 2 | ISP-4 – EDGE-C | 4 |
| ISP-1 – ISP-4 | 3 | ISP-5 – EDGE-C | 2 |
| EDGE-B – Bob-PC (192.168.3.0/24) | 1 | ISP-5 – EDGE-D | 1 |
| EDGE-C – Charlie-PC (192.168.4.0/24) | 1 | EDGE-D – Diana-PC (192.168.5.0/24) | 1 |

Router-to-router links use `10.0.N.0/30` addresses; MACs follow `02:50:50:00:<node>:<interface>`.
Shortest paths (unique by design):
- Bob: Alice → GW-A → ISP-E → ISP-1 → ISP-4 → EDGE-B → Bob (cost 10)
- Charlie: … ISP-E → ISP-1 → ISP-3 → EDGE-C → Charlie (cost 11)
- Diana: … ISP-E → ISP-2 → ISP-5 → EDGE-D → Diana (cost 11)

Every backbone link has an alternative, so a failure never makes the demo impossible.

---

## 8. OSI layer mapping

| OSI layer | In the game | PDU |
|---|---|---|
| L7 Application | the PacketChat message | data |
| L6 Presentation | shown conceptually (UTF-8 text encoding) — no fake encryption | — |
| L5 Session | shown conceptually (dialogue handled by app/TCP) | — |
| L4 Transport | TCP or UDP header, ports 49152 → 5000 | segment / datagram |
| L3 Network | IPv4 header: src/dst IP, TTL, protocol | packet |
| L2 Data Link | Ethernet header (src/dst MAC, EtherType) + FCS trailer | frame |
| L1 Physical | animated bitstream | bits |

## 9. Encapsulation and decapsulation

**Encapsulation** adds protocol information *around* the data, top-down: the transport header wraps the data, the IP header wraps the segment, the Ethernet header/trailer wraps the packet, and the frame is sent as bits. The game enforces this order (wrong order is rejected with an explanation). At L2, the destination MAC is the **default gateway's** MAC, not Bob's.

**Decapsulation** at the destination host is the reverse: Ethernet (check dst MAC + FCS, EtherType → IPv4) → IP (dst IP is mine, protocol → TCP/UDP) → TCP/UDP (dst port → application) → data. The original message appears only after all headers are removed.

**Routers do not decapsulate the application data.** Each router receives the frame (L1/L2), reads the IP header (L3), decrements TTL, and builds a **new frame** for the next link.

## 10. TTL and hop count

- **TTL** starts at the value chosen on the compose screen (default **8**). Each router that forwards the packet decrements it by 1. If it reaches 0, the router discards the packet (a real router would send ICMP Time Exceeded). TTL never goes negative.
- **Hop count** is tracked separately and counts **links traversed, including the final link into the destination host**.
- Example to Bob: 5 routers forward → TTL 8 → 3; 6 links traversed → hop count 6.
- Set TTL = 3 to see the packet expire at ISP-1.
- IP source/destination never change; MAC source/destination are rewritten on every link (the packet inspector shows both).

## 11. Link failure and rerouting

- **F** (or the *Fail route link* button) fails the next backbone link on the packet's remaining route that still leaves an alternative path — reliable for demos.
- **Clicking any link** toggles it down/up (this can make a destination unreachable, which is also a teachable case). **R** restores all links.
- **Random events** (toggle **E**) may fail one safe link per journey, with a cooldown, using a **seeded** RNG (default seed 42) so demos are reproducible.
- After a failure all routing tables are recomputed with Dijkstra. When the packet reaches a router whose next hop changed, the game pauses and the player must pick the new lowest-cost next hop.

## 12. Congestion and packet loss

- Every router has a bounded FIFO queue (capacity 8) and forwards 4 packets per simulated second.
- Background traffic from other customers (grey dots) loads the core routers; it never replaces the player's packet.
- **S** triggers a *traffic surge* at the selected router (click it first) or the next router on the route: queues overflow, **tail drop** discards packets, a congestion warning appears, routers turn amber/red and loss statistics update.
- If the player's packet arrives at a full queue it is dropped with the reason recorded; the report offers **Retransmit** (what TCP would do after a timeout; UDP would not).
- Congestion (full buffers) is kept separate from link failure (link down).

## 13. Scoring

| Event | Points |
|---|---|
| Each encapsulation layer applied | +5 |
| Correct local/remote decision | +25 (+10 after a wrong try) |
| Correct next hop / reroute | +25 (+10 after a wrong try) |
| Wrong answer | −5 (wrong layer order −2) |
| Message delivered | +100 |
| Delivered despite a link failure | +50 |
| Player's packet lost | −50 |
| Background packet lost | −1 each (max −20) |

**Network health** (top bar) falls with failed links, queue occupancy and recent drops. You win by delivering the message with health ≥ 50%.

---

## 14. Controls

| Key / action | Effect |
|---|---|
| Mouse | click buttons, drag the packet, click links/routers |
| Enter | primary action (Play, Send to gateway, Report…) |
| Ctrl+Enter | send message (compose screen) |
| Tab / ← → | switch input field / recipient |
| Space | encapsulation: drop into next layer · decapsulation: next layer |
| T / U | choose TCP / UDP |
| 1 – 4 | choose an answer / next-hop option |
| F / S / R | fail route link / traffic surge / restore links |
| X | simulation speed 1x / 2x |
| E | random events on/off |
| A | auto-play decapsulation |
| Esc or P | pause (resume / restart with confirmation / main menu) |
| H | how to play (title screen) |

The window is resizable; the 1280×720 layout scales with letterboxing.

---

## 15. Test cases

`python -m unittest discover -s tests -v` — 24 tests, all passing:

| # | Requirement | Test |
|---|---|---|
| 1 | Dijkstra picks the lowest-cost route | `test_1_lowest_cost_route`, `test_each_recipient_has_unique_shortest_path` |
| 2 | Alternative route after a link fails | `test_2_alternative_route_after_failure`, `test_reroute_after_link_failure` |
| 3 | Unreachable destination detected | `test_3_unreachable_destination` |
| 4 | TTL decreases once per router | `test_4_ttl_decrements_once_per_router` |
| 5 | TTL expiry drops the packet | `test_5_ttl_expiry_drops_packet` |
| 6 | Hop count independent of TTL | `test_6_hops_independent_of_ttl` |
| 7 | IP src/dst unchanged while forwarding | `test_7_ip_addresses_unchanged` |
| 8 | MAC addresses change per link | `test_8_mac_addresses_change_per_link` |
| 9 | Encapsulation order | `test_9_headers_added_in_order`, `test_out_of_order_rejected` |
| 10 | Decapsulation reverse order | `test_10_decapsulation_reverse_order` |
| 11 | Full queue → drop | `test_11_full_queue_tail_drop`, `test_11b_main_packet_dropped_by_congestion` |
| 12 | Delivered/dropped packet not processed again | `test_12_final_packet_not_processed_again` |
| – | extras | routing tables + longest prefix match, tables update after failure, player decision flow, safe manual failures, seeded reproducibility, surge drops |

---

## 16. Limitations and future improvements

- Routing tables reconverge instantly; real OSPF/RIP take time and can loop briefly.
- One player packet at a time; no real TCP handshake, windows or retransmission timers (retransmission is a button).
- Background traffic wanders randomly instead of following real flows.
- Link costs are static; routing does not react to congestion (true of plain OSPF too).
- No NAT, VLANs, IPv6, ICMP messages or real ARP caching.
- Future: multiple simultaneous packets, distance-vector (Bellman–Ford) mode for comparison, TCP congestion window visualisation, sound effects, editable topologies, packet-capture-style export.

---

## 17. Suggested viva questions

**Q: What is encapsulation?**
Each layer adds its own header (and L2 adds a trailer) around the data from the layer above so that layer's job can be done: ports at L4, IP addresses at L3, MAC addresses at L2.

**Q: Why does the destination MAC in Alice's frame belong to GW-A and not Bob?**
Bob is on another network. MAC addresses only work on the local link, so Alice sends the frame to the next hop — her default gateway — found with ARP.

**Q: How does Alice know Bob is remote?**
She ANDs both IPs with her mask 255.255.255.0: 192.168.1.0 ≠ 192.168.3.0, so the destination is off-subnet.

**Q: What changes and what stays the same at each router?**
IP source/destination stay the same; TTL decreases by 1; a new Ethernet frame is built with new source/destination MACs for the outgoing link.

**Q: Explain Dijkstra's algorithm. Complexity?**
Greedy shortest-path: repeatedly finalise the closest unvisited node and relax its edges. With a binary heap O((V+E) log V). It requires non-negative edge costs.

**Q: How do the routing tables relate to Dijkstra?**
Each router runs Dijkstra from itself; for every destination network, the next hop is the first node on its shortest path (link-state routing, as in OSPF).

**Q: What is longest-prefix match?**
When several entries match a destination, the router uses the most specific (longest mask). E.g. GW-A uses its /24 connected route for local traffic and the /0 default route for everything else.

**Q: Why does TTL exist?**
To stop packets circulating forever in routing loops. At 0 the packet is discarded and ICMP Time Exceeded is sent (traceroute uses this).

**Q: Difference between hop count and TTL here?**
TTL is a header field decremented only by routers; hop count is our statistic of links traversed, including the last link into the destination host — so to Bob hops = 6 while TTL drops by 5.

**Q: What happens on a link failure?**
The link is marked down, tables are recomputed, and the next router whose best next hop changed forwards along the new shortest path (the player confirms it).

**Q: Congestion vs link failure?**
Congestion: the link works but a router's queue is full, so tail drop discards arriving packets. Failure: the link itself is down. Different causes, different fixes.

**Q: TCP vs UDP?**
TCP is connection-oriented and reliable (handshake, sequence numbers, ACKs, retransmission). UDP is connectionless, with an 8-byte header and no delivery guarantee.

**Q: Do routers read the message?**
No. Routers work at L1–L3. Only the destination host goes up to the application layer.

**Q: Is this real networking?**
No — it's a discrete simulation. Headers and bits are educational representations; nothing is sent on a real network.
=======
# Packet-Game
>>>>>>> dc3eaff830df5424bbd41d4ec07219d7a29aec59
