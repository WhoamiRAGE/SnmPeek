# snmpeek

A terminal-based mini Network Management System (NMS) — the kind of tool a NOC engineer might reach for, built from scratch as a portfolio project.

Point it at a subnet and it does three things continuously in the background: **discovers** every live host with an ARP scan, **enriches** the SNMP-capable ones with system info, interface tables, and LLDP/CDP neighbor data, and **persists** everything to SQLite so status history survives restarts. All of it is rendered live in a keyboard-driven TUI: a sortable device table, a detail panel that updates as you move the cursor, an ASCII topology view, and one-key Excel export.

No external services, no agents to install on target devices (beyond enabling SNMP) — just a laptop, a subnet, and root access for raw sockets.

## Features

- **Discovery**: ARP scan (scapy) finds every live host on the configured subnet, including the local machine itself
- **SNMP enrichment**: pulls `sysName`, `sysDescr`, and the interface table (`ifDescr`, `ifOperStatus`, `ifSpeed`, `ifPhysAddress`) via `pysnmp`'s asyncio hlapi — supports both SNMPv2c (community string) and SNMPv3 (USM auth/privacy)
- **Topology view**: real edges from LLDP/CDP neighbor data when available (matched by hostname), falling back to a star graph from the default gateway otherwise — rendered as an ASCII tree, press `t` to toggle
- **Persistence**: every scan is upserted into SQLite; status transitions (up ↔ down) are logged to a history table
- **Alerting**: devices that stop responding to ARP are marked `down` and highlighted in red, with a live down-count in the status bar
- **Excel export**: dumps the current device table and full status history to a timestamped `.xlsx` (press `e`)
- **TUI**: Textual-based device table with a live-updating detail panel (interfaces, LLDP/CDP neighbors, recent status history) as you move the cursor

## Quick install

```bash
git clone https://github.com/WhoamiRAGE/snmpeek.git
cd snmpeek
./install.sh
```

This creates a virtual environment, installs dependencies, generates `config.yaml` from the example, and installs a `peek` launcher command to `~/.local/bin` — so you can start the app from anywhere with just `peek`, without typing out the venv path every time. If `~/.local/bin` isn't already on your `PATH`, the installer tells you exactly what to add.

Then edit `config.yaml` to match your subnet (see [Configuration](#configuration) below), and run:

```bash
peek
```

> ARP scanning requires root/sudo (raw socket access) — `peek` calls `sudo` internally, so it'll prompt for your password.

### Manual install

If you'd rather not run the script, or you're not on Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
sudo venv/bin/python cli.py
```

## Usage

| Key | Action |
|-----|--------|
| `r` | Rescan immediately |
| `t` | Toggle topology view |
| `e` | Export devices + status history to `.xlsx` |
| `↑`/`↓` | Move cursor / update detail panel |
| `q` | Quit |

## Configuration

Everything lives in `config.yaml` (copied from `config.example.yaml` on install). Key sections:

- `network.subnet` — CIDR range to scan, e.g. `192.168.1.0/24`
- `snmp.version` — `"2c"` (community string) or `"3"` (USM auth/privacy, see `snmp.v3.*`)
- `monitor.poll_interval` — seconds between automatic rescans
- `storage.db_path` — where the SQLite database is written

### Testing SNMP enrichment locally

Most consumer routers ship with SNMP disabled. To see enrichment in action without a managed switch, run an SNMP agent on your own machine:

```bash
# Arch/CachyOS example
sudo mkdir -p /etc/snmp
echo "rocommunity public default" | sudo tee /etc/snmp/snmpd.conf
sudo systemctl enable --now snmpd
```

Your own host should then show up in the device table with `SNMP: yes` after a rescan.

## Architecture

```
discovery/   ARP scanning (scapy), SNMP client (pysnmp), LLDP/CDP neighbor discovery
core/        Device data model, config loading, topology graph building
storage/     SQLite persistence (SQLAlchemy) and Excel export (openpyxl)
ui/          Textual TUI app
```

## Known limitations

- Down-detection is based on missing from a single ARP scan pass, no debounce/threshold yet — a device that briefly doesn't answer will flash red
- LLDP/CDP support is implemented but untested against real switches so far (developed and validated on a home network without managed gear) — expect edge cases on first real-world run

## Status

Actively in development. See [issues](https://github.com/WhoamiRAGE/snmpeek/issues).

## License

MIT — see [LICENSE](LICENSE).
