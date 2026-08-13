"""SNMP enrichment: pulls sysName/sysDescr, interface table, and LLDP/CDP
neighbors from a device. Supports both SNMPv2c (community string) and
SNMPv3 (username + optional auth/privacy).

Uses pysnmp's modern asyncio-based hlapi (pysnmp >= 7, maintained by Lextudio).
The old synchronous generator-based hlapi relied on the `asyncore` module,
which was removed from the Python standard library in 3.12+ - so this is the
only API surface that still works on current Python versions.

Devices that don't respond (SNMP disabled, wrong credentials, firewalled)
simply return None / empty results - this is expected for most consumer
devices, so callers should treat it as "not SNMP-managed" rather than an
error.
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
    UsmUserData,
    get_cmd,
    usmAesCfb128Protocol,
    usmDESPrivProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
    walk_cmd,
)

from core.device import Interface

logger = logging.getLogger(__name__)

# IF-MIB OIDs for the interface table (indexed by ifIndex)
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"

# LLDP-MIB (standard, vendor-neutral) and CISCO-CDP-MIB (Cisco-specific)
# OIDs for neighbor discovery. Not supported by consumer routers, but common
# on managed switches/routers in enterprise or lab environments.
LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
CDP_CACHE_DEVICE_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"

_OPER_STATUS_MAP = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "not present", 7: "lower layer down"}

_AUTH_PROTOCOLS = {
    "none": usmNoAuthProtocol,
    "md5": usmHMACMD5AuthProtocol,
    "sha": usmHMACSHAAuthProtocol,
}
_PRIV_PROTOCOLS = {
    "none": usmNoPrivProtocol,
    "des": usmDESPrivProtocol,
    "aes128": usmAesCfb128Protocol,
}


def build_auth(snmp_cfg: dict):
    """Build the pysnmp auth object for either v2c or v3, from config.yaml's
    snmp section.

    v2c (default): CommunityData from `community`.
    v3: UsmUserData from `v3.username` (+ optional auth/priv key & protocol).
        Falls back to noAuthNoPriv if no auth_key is set.
    """
    if snmp_cfg.get("version") != "3":
        return CommunityData(snmp_cfg.get("community", "public"), mpModel=1)  # SNMPv2c

    v3_cfg = snmp_cfg.get("v3", {}) or {}
    username = v3_cfg.get("username", "")
    auth_key = v3_cfg.get("auth_key") or None
    priv_key = v3_cfg.get("priv_key") or None
    auth_protocol = _AUTH_PROTOCOLS.get(v3_cfg.get("auth_protocol", "sha"), usmHMACSHAAuthProtocol)
    priv_protocol = _PRIV_PROTOCOLS.get(v3_cfg.get("priv_protocol", "aes128"), usmAesCfb128Protocol)

    return UsmUserData(
        username,
        authKey=auth_key,
        privKey=priv_key,
        authProtocol=auth_protocol if auth_key else usmNoAuthProtocol,
        privProtocol=priv_protocol if priv_key else usmNoPrivProtocol,
    )


async def _walk_column(ip: str, base_oid: str, auth_data, port: int, timeout: int, retries: int) -> dict[str, str]:
    """Walk a single SNMP table column, returning {index: value} keyed by the
    trailing OID index (e.g. ifIndex, lldpRemIndex)."""
    result: dict[str, str] = {}
    try:
        engine = SnmpEngine()
        target = await UdpTransportTarget.create((ip, port), timeout=timeout, retries=retries)
        async for error_indication, error_status, _error_index, var_binds in walk_cmd(
            engine,
            auth_data,
            target,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication or error_status:
                break
            for oid, value in var_binds:
                index = str(oid).rsplit(".", 1)[-1]
                result[index] = value.prettyPrint()
        engine.close_dispatcher()
    except Exception:
        logger.debug("SNMP walk failed for %s (oid=%s)", ip, base_oid, exc_info=True)
    return result


async def get_sys_info(ip: str, auth_data=None, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> dict | None:
    """Fetch sysName and sysDescr via SNMP GET. Returns None if the device didn't respond.

    Pass `auth_data` (from build_auth()) for v3, or leave it None to fall
    back to v2c with `community` (kept for backward compatibility / simple
    scripts).
    """
    if auth_data is None:
        auth_data = CommunityData(community, mpModel=1)

    try:
        engine = SnmpEngine()
        target = await UdpTransportTarget.create((ip, port), timeout=timeout, retries=retries)
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            engine,
            auth_data,
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
        # No response / bad credentials / SNMP disabled - not an exceptional case
        return None

    sys_name, sys_descr = (str(vb[1]) for vb in var_binds)
    return {"sys_name": sys_name or None, "sys_descr": sys_descr or None}


async def get_interfaces(ip: str, auth_data=None, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> list[Interface]:
    """Walk the IF-MIB interface table and return a list of Interface objects."""
    if auth_data is None:
        auth_data = CommunityData(community, mpModel=1)
    kwargs = dict(auth_data=auth_data, port=port, timeout=timeout, retries=retries)

    descrs = await _walk_column(ip, IF_DESCR, **kwargs)
    if not descrs:
        return []
    statuses = await _walk_column(ip, IF_OPER_STATUS, **kwargs)
    speeds = await _walk_column(ip, IF_SPEED, **kwargs)
    macs = await _walk_column(ip, IF_PHYS_ADDRESS, **kwargs)

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


async def get_neighbors(ip: str, auth_data=None, community: str = "public", port: int = 161, timeout: int = 1, retries: int = 1) -> list[str]:
    """Return neighbor device names/IDs via LLDP (preferred) or CDP.

    Returns an empty list if the device doesn't support either (true for
    almost all consumer gear) or has no neighbors reported.
    """
    if auth_data is None:
        auth_data = CommunityData(community, mpModel=1)
    kwargs = dict(auth_data=auth_data, port=port, timeout=timeout, retries=retries)

    lldp_neighbors = await _walk_column(ip, LLDP_REM_SYS_NAME, **kwargs)
    if lldp_neighbors:
        return sorted(set(lldp_neighbors.values()))

    cdp_neighbors = await _walk_column(ip, CDP_CACHE_DEVICE_ID, **kwargs)
    if cdp_neighbors:
        return sorted(set(cdp_neighbors.values()))

    return []
