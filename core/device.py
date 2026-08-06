"""Core data model for a discovered network device."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DeviceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class Interface:
    """A single interface on a device, as seen via SNMP ifTable."""

    index: int
    name: str
    status: str = "unknown"       # up / down / unknown
    speed_mbps: int | None = None
    mac: str | None = None


@dataclass
class Device:
    """A device discovered on the network."""

    ip: str
    mac: str | None = None
    vendor: str | None = None          # from MAC OUI lookup
    hostname: str | None = None        # from SNMP sysName or reverse DNS
    sys_descr: str | None = None       # from SNMP sysDescr
    interfaces: list[Interface] = field(default_factory=list)
    neighbors: list[str] = field(default_factory=list)  # IPs of LLDP/CDP neighbors
    snmp_enabled: bool = False
    status: DeviceStatus = DeviceStatus.UNKNOWN
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def display_name(self) -> str:
        """Best available label for this device: hostname > vendor > ip."""
        if self.hostname:
            return self.hostname
        if self.vendor:
            return f"{self.vendor} ({self.ip})"
        return self.ip

    def touch(self) -> None:
        """Mark the device as seen right now and update status to UP."""
        self.last_seen = datetime.now()
        self.status = DeviceStatus.UP

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "mac": self.mac,
            "vendor": self.vendor,
            "hostname": self.hostname,
            "sys_descr": self.sys_descr,
            "snmp_enabled": self.snmp_enabled,
            "status": self.status.value,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "neighbors": self.neighbors,
        }
