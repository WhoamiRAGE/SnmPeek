"""Topology model: real edges from LLDP/CDP when available, otherwise a
star-graph approximation from the default gateway.

Most consumer gear doesn't speak LLDP/CDP, so the star fallback is what
you'll see on a typical home network - it's still useful (one hop from
the gateway is usually right), just not verified physical wiring. On
managed switches/routers that do report neighbors, real edges are used
and the star fallback is skipped entirely.
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


def _label(dev: Device) -> str:
    return dev.hostname or dev.vendor or dev.ip


def build_topology(devices: dict[str, Device], gateway_ip: str | None) -> nx.DiGraph:
    """Build the topology graph.

    Prefers real LLDP/CDP-reported neighbor edges (device.neighbors, matched
    by hostname). If no device reported any neighbors, falls back to a star
    graph rooted at gateway_ip.
    """
    graph = nx.DiGraph()
    for ip in devices:
        graph.add_node(ip)

    name_to_ip = {dev.hostname.lower(): ip for ip, dev in devices.items() if dev.hostname}

    real_edges = False
    for ip, dev in devices.items():
        for neighbor_name in dev.neighbors:
            neighbor_ip = name_to_ip.get(neighbor_name.lower())
            if neighbor_ip and neighbor_ip != ip:
                graph.add_edge(ip, neighbor_ip)
                real_edges = True

    if not real_edges and gateway_ip and gateway_ip in devices:
        for ip in devices:
            if ip != gateway_ip:
                graph.add_edge(gateway_ip, ip)

    return graph


def render_tree(graph: nx.DiGraph, devices: dict[str, Device], gateway_ip: str | None) -> str:
    """Render the topology as an indented ASCII tree for the TUI."""
    if graph.number_of_edges() == 0:
        lines = ["No topology data yet - showing flat device list:"]
        for ip in sorted(devices, key=lambda x: tuple(int(o) for o in x.split("."))):
            dev = devices[ip]
            lines.append(f"  - {_label(dev)} ({dev.ip})  {dev.status.value}")
        return "\n".join(lines)

    root = gateway_ip if gateway_ip in graph.nodes else next(iter(graph.nodes))
    root_dev = devices[root]
    root_tag = "  [gateway]" if root == gateway_ip else ""
    lines = [f"{_label(root_dev)} ({root_dev.ip}){root_tag}"]

    visited = {root}

    def walk(node: str, prefix: str) -> None:
        children = sorted(
            (n for n in graph.successors(node) if n not in visited),
            key=lambda x: tuple(int(o) for o in x.split(".")),
        )
        for i, child in enumerate(children):
            visited.add(child)
            is_last = i == len(children) - 1
            branch = "└── " if is_last else "├── "
            dev = devices[child]
            lines.append(f"{prefix}{branch}{_label(dev)}  ({dev.ip})  {dev.status.value}")
            walk(child, prefix + ("    " if is_last else "│   "))

    walk(root, "")
    return "\n".join(lines)
