"""Alberta Township System (ATS) locations.

Wells in Alberta are located by a legal land description such as
04-12-038-27W4, which reads:

    LSD 04 - Section 12 - Township 038 - Range 27 - West of the 4th meridian

* A township is about 6 miles (9.7 km) square, counted north from the
  49th parallel (the US border).
* Ranges are counted west from a meridian: the 4th meridian is 110 deg W,
  the 5th is 114 deg W and the 6th is 118 deg W.
* Each township has 36 sections (1 mile square), numbered in a back-and-forth
  "snake" starting at the south-east corner.
* Each section has 16 legal subdivisions (LSDs, about 400 m square), also
  numbered in a snake.

This module parses the text formats found in OWA and AER files and converts
a location to latitude and longitude. Two methods are available:

1. Exact: look the LSD up in the AltaLIS ATS centroid file (if downloaded).
2. Approximate: compute the position from the survey geometry. This ignores
   road allowances and correction lines, so it can be off by a few hundred
   metres. Results record which method was used.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

MILE_KM = 1.609344
KM_PER_DEG_LAT = 111.2
MERIDIAN_LON = {4: -110.0, 5: -114.0, 6: -118.0}


@dataclass(frozen=True)
class LSDLocation:
    lsd: int
    section: int
    township: int
    range: int
    meridian: int

    def key(self) -> str:
        """Standard text form, e.g. 04-12-038-27W4."""
        return f"{self.lsd:02d}-{self.section:02d}-{self.township:03d}-{self.range:02d}W{self.meridian}"


# 04-12-038-27W4, 4-12-38-27-W4, 04-12-038-27 W4M, and the same inside a UWI
# such as 100/04-12-038-27W4/00
_DASHED = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{1,3})-(\d{1,2})\s*-?\s*W\s*([4-6])\s*M?", re.I)
# Compressed 16-character UWI: 1 00 04 12 038 27 W4 00
_COMPACT = re.compile(r"^\d[0-9A-Z]{2}(\d{2})(\d{2})(\d{3})(\d{2})W([4-6])\d{0,2}$", re.I)


class LocationError(ValueError):
    """Raised with a short, human-readable reason when a location is invalid."""


def parse_location(text) -> LSDLocation:
    """Parse any supported location format. Raises LocationError with the reason."""
    if text is None or pd.isna(text) or str(text).strip() == "":
        raise LocationError("missing")
    s = str(text).strip().upper()
    m = _DASHED.search(s)
    if not m:
        m = _COMPACT.match(s.replace(" ", "").replace("/", ""))
    if not m:
        raise LocationError("unrecognized format")
    lsd, sec, twp, rge, mer = (int(g) for g in m.groups())
    if not 1 <= lsd <= 16:
        raise LocationError(f"LSD {lsd} not in 1-16")
    if not 1 <= sec <= 36:
        raise LocationError(f"section {sec} not in 1-36")
    if not 1 <= twp <= 126:
        raise LocationError(f"township {twp} not in 1-126")
    if not 1 <= rge <= 30:
        raise LocationError(f"range {rge} not in 1-30")
    return LSDLocation(lsd, sec, twp, rge, mer)


def _section_offset(section: int) -> tuple[int, int]:
    """(row from south, column from east) of a section inside its township."""
    row = (section - 1) // 6
    k = (section - 1) % 6
    col = k if row % 2 == 0 else 5 - k
    return row, col


def _lsd_offset(lsd: int) -> tuple[int, int]:
    """(row from south, column from east) of an LSD inside its section."""
    row = (lsd - 1) // 4
    k = (lsd - 1) % 4
    col = k if row % 2 == 0 else 3 - k
    return row, col


def approx_latlon(loc: LSDLocation) -> tuple[float, float]:
    """Approximate centre of an LSD in decimal degrees (WGS84)."""
    srow, scol = _section_offset(loc.section)
    lrow, lcol = _lsd_offset(loc.lsd)
    north_mi = (loc.township - 1) * 6 + srow + (lrow + 0.5) / 4
    lat = 49.0 + north_mi * MILE_KM / KM_PER_DEG_LAT
    west_mi = (loc.range - 1) * 6 + scol + (lcol + 0.5) / 4
    km_per_deg_lon = KM_PER_DEG_LAT * math.cos(math.radians(lat))
    lon = MERIDIAN_LON[loc.meridian] - west_mi * MILE_KM / km_per_deg_lon
    return lat, lon


def approx_location(lat: float, lon: float) -> LSDLocation:
    """Inverse of approx_latlon: the LSD that contains a point (approximate)."""
    north_mi = (lat - 49.0) * KM_PER_DEG_LAT / MILE_KM
    km_per_deg_lon = KM_PER_DEG_LAT * math.cos(math.radians(lat))
    mer = 4 if lon > -114.0 else (5 if lon > -118.0 else 6)
    west_mi = (MERIDIAN_LON[mer] - lon) * km_per_deg_lon / MILE_KM
    twp = int(north_mi // 6) + 1
    rge = int(west_mi // 6) + 1
    ny, wx = north_mi - (twp - 1) * 6, west_mi - (rge - 1) * 6
    srow, scol = int(ny), int(wx)
    section = srow * 6 + (scol if srow % 2 == 0 else 5 - scol) + 1
    lrow, lcol = int((ny - srow) * 4), int((wx - scol) * 4)
    lsd = lrow * 4 + (lcol if lrow % 2 == 0 else 3 - lcol) + 1
    return LSDLocation(lsd, section, twp, rge, mer)


class LocationConverter:
    """Converts locations, preferring the official centroid file when present."""

    def __init__(self, centroid_file: Path | None = None):
        self.lookup: dict[str, tuple[float, float]] = {}
        if centroid_file and Path(centroid_file).exists():
            df = pd.read_csv(centroid_file)
            cols = {c.lower(): c for c in df.columns}
            need = ["lsd", "sec", "twp", "rge", "mer", "lat", "lon"]
            if all(n in cols for n in need):
                for r in df.itertuples(index=False):
                    d = r._asdict()
                    loc = LSDLocation(int(d[cols["lsd"]]), int(d[cols["sec"]]), int(d[cols["twp"]]),
                                      int(d[cols["rge"]]), int(d[cols["mer"]]))
                    self.lookup[loc.key()] = (float(d[cols["lat"]]), float(d[cols["lon"]]))

    def to_latlon(self, loc: LSDLocation) -> tuple[float, float, str]:
        """Return (lat, lon, method) where method is 'ats_file' or 'approx'."""
        hit = self.lookup.get(loc.key())
        if hit:
            return hit[0], hit[1], "ats_file"
        lat, lon = approx_latlon(loc)
        return lat, lon, "approx"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance on the earth's surface in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
