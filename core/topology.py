"""Simple star-topology model: gateway at the center, everything else a leaf.

Without LLDP/CDP data (most consumer gear doesn't speak it), we can't know
the *real* physical wiring, so we approximate: every device is assumed to
be one hop from the default gateway. This is enough to get a useful,
readable picture on a typical home/small-office network.
"""

from __future__ import annotations

import logging

import networkx as nx
from scapy.all import conf

from core.device import Device

logger = logging.getLogger(__name__)


def detect_gateway_ip(interface: str | None = None) -> str | None:
    """Best-effort default gateway IP, read from the OS routing table via scapy."""
    try:
        iface = interface or conf.iface
        for net, mask, gw, dev, _addr, _metric in conf.route.routes:
            if net == 0 and mask == 0 and gw and gw != "0.0.0.0":
                if interface is None or dev == iface:
                    return gw
    except Exception:
        logger.debug("Gateway detection failed", exc_info=True)
    return None


def build_topology(devices: dict[str, Device], gateway_ip: str | None) -> nx.DiGraph:
    """Build a star graph: gateway_ip -> every other known device."""
    graph = nx.DiGraph()
    for ip in devices:
        graph.add_node(ip)
    if gateway_ip and gateway_ip in devices:
        for ip in devices:
            if ip != gateway_ip:
                graph.add_edge(gateway_ip, ip)
    return graph


def render_tree(graph: nx.DiGraph, devices: dict[str, Device], gateway_ip: str | None) -> str:
    """Render the topology as an indented ASCII tree for the TUI."""
    if not gateway_ip or gateway_ip not in devices:
        lines = ["Gateway not detected - showing flat device list:"]
        for ip in sorted(devices, key=lambda x: tuple(int(o) for o in x.split("."))):
            dev = devices[ip]
            lines.append(f"  - {dev.display_name} ({dev.ip})  {dev.status.value}")
        return "\n".join(lines)

    root = devices[gateway_ip]
    lines = [f"{root.display_name} ({root.ip})  [gateway]"]

    children = sorted(
        graph.successors(gateway_ip),
        key=lambda x: tuple(int(o) for o in x.split(".")),
    )
    for i, ip in enumerate(children):
        dev = devices[ip]
        branch = "└──" if i == len(children) - 1 else "├──"
        label = dev.display_name if dev.display_name != dev.ip else dev.ip
        lines.append(f"{branch} {label}  ({dev.ip})  {dev.status.value}")

    return "\n".join(lines)
