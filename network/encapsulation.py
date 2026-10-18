"""Encapsulation / decapsulation of the player's packet.

Each layer wraps the data from the layer above with its own header:

    Application data
    [TCP/UDP header | data]                         <- Transport  (segment / datagram)
    [IP header | TCP/UDP header | data]             <- Network    (packet)
    [Eth header | IP | TCP/UDP | data | FCS]        <- Data Link  (frame)
    0101 1100 ...                                   <- Physical   (bits on the medium)

The headers and the bitstream are EDUCATIONAL REPRESENTATIONS. The byte
layouts loosely follow the real formats (so the bitstream looks authentic),
but nothing is sent on a real network.
"""

from __future__ import annotations

import ipaddress
import struct
import zlib

from .models import PacketStatus

ORDER = ["transport", "network", "datalink", "physical"]

LAYER_INFO = {
    "application": ("L7", "Application", "Data"),
    "transport": ("L4", "Transport", "Segment"),
    "network": ("L3", "Network", "Packet"),
    "datalink": ("L2", "Data Link", "Frame"),
    "physical": ("L1", "Physical", "Bits"),
}

PROTO_NUMBERS = {"TCP": 6, "UDP": 17}


class EncapsulationError(Exception):
    pass


class Header:
    def __init__(self, layer, name, fields):
        self.layer = layer      # "transport" | "network" | "datalink"
        self.name = name        # "TCP", "UDP", "IPv4", "Ethernet"
        self.fields = fields    # list of (label, value) pairs for display

    def __repr__(self):
        return f"Header({self.name})"


def next_layer(packet):
    """Which layer should be applied next (None when fully encapsulated)."""
    done = [h.layer for h in packet.headers]
    if packet.on_wire:
        done.append("physical")
    for layer in ORDER:
        if layer not in done:
            return layer
    return None


def encapsulate(packet, layer, protocol=None, src_mac=None, dst_mac=None):
    """Apply one layer. Raises EncapsulationError if done out of order."""
    expected = next_layer(packet)
    if layer != expected:
        raise EncapsulationError(
            f"{LAYER_INFO[layer][1]} cannot be applied now; next is "
            f"{LAYER_INFO[expected][1] if expected else 'nothing (done)'}")

    if layer == "transport":
        if protocol not in ("TCP", "UDP"):
            raise EncapsulationError("Choose TCP or UDP")
        packet.protocol = protocol
        if protocol == "TCP":
            fields = [("Src port", str(packet.src_port)), ("Dst port", str(packet.dst_port)),
                      ("Seq", "1000"), ("Flags", "PSH, ACK"), ("Window", "64240")]
        else:
            fields = [("Src port", str(packet.src_port)), ("Dst port", str(packet.dst_port)),
                      ("Length", str(8 + len(packet.payload.encode()))), ("Checksum", "sim")]
        packet.headers.append(Header("transport", protocol, fields))

    elif layer == "network":
        packet.headers.append(Header("network", "IPv4", [
            ("Src IP", packet.src_ip), ("Dst IP", packet.dst_ip),
            ("TTL", "ttl"),  # live value, read from packet.ttl when displayed
            ("Protocol", f"{PROTO_NUMBERS[packet.protocol]} ({packet.protocol})"),
            ("Version", "4"),
        ]))

    elif layer == "datalink":
        if not src_mac or not dst_mac:
            raise EncapsulationError("Data Link layer needs source and next-hop MAC")
        packet.l2 = {"src_mac": src_mac, "dst_mac": dst_mac}
        packet.headers.append(Header("datalink", "Ethernet", [
            ("Src MAC", "l2src"), ("Dst MAC", "l2dst"),  # live values
            ("EtherType", "0x0800 (IPv4)"), ("FCS", "CRC-32 (trailer)"),
        ]))

    elif layer == "physical":
        packet.on_wire = True
        packet.status = PacketStatus.ENCAPSULATED
    return packet


def field_value(packet, value):
    """Resolve live placeholder values in header fields."""
    if value == "ttl":
        return str(packet.ttl)
    if value == "l2src":
        return packet.l2["src_mac"] or "-"
    if value == "l2dst":
        return packet.l2["dst_mac"] or "-"
    return value


def decapsulate(packet):
    """Remove the outermost header (destination host). Returns it.

    Order is the reverse of encapsulation: Ethernet -> IP -> TCP/UDP.
    When no headers remain the application data is exposed.
    """
    if packet.on_wire:
        packet.on_wire = False      # bits -> frame (receive from medium)
    if not packet.headers:
        raise EncapsulationError("Nothing left to decapsulate")
    return packet.headers.pop()


# ---------------------------------------------------------------------------
# Byte representation (for the bitstream animation only)
# ---------------------------------------------------------------------------
def _mac_bytes(mac):
    return bytes(int(x, 16) for x in (mac or "00:00:00:00:00:00").split(":"))


def _checksum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


def frame_bytes(packet):
    """Return [(segment_name, bytes), ...] in wire order."""
    data = packet.payload.encode("utf-8")
    layers = {h.layer for h in packet.headers}
    segments = []
    if "transport" in layers:
        if packet.protocol == "TCP":
            l4 = struct.pack("!HHLLBBHHH", packet.src_port, packet.dst_port, 1000, 0,
                             5 << 4, 0x18, 64240, 0, 0)
        else:
            l4 = struct.pack("!HHHH", packet.src_port, packet.dst_port, 8 + len(data), 0)
    else:
        l4 = b""
    if "network" in layers:
        total = 20 + len(l4) + len(data)
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, packet.id & 0xFFFF, 0,
                         max(packet.ttl, 0), PROTO_NUMBERS[packet.protocol], 0,
                         ipaddress.ip_address(packet.src_ip).packed,
                         ipaddress.ip_address(packet.dst_ip).packed)
        ip = ip[:10] + struct.pack("!H", _checksum(ip)) + ip[12:]
    else:
        ip = b""
    if "datalink" in layers:
        eth = _mac_bytes(packet.l2["dst_mac"]) + _mac_bytes(packet.l2["src_mac"]) + b"\x08\x00"
        segments.append(("eth", eth))
    if ip:
        segments.append(("ip", ip))
    if l4:
        segments.append(("l4", l4))
    segments.append(("data", data))
    if "datalink" in layers:
        body = b"".join(b for _, b in segments)
        segments.append(("fcs", struct.pack("!I", zlib.crc32(body) & 0xFFFFFFFF)))
    return segments


def bitstream(packet, max_bits=None):
    """[(segment_name, '0'/'1'), ...] - the simplified physical representation."""
    bits = []
    for name, chunk in frame_bytes(packet):
        for byte in chunk:
            for b in format(byte, "08b"):
                bits.append((name, b))
                if max_bits and len(bits) >= max_bits:
                    return bits
    return bits
