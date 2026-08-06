"""Minimal YAML config loader with sane defaults."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS = {
    "network": {"subnet": "192.168.1.0/24", "interface": None},
    "snmp": {"enabled": True, "community": "public", "port": 161, "timeout": 1, "retries": 1},
    "monitor": {"poll_interval": 30},
    "storage": {"db_path": "snmpeek.db"},
    "ui": {"refresh_rate": 2},
}


def load_config(path: str = "config.yaml") -> dict:
    """Load config.yaml if present, otherwise fall back to DEFAULTS.

    Missing keys in the file are filled in from DEFAULTS (shallow per-section merge).
    """
    config = {section: dict(values) for section, values in DEFAULTS.items()}

    config_path = Path(path)
    if config_path.exists():
        with config_path.open() as f:
            user_config = yaml.safe_load(f) or {}
        for section, values in user_config.items():
            if section in config and isinstance(values, dict):
                config[section].update(values)
            else:
                config[section] = values

    return config
