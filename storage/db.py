"""SQLite persistence layer using SQLAlchemy Core.

Two tables:
- devices: latest known state per device (upserted on every scan)
- status_history: an append-only log of status transitions (up/down),
  written only when a device's status actually changes - this is what
  answers "when did this device go offline" later on.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from core.device import Device

metadata = MetaData()

devices_table = Table(
    "devices",
    metadata,
    Column("ip", String, primary_key=True),
    Column("mac", String),
    Column("vendor", String),
    Column("hostname", String),
    Column("sys_descr", String),
    Column("snmp_enabled", Integer),  # 0/1 - sqlite has no native bool
    Column("status", String),
    Column("first_seen", DateTime),
    Column("last_seen", DateTime),
)

status_history_table = Table(
    "status_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ip", String, index=True),
    Column("status", String),
    Column("timestamp", DateTime),
)


def init_db(db_path: str = "snmpeek.db") -> Engine:
    """Create the SQLite engine and ensure tables exist."""
    engine = create_engine(f"sqlite:///{db_path}")
    metadata.create_all(engine)
    return engine


def upsert_device(engine: Engine, device: Device) -> None:
    """Insert or update a device's latest state.

    If the device's status differs from what's stored (or it's new),
    a row is appended to status_history.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(devices_table.c.status).where(devices_table.c.ip == device.ip)
        ).first()

        status_changed = existing is None or existing.status != device.status.value

        if existing is None:
            conn.execute(
                insert(devices_table).values(
                    ip=device.ip,
                    mac=device.mac,
                    vendor=device.vendor,
                    hostname=device.hostname,
                    sys_descr=device.sys_descr,
                    snmp_enabled=int(device.snmp_enabled),
                    status=device.status.value,
                    first_seen=device.first_seen,
                    last_seen=device.last_seen,
                )
            )
        else:
            conn.execute(
                update(devices_table)
                .where(devices_table.c.ip == device.ip)
                .values(
                    mac=device.mac,
                    vendor=device.vendor,
                    hostname=device.hostname,
                    sys_descr=device.sys_descr,
                    snmp_enabled=int(device.snmp_enabled),
                    status=device.status.value,
                    last_seen=device.last_seen,
                )
            )

        if status_changed:
            conn.execute(
                insert(status_history_table).values(
                    ip=device.ip,
                    status=device.status.value,
                    timestamp=device.last_seen,
                )
            )


def get_history(engine: Engine, ip: str, limit: int = 50) -> list[dict]:
    """Return recent status_history rows for a device, newest first."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(status_history_table)
            .where(status_history_table.c.ip == ip)
            .order_by(status_history_table.c.timestamp.desc())
            .limit(limit)
        ).all()
    return [dict(row._mapping) for row in rows]


def get_all_known_ips(engine: Engine) -> list[str]:
    """Return every IP ever seen, including ones not found in the latest scan."""
    with engine.connect() as conn:
        rows = conn.execute(select(devices_table.c.ip)).all()
    return [row.ip for row in rows]
