"""Load config.yaml and resolve file paths relative to the project root."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read the YAML configuration. Paths stay relative; use `resolve()` to open them."""
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(p: str | Path) -> Path:
    """Turn a path from the config into an absolute path inside the project."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def input_path(cfg: dict, key: str, sample_name: str) -> tuple[Path, bool]:
    """Return the real input file if it exists, otherwise the sample file.

    The second value is True when the sample is being used, so every output
    can say clearly whether it came from real or sample data.
    """
    real = resolve(cfg["paths"][key])
    if real.exists():
        return real, False
    return resolve(cfg["paths"]["sample_dir"]) / sample_name, True


def out_dir(cfg: dict, *parts: str) -> Path:
    d = resolve(cfg["paths"]["outputs"]).joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    return d
