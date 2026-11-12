"""Assign each site to a county (rural municipality).

The OWA inventory has no county column, so the county is worked out from the
site's coordinates.

* Preferred: point-in-polygon against the Government of Alberta municipal
  boundaries (open.alberta.ca/opendata/property-municipal-boundaries),
  exported as GeoJSON to data/reference/municipal_boundaries.geojson.
* Fallback: nearest county centre from the small table below. This is only
  approximate and every row it assigns is marked county_method = "nearest_centre".
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .locations import haversine_km

# Approximate centres of selected Alberta rural municipalities (fallback only).
COUNTY_CENTRES = {
    "Red Deer County": (52.12, -113.75),
    "Lacombe County": (52.47, -113.55),
    "Ponoka County": (52.73, -113.70),
    "Clearwater County": (52.30, -114.95),
    "Mountain View County": (51.83, -114.25),
    "Kneehill County": (51.72, -113.20),
    "County of Stettler": (52.30, -112.70),
    "County of Wetaskiwin": (52.97, -113.60),
    "Leduc County": (53.22, -113.55),
    "Brazeau County": (53.05, -115.30),
    "Camrose County": (52.95, -112.85),
    "Flagstaff County": (52.65, -111.90),
    "County of Paintearth": (52.12, -111.90),
    "Starland County": (51.75, -112.60),
    "Wheatland County": (51.20, -112.90),
    "Rocky View County": (51.20, -114.20),
    "Yellowhead County": (53.45, -116.50),
    "County of Vermilion River": (53.30, -110.85),
    "Municipal District of Bonnyville": (54.30, -110.90),
    "Special Areas": (51.50, -111.20),
}


class CountyAssigner:
    def __init__(self, geojson: Path | None = None, name_fields=("MUNI_NAME", "NAME", "name")):
        self.polygons = []
        if geojson and Path(geojson).exists():
            from shapely.geometry import shape
            from shapely.strtree import STRtree

            with open(geojson, encoding="utf-8") as f:
                gj = json.load(f)
            for feat in gj.get("features", []):
                props = feat.get("properties", {})
                name = next((props[k] for k in name_fields if k in props), None)
                if name:
                    self.polygons.append((shape(feat["geometry"]), str(name)))
            self._tree = STRtree([p for p, _ in self.polygons]) if self.polygons else None

    @property
    def method(self) -> str:
        return "boundary_file" if self.polygons else "nearest_centre"

    def assign(self, lat: float, lon: float) -> tuple[str | None, str]:
        if self.polygons:
            from shapely.geometry import Point

            pt = Point(lon, lat)
            for idx in self._tree.query(pt):
                poly, name = self.polygons[int(idx)]
                if poly.contains(pt):
                    return name, "boundary_file"
            return None, "boundary_file"
        best = min(COUNTY_CENTRES.items(), key=lambda kv: haversine_km(lat, lon, *kv[1]))
        return best[0], "nearest_centre"

    def assign_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        res = [self.assign(a, b) if pd.notna(a) else (None, None) for a, b in zip(out["lat"], out["lon"])]
        out["county"] = [r[0] for r in res]
        out["county_method"] = [r[1] for r in res]
        return out
