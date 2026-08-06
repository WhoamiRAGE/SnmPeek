"""Textual TUI for snmpeek: live device table driven by ARP scans."""

from __future__ import annotations

import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Static

from core.config import load_config
from core.device import Device
from discovery.scanner import arp_scan


class SnmpeekApp(App):
    """Main TUI application: scans the configured subnet and shows live results."""

    CSS = """
    #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("r", "rescan", "Rescan now"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config_path: str = "config.yaml") -> None:
        super().__init__()
        self.config = load_config(config_path)
        self.devices: dict[str, Device] = {}  # keyed by IP

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Starting up...", id="status")
        yield DataTable(id="device_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#device_table", DataTable)
        table.add_columns("IP", "MAC", "Vendor", "Status", "Last Seen")
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

        self._refresh_table()
        now = datetime.now().strftime("%H:%M:%S")
        status.update(f"Last scan: {now}  |  {len(self.devices)} device(s) known  |  subnet: {subnet}")

    def _refresh_table(self) -> None:
        table = self.query_one("#device_table", DataTable)
        table.clear()
        for device in sorted(self.devices.values(), key=lambda d: tuple(int(o) for o in d.ip.split("."))):
            table.add_row(
                device.ip,
                device.mac or "-",
                device.vendor or "-",
                device.status.value,
                device.last_seen.strftime("%H:%M:%S"),
            )


def run(config_path: str = "config.yaml") -> None:
    SnmpeekApp(config_path).run()


if __name__ == "__main__":
    run()
