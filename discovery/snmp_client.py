"""SNMP (v2c) enrichment: pulls sysName/sysDescr and interface table from a device.

Uses pysnmp's modern asyncio-based hlapi (pysnmp >= 7, maintained by Lextudio).
The old synchronous generator-based hlapi relied on the `asyncore` module,
which was removed from the Python standard library in 3.12+ - so this is the
only API surface that still works on current Python versions.

Devices that don't respond (SNMP disabled, wrong community string,
firewalled) simply return None / empty results - this is expected for most
consumer devices, so callers should treat it as "not SNMP-managed" rather
than an error.
"""

from __future__ import annotations

import logging

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    walk_cmd,
)

from core.device import Interface

logger = logging.getLogger(__name__)

# IF-MIB OIDs for the interface table (indexed by ifIndex)
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"

_OPER_STATUS_MAP = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "not present", 7: "lower layer down"}


async def get_sys_info(ip: str, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> dict | None:
    """Fetch sysName and sysDescr via SNMP GET. Returns None if the device didn't respond."""
    try:
        engine = SnmpEngine()
        target = await UdpTransportTarget.create((ip, port), timeout=timeout, retries=retries)
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            engine,
            CommunityData(community, mpModel=1),  # mpModel=1 -> SNMPv2c
            target,
            ContextData(),
            ObjectType(ObjectIdentity("SNMPv2-MIB", "sysName", 0)),
            ObjectType(ObjectIdentity("SNMPv2-MIB", "sysDescr", 0)),
        )
        engine.close_dispatcher()
    except Exception:
        logger.debug("SNMP sysinfo query failed for %s", ip, exc_info=True)
        return None

    if error_indication or error_status:
        # No response / wrong community / SNMP disabled - not an exceptional case
        return None

    sys_name, sys_descr = (str(vb[1]) for vb in var_binds)
    return {"sys_name": sys_name or None, "sys_descr": sys_descr or None}


async def get_interfaces(ip: str, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> list[Interface]:
    """Walk the IF-MIB interface table and return a list of Interface objects."""
    descrs: dict[str, str] = {}
    statuses: dict[str, str] = {}
    speeds: dict[str, int] = {}
    macs: dict[str, str] = {}

    for base_oid, sink in (
        (IF_DESCR, descrs),
        (IF_OPER_STATUS, statuses),
        (IF_SPEED, speeds),
        (IF_PHYS_ADDRESS, macs),
    ):
        try:
            engine = SnmpEngine()
            target = await UdpTransportTarget.create((ip, port), timeout=timeout, retries=retries)
            async for error_indication, error_status, _error_index, var_binds in walk_cmd(
                engine,
                CommunityData(community, mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False,
            ):
                if error_indication or error_status:
                    break
                for oid, value in var_binds:
                    if_index = str(oid).rsplit(".", 1)[-1]
                    sink[if_index] = value.prettyPrint()
            engine.close_dispatcher()
        except Exception:
            logger.debug("SNMP ifTable walk failed for %s (oid=%s)", ip, base_oid, exc_info=True)
            return []

    interfaces = []
    for if_index, name in descrs.items():
        raw_status = statuses.get(if_index)
        status = _OPER_STATUS_MAP.get(int(raw_status), "unknown") if raw_status and raw_status.isdigit() else "unknown"
        raw_speed = speeds.get(if_index)
        speed_mbps = int(raw_speed) // 1_000_000 if raw_speed and raw_speed.isdigit() else None
        interfaces.append(
            Interface(
                index=int(if_index),
                name=name,
                status=status,
                speed_mbps=speed_mbps,
                mac=macs.get(if_index),
            )
        )

    return sorted(interfaces, key=lambda i: i.index)
