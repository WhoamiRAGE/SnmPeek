# snmpeek

Terminal-based mini Network Management System (NMS). Discovers hosts on the local network via ARP/ping, enriches SNMP-capable devices with additional data (interfaces, LLDP/CDP neighbors), and renders it all as a live topology map in a Textual-based TUI.

## Features (planned)

- **Discovery**: ARP scan (scapy) to find live hosts on the subnet
- **SNMP enrichment**: sysName, sysDescr, ifTable, and LLDP/CDP neighbor tables where available
- **Topology graph**: graph model built with networkx, rendered visually in the TUI
- **Monitoring**: asyncio background polling, status history stored in SQLite
- **TUI**: Textual-based device table + topology view + detail panel

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

> ARP scanning typically requires root/sudo (raw sockets).

## Usage

```bash
sudo python -m snmpeek.cli
```

## Status

Actively in development. See [issues](https://github.com/WhoamiRAGE/snmpeek/issues).

## License

MIT — see [LICENSE](LICENSE).
