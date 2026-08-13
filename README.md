# snmpeek

Terminal-based mini Network Management System (NMS). Discovers hosts on the local network via ARP scan, enriches SNMP-capable devices with additional data (sysName, sysDescr, interface table), tracks status history in SQLite, and renders it all live in a Textual-based TUI — device table, per-device detail panel, and a topology view.


## Features

- **Discovery**: ARP scan (scapy) finds every live host on the configured subnet, including the local machine itself
- **SNMP enrichment**: pulls `sysName`, `sysDescr`, and the interface table (`ifDescr`, `ifOperStatus`, `ifSpeed`, `ifPhysAddress`) via `pysnmp`'s asyncio hlapi - supports both SNMPv2c (community string) and SNMPv3 (USM auth/privacy)
- **Persistence**: every scan is upserted into SQLite; status transitions (up ↔ down) are logged to a history table
- **Topology view**: real edges from LLDP/CDP neighbor data when available (matched by hostname), falling back to a star graph from the default gateway otherwise — rendered as an ASCII tree, press `t` to toggle
- **Alerting**: devices that stop responding to ARP are marked `down` and highlighted in red, with a live down-count in the status bar
- **Excel export**: dumps the current device table and full status history to a timestamped `.xlsx` (press `e`)
- **TUI**: Textual-based device table with a live-updating detail panel (interfaces + recent status history) as you move the cursor

## Installation

```bash
git clone https://github.com/WhoamiRAGE/snmpeek.git
cd snmpeek
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml to match your subnet
```

> ARP scanning requires root/sudo (raw socket access).

## Usage

```bash
sudo venv/bin/python cli.py
```

| Key | Action |
|-----|--------|
| `r` | Rescan immediately |
| `t` | Toggle topology view |
| `e` | Export devices + status history to `.xlsx` |
| `↑`/`↓` | Move cursor / update detail panel |
| `q` | Quit |

Subnet, poll interval, SNMP community string, and DB path are all read from `config.yaml` (see `config.example.yaml` for the full list of options).

### Testing SNMP enrichment locally

Most consumer routers ship with SNMP disabled. To see enrichment in action without a managed switch, run an SNMP agent on your own machine:

```bash
# Arch/CachyOS example
sudo mkdir -p /etc/snmp
echo "rocommunity public default" | sudo tee /etc/snmp/snmpd.conf
sudo systemctl enable --now snmpd
```

Your own host should then show up in the device table with `SNMP: yes` after a rescan.

## Known limitations

- Down-detection is based on missing from a single ARP scan pass, no debounce/threshold yet — a device that briefly doesn't answer will flash red

## Status

Actively in development. See [issues](https://github.com/WhoamiRAGE/snmpeek/issues).

## License

MIT — see [LICENSE](LICENSE).
