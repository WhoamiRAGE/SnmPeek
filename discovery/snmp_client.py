"""SNMP (v2c) enrichment: pulls sysName/sysDescr and interface table from a device.

Uses pysnmp's synchronous hlapi. Devices that don't respond (SNMP disabled,
wrong community string, firewalled) simply return None / empty results -
this is expected for most consumer devices, so callers should treat it as
"not SNMP-managed" rather than an error.
"""

from __future__ import annotations

import logging

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    nextCmd,
)

from core.device import Interface

logger = logging.getLogger(__name__)

# IF-MIB OIDs for the interface table (indexed by ifIndex)
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"

_OPER_STATUS_MAP = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "not present", 7: "lower layer down"}


def get_sys_info(ip: str, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> dict | None:
    """Fetch sysName and sysDescr via SNMP GET. Returns None if the device didn't respond."""
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),  # mpModel=1 -> SNMPv2c
        UdpTransportTarget((ip, port), timeout=timeout, retries=retries),
        ContextData(),
        ObjectType(ObjectIdentity("SNMPv2-MIB", "sysName", 0)),
        ObjectType(ObjectIdentity("SNMPv2-MIB", "sysDescr", 0)),
    )

    try:
        error_indication, error_status, _error_index, var_binds = next(iterator)
    except Exception:
        logger.debug("SNMP sysinfo query failed for %s", ip, exc_info=True)
        return None

    if error_indication or error_status:
        # No response / wrong community / SNMP disabled - not an exceptional case
        return None

    sys_name, sys_descr = (str(vb[1]) for vb in var_binds)
    return {"sys_name": sys_name or None, "sys_descr": sys_descr or None}


def get_interfaces(ip: str, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> list[Interface]:
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
            for error_indication, error_status, _error_index, var_binds in nextCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                UdpTransportTarget((ip, port), timeout=timeout, retries=retries),
                ContextData(),
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False,
            ):
                if error_indication or error_status:
                    break
                for oid, value in var_binds:
                    if_index = str(oid).rsplit(".", 1)[-1]
                    sink[if_index] = value.prettyPrint()
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
