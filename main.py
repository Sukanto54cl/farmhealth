"""CLI entry point for the farmhealth NDVI pipeline.

Examples
--------
    python main.py                                  # defaults: Märkisch-Oderland, 2025-05..2026-05
    python main.py --start 2024-04-01 --end 2024-11-01
    python main.py --aoi-name "Barnim" --aoi-key-prefix 12060
"""

from farmhealth.config import parse_args
from farmhealth.pipeline import run


def main() -> None:
    config = parse_args()
    run(config)


if __name__ == "__main__":
    main()
