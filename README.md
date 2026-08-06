# snmpeek

Terminal-based mini Network Management System (NMS). Yerli şəbəkəni ARP/ping ilə kəşf edir, SNMP dəstəkləyən cihazlardan əlavə məlumat (interfeyslər, LLDP/CDP qonşuları) toplayır və nəticəni Textual əsaslı TUI-də real-time topologiya xəritəsi kimi göstərir.

## Xüsusiyyətlər (planlanan)

- **Discovery**: ARP scan (scapy) ilə subnetdəki canlı hostların aşkarlanması
- **SNMP enrichment**: sysName, sysDescr, ifTable, mümkünsə LLDP/CDP qonşu cədvəli
- **Topology graph**: networkx ilə qraf modeli, TUI-də vizual render
- **Monitoring**: asyncio background polling, status dəyişikliklərinin SQLite-da tarixçəsi
- **TUI**: Textual ilə device table + topology view + detail panel

## Quraşdırma

```bash
git clone https://github.com/WhoamiRAGE/snmpeek.git
cd snmpeek
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# config.yaml faylını öz subnetinə uyğun redaktə et
```

> ARP scan üçün adətən root/sudo hüququ lazımdır (raw socket).

## İstifadə

```bash
sudo python -m snmpeek.cli
```

## Status

Aktiv inkişafda. Bax [issues](https://github.com/WhoamiRAGE/snmpeek/issues).

## Lisenziya

MIT — bax [LICENSE](LICENSE).
