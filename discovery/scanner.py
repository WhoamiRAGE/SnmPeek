"""ARP-based host discovery on a local subnet.

Requires root/sudo privileges (raw sockets via scapy).
"""

from __future__ import annotations

import logging

from scapy.all import ARP, Ether, conf, get_if_addr, get_if_hwaddr, srp

from core.device import Device

logger = logging.getLogger(__name__)


def _lookup_vendor(mac: str) -> str | None:
    """Best-effort MAC OUI vendor lookup using scapy's bundled manuf database."""
    try:
        vendor = conf.manufdb._get_manuf(mac)
        # scapy returns the MAC itself back if it has no match
        if vendor and vendor.lower() != mac.lower():
            return vendor
    except Exception:
        logger.debug("Vendor lookup failed for %s", mac, exc_info=True)
    return None


def _get_local_device(interface: str | None) -> Device | None:
    """Return a Device for this host's own interface.

    A host generally doesn't reply to its own ARP broadcast, so arp_scan()
    misses itself. We fill that gap here by reading the IP/MAC directly
    off the interface instead of relying on a network round-trip.
    """
    iface = interface or conf.iface
    try:
        local_ip = get_if_addr(iface)
        local_mac = get_if_hwaddr(iface)
    except Exception:
        logger.debug("Could not read local interface %s", iface, exc_info=True)
        return None

    if not local_ip or local_ip == "0.0.0.0":
        return None

    device = Device(ip=local_ip, mac=local_mac, vendor=_lookup_vendor(local_mac))
    device.touch()
    return device


def arp_scan(subnet: str, interface: str | None = None, timeout: int = 2) -> list[Device]:
    """Send ARP requests to every host in `subnet` and return discovered devices.

    Args:
        subnet: CIDR notation, e.g. "192.168.1.0/24".
        interface: Network interface to send on. None lets scapy pick the
            default route interface.
        timeout: Seconds to wait for replies.

    Returns:
        List of Device objects for every host that replied, plus this host
        itself (which normally wouldn't answer its own ARP broadcast).
    """
    arp_request = ARP(pdst=subnet)
    broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request

    send_kwargs = {"timeout": timeout, "verbose": False}
    if interface:
        send_kwargs["iface"] = interface

    try:
        answered, _unanswered = srp(packet, **send_kwargs)
    except PermissionError as exc:
        raise PermissionError(
            "ARP scan requires root/sudo privileges (raw socket access)."
        ) from exc

    devices: list[Device] = []
    seen_ips: set[str] = set()
    for _sent, received in answered:
        ip = received.psrc
        mac = received.hwsrc
        device = Device(ip=ip, mac=mac, vendor=_lookup_vendor(mac))
        device.touch()
        devices.append(device)
        seen_ips.add(ip)

    local_device = _get_local_device(interface)
    if local_device and local_device.ip not in seen_ips:
        devices.append(local_device)

    logger.info("ARP scan of %s found %d device(s)", subnet, len(devices))
    return devices


if __name__ == "__main__":
    # Quick manual test: sudo python -m discovery.scanner
    import sys

    logging.basicConfig(level=logging.INFO)
    subnet_arg = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.0/24"
    found = arp_scan(subnet_arg)
    for d in found:
        print(f"{d.ip:15}  {d.mac:17}  {d.vendor or ''}")
