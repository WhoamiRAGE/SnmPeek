"""snmpeek - Terminal Network Topology Visualizer / Mini NMS

Entry point.
"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="snmpeek", description="Terminal Network Topology Visualizer / Mini NMS")
    parser.add_argument(
        "-c", "--config", default="config.yaml", help="Path to config.yaml (default: ./config.yaml)"
    )
    args = parser.parse_args()

    from ui.app import run

    try:
        run(args.config)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
