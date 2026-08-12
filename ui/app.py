"""Textual TUI for snmpeek: live device table driven by ARP scans."""

from __future__ import annotations

import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Static

from core.config import load_config
from core.device import Device
from core.topology import build_topology, detect_gateway_ip, render_tree
from discovery.scanner import arp_scan
from discovery.snmp_client import get_interfaces, get_sys_info
from storage.db import get_history, init_db, upsert_device


class SnmpeekApp(App):
    """Main TUI application: scans the configured subnet and shows live results."""

    CSS = """
    #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    #device_table {
        height: 1fr;
    }
    #detail {
        height: auto;
        max-height: 40%;
        border-top: solid $primary;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ("r", "rescan", "Rescan now"),
        ("t", "toggle_topology", "Topology"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config_path: str = "config.yaml") -> None:
        super().__init__()
        self.config = load_config(config_path)
        self.devices: dict[str, Device] = {}  # keyed by IP
        self.db = init_db(self.config["storage"]["db_path"])
        self.gateway_ip: str | None = None
        self.topology_mode: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Starting up...", id="status")
        yield DataTable(id="device_table")
        yield Static("Select a device to see details.", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#device_table", DataTable)
        table.add_columns("IP", "MAC", "Vendor", "Hostname", "SNMP", "Status", "Last Seen")
        table.cursor_type = "row"

        interval = self.config["monitor"]["poll_interval"]
        self.set_interval(interval, self.action_rescan)
        self.action_rescan()

    def action_rescan(self) -> None:
        self.run_worker(self._scan(), exclusive=True, group="scan")

    async def _scan(self) -> None:
        status = self.query_one("#status", Static)
        status.update("Scanning...")

        subnet = self.config["network"]["subnet"]
        interface = self.config["network"]["interface"]

        if self.gateway_ip is None:
            self.gateway_ip = await asyncio.to_thread(detect_gateway_ip, interface)

        try:
            found = await asyncio.to_thread(arp_scan, subnet, interface)
        except PermissionError:
            status.update(
                "[red]Permission denied - run with sudo (raw socket access needed)[/red]"
            )
            return
        except Exception as exc:  # noqa: BLE001 - surface any scan error in the UI
            status.update(f"[red]Scan failed: {exc}[/red]")
            return

        for device in found:
            self.devices[device.ip] = device

        if self.config["snmp"]["enabled"]:
            status.update(f"Scanned {len(found)} device(s), querying SNMP...")
            await asyncio.gather(*(self._enrich_snmp(device) for device in found))

        self._refresh_table()
        await asyncio.to_thread(self._persist_all)

        if self.topology_mode:
            self._show_topology()

        now = datetime.now().strftime("%H:%M:%S")
        status.update(f"Last scan: {now}  |  {len(self.devices)} device(s) known  |  subnet: {subnet}")

    async def _enrich_snmp(self, device: Device) -> None:
        """Best-effort SNMP query for a single device. Silently leaves it
        unenriched if there's no response (most consumer devices)."""
        snmp_cfg = self.config["snmp"]
        kwargs = dict(
            community=snmp_cfg["community"],
            port=snmp_cfg["port"],
            timeout=snmp_cfg["timeout"],
            retries=snmp_cfg["retries"],
        )
        try:
            sys_info = await get_sys_info(device.ip, **kwargs)
        except Exception:
            return

        if sys_info is None:
            return

        device.snmp_enabled = True
        device.hostname = sys_info.get("sys_name") or device.hostname
        device.sys_descr = sys_info.get("sys_descr")

        try:
            device.interfaces = await get_interfaces(device.ip, **kwargs)
        except Exception:
            device.interfaces = []

    def action_toggle_topology(self) -> None:
        self.topology_mode = not self.topology_mode
        if self.topology_mode:
            self._show_topology()
        else:
            self.query_one("#detail", Static).update("Select a device to see details.")

    def _show_topology(self) -> None:
        detail = self.query_one("#detail", Static)
        graph = build_topology(self.devices, self.gateway_ip)
        tree = render_tree(graph, self.devices, self.gateway_ip)
        detail.update(f"[b]Topology[/b] (press 't' to go back to device details)\n\n{tree}")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self.topology_mode or event.row_key.value is None:
            return
        self.run_worker(self._show_detail(str(event.row_key.value)), exclusive=True, group="detail")

    async def _show_detail(self, ip: str) -> None:
        device = self.devices.get(ip)
        detail = self.query_one("#detail", Static)
        if device is None:
            detail.update("Select a device to see details.")
            return

        lines = [f"[b]{device.display_name}[/b]  ({device.ip})  {device.mac or '-'}"]
        if device.vendor:
            lines.append(f"Vendor: {device.vendor}")
        if device.snmp_enabled:
            lines.append(f"SNMP: {device.sys_descr or '-'}")
            if device.interfaces:
                lines.append("Interfaces:")
                for iface in device.interfaces:
                    speed = f"{iface.speed_mbps} Mbps" if iface.speed_mbps else "-"
                    lines.append(f"  [{iface.index}] {iface.name}  {iface.status}  {speed}  {iface.mac or ''}")
        else:
            lines.append("SNMP: not responding / disabled")

        history = await asyncio.to_thread(get_history, self.db, ip, 5)
        if history:
            lines.append("Recent status changes:")
            for row in history:
                ts = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"  {ts}  ->  {row['status']}")

        detail.update("\n".join(lines))

    def _persist_all(self) -> None:
        for device in self.devices.values():
            upsert_device(self.db, device)

    def _refresh_table(self) -> None:
        table = self.query_one("#device_table", DataTable)
        table.clear()
        for device in sorted(self.devices.values(), key=lambda d: tuple(int(o) for o in d.ip.split("."))):
            table.add_row(
                device.ip,
                device.mac or "-",
                device.vendor or "-",
                device.hostname or "-",
                "yes" if device.snmp_enabled else "no",
                device.status.value,
                device.last_seen.strftime("%H:%M:%S"),
                key=device.ip,
            )


def run(config_path: str = "config.yaml") -> None:
    SnmpeekApp(config_path).run()


if __name__ == "__main__":
    run()
