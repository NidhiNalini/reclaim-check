"""Generate SAMPLE input files in the same format as the real ones.

The sample lets the whole system run before the real OWA file is downloaded,
and gives the tests a fixed dataset. Every value is invented. The file layout
copies the real OWA Site-specific Inventory (8 columns) and a simplified
AER ST37 well list. Common data problems are injected on purpose so the
cleaning steps have something to find.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.counties import COUNTY_CENTRES
from .common.locations import approx_location
from .config import load_config, resolve

LICENSEES = [
    "Aspen Coulee Resources Ltd.", "Parkland Ridge Energy Inc.", "Medicine Flats Oil Corp.",
    "Blindman Valley Petroleum Ltd.", "Antler Hill Resources Inc.", "Gull Creek Energy Ltd.",
    "Prairie Kestrel Oil Ltd.", "Battle River Hydrocarbons Inc.",
]
PROJECT_TYPES = [
    ("Decommissioning", "Decommissioning", 30),
    ("Reclamation - Environmental Site Assessment", "Reclamation", 14),
    ("Reclamation - Remediation", "Reclamation", 6),
    ("Reclamation - Vegetation Monitoring", "Reclamation", 28),
    ("Reclamation - Reclamation Certificate Application", "Reclamation", 12),
    ("Reclamation", "Reclamation", 10),
]
COMPONENTS = [("Well", 78), ("Pipeline", 14), ("Facility", 8)]
# Weight of each county in the sample (Central Alberta heavier, as in the real backlog).
COUNTY_W = {
    "Red Deer County": 9, "Lacombe County": 7, "Ponoka County": 6, "Clearwater County": 8,
    "Mountain View County": 5, "Kneehill County": 5, "County of Stettler": 4,
}


def _fmt_location(rng: np.random.Generator, key: str) -> str:
    """Write the same location in the different styles found in real files."""
    lsd, sec, twp, rgem = key.split("-")
    r = rng.random()
    if r < 0.55:
        return key
    if r < 0.8:
        return f"100/{key}/00"
    if r < 0.9:
        return f"00/{key}/0"
    rge, mer = rgem.split("W")
    return f"100{lsd}{sec}{twp}{rge}W{mer}00"


def make_sample(n_rows: int = 650, seed: int = 2026) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    names = list(COUNTY_CENTRES)
    weights = np.array([COUNTY_W.get(n, 1.6) for n in names], float)
    weights /= weights.sum()
    pt_w = np.array([w for *_, w in PROJECT_TYPES], float)
    pt_w /= pt_w.sum()
    comp_w = np.array([w for _, w in COMPONENTS], float)
    comp_w /= comp_w.sum()

    owa, aer = [], []
    for i in range(n_rows):
        county = names[rng.choice(len(names), p=weights)]
        clat, clon = COUNTY_CENTRES[county]
        lat = float(np.clip(clat + rng.normal(0, 0.10), 49.2, 59.8))
        lon = float(np.clip(clon + rng.normal(0, 0.17), -119.8, -110.1))
        key = approx_location(lat, lon).key()
        big = rng.random() < 0.28
        licensee = LICENSEES[0] if big else LICENSEES[1 + rng.integers(len(LICENSEES) - 1)]
        ptype, dept, _ = PROJECT_TYPES[rng.choice(len(PROJECT_TYPES), p=pt_w)]
        comp = COMPONENTS[rng.choice(len(COMPONENTS), p=comp_w)][0]
        lic_num = int(rng.integers(10_000, 520_000))
        prefix = {"Well": "W", "Pipeline": "P", "Facility": "F"}[comp]
        to_key = key if comp != "Well" or rng.random() < 0.6 else approx_location(lat + rng.normal(0, 0.003), lon).key()
        owa.append({
            "Site Name": f"{licensee.split()[0].upper()} {key.replace('-', ' ')}",
            "Licensee": licensee,
            "Responsible Department": dept,
            "Current Project Type": ptype,
            "Component Type": comp,
            "License Number": f"{prefix}{lic_num:07d}" if rng.random() < 0.7 else str(lic_num),
            "From Location": _fmt_location(rng, key),
            "To Location": _fmt_location(rng, to_key),
        })
        if comp == "Well" and rng.random() < 0.93:   # ~7% of wells will not match AER
            year = int(np.clip(rng.normal(1985, 12), 1952, 2018))
            lic_date = pd.Timestamp(year=year, month=int(rng.integers(1, 13)), day=int(rng.integers(1, 28)))
            aer.append({
                "Licence Number": f"{lic_num:07d}",
                "UWI": f"100/{key}/00",
                "Licensee Name": licensee if rng.random() < 0.92 else LICENSEES[rng.integers(len(LICENSEES))],
                "Licence Status": rng.choice(["Abandoned", "Suspended", "RecCertified", "Issued"], p=[.55, .3, .1, .05]),
                "Licence Issue Date": lic_date.date().isoformat(),
                "Spud Date": (lic_date + pd.Timedelta(days=int(rng.integers(10, 200)))).date().isoformat(),
            })

    owa_df = pd.DataFrame(owa)
    # ---- inject realistic problems -------------------------------------
    idx = rng.choice(len(owa_df), 8, replace=False)
    dups = owa_df.iloc[idx].copy()                                   # duplicate rows
    owa_df.loc[rng.choice(len(owa_df), 6, replace=False), "From Location"] = ""   # missing
    bad = ["17-04-036-26W4", "08-38-040-02W5", "12-22-39-27", "LSD 6 SEC 14", "06-14-037-31W4"]
    owa_df.loc[rng.choice(len(owa_df), len(bad), replace=False), "From Location"] = bad
    owa_df.loc[rng.choice(len(owa_df), 5, replace=False), "Licensee"] = (
        owa_df["Licensee"].sample(5, random_state=seed).str.upper().str.replace(" LTD.", " LTD", regex=False).values)
    owa_df.loc[rng.choice(len(owa_df), 3, replace=False), "Current Project Type"] = ""
    owa_df = pd.concat([owa_df, dups]).sample(frac=1, random_state=seed).reset_index(drop=True)
    return {"owa": owa_df, "aer": pd.DataFrame(aer)}


def write_sample(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    d = resolve(cfg["paths"]["sample_dir"])
    d.mkdir(parents=True, exist_ok=True)
    s = make_sample()
    owa_path, aer_path = d / "owa_inventory_SAMPLE.xlsx", d / "st37_wells_SAMPLE.csv"
    s["owa"].to_excel(owa_path, index=False, sheet_name="Inventory")
    s["aer"].to_csv(aer_path, index=False)
    return [str(owa_path), str(aer_path)]
