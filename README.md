# ReclaimCheck

**A data and satellite screening system for orphan well reclamation in Central Alberta.**

Independent project by Nidhi Nalini, 2026.

When an Alberta oil and gas company goes bankrupt, its wells become "orphans" and the
Orphan Well Association (OWA) takes over the cleanup. After a well is sealed, the land around it
(the well pad) must be reclaimed until vegetation returns. Checking that vegetation means visiting each
site, often on private farmland. ReclaimCheck uses public data to show where the backlog is, checks
from free satellite images whether each pad is growing back, and plans which sites a field crew should
visit first.

> The repository ships with **SAMPLE data** so it runs immediately. Every result produced from the sample is
> labelled as sample data. Put the real files in `data/raw/` to analyse the real backlog.

---

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1              # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m reclaimcheck all              # sample -> data -> satellite -> plan
streamlit run app/Home.py               # opens the app in the browser
python -m pytest                        # 33 tests
```

## Use the real data

| File | Where to get it | Save as |
|---|---|---|
| OWA Site-specific Inventory (Excel) | [orphanwell.ca/inventory/site-specific-inventory](https://www.orphanwell.ca/inventory/site-specific-inventory) → "Site-Specific Orphan Inventory List" | `data/raw/owa_inventory.xlsx` |
| AER ST37 List of Wells in Alberta | [AER Product Catalogue 10](https://www1.aer.ca/ProductCatalogue/10.html) → free self-service package | `data/raw/st37_wells.csv` (or .xlsx; update `config.yaml`) |
| Alberta municipal boundaries *(optional, recommended)* | [open.alberta.ca/opendata/property-municipal-boundaries](https://open.alberta.ca/opendata/property-municipal-boundaries), export as GeoJSON | `data/reference/municipal_boundaries.geojson` |
| ATS LSD centroids *(optional, recommended)* | [Alberta Township System dataset](https://open.canada.ca/data/en/dataset/76874ae6-373f-4371-bc99-e319a4fb84a3) (AltaLIS), CSV with `lsd,sec,twp,rge,mer,lat,lon` | `data/reference/ats_lsd_centroids.csv` |

Then:

```powershell
python -m reclaimcheck data
python -m reclaimcheck satellite --provider stac --limit 5     # quick test with real Sentinel-2
python -m reclaimcheck satellite --provider stac               # all eligible sites (cached after first run)
python -m reclaimcheck plan
```

Real satellite images need `pip install pystac-client rioxarray` and an internet connection. Images come from
[Sentinel-2 L2A on AWS Open Data](https://registry.opendata.aws/sentinel-2-l2a-cogs/) through the
[Earth Search STAC API](https://earth-search.aws.element84.com/v1); no account is needed. Only a 400 m window
around each site is downloaded and cached in `data/cache/`.

**Before trusting real results, check `config.yaml`:**
* `stage_keywords` and `expect_recovered_keywords` match the real values in *Current Project Type*
  (see the Data Intake page, column profile).
* `aer_columns` patterns found the right ST37 columns (shown on the Record Audit page).
* Without the boundary file, counties come from the nearest county centre (approximate, marked
  `nearest_centre`). Without the centroid file, coordinates are approximate (marked `approx`), which can be a
  few hundred metres off. The pad finder compensates for this.

---

## System design

```
OWA inventory (8 columns) ─┐
AER ST37 well list ────────┼─► DATA COMPONENT ─► outputs/data/
county boundaries ─────────┘   clean · locate · county · join · analyse
                                          │  wells_clean.csv
Sentinel-2 L2A (AWS) ──────────► SATELLITE COMPONENT ─► outputs/cv/
                                 cloud mask · NDVI · pad finder · recovery · evaluation
                                          │
                                 SHARED OUTPUT ─► outputs/plan/, outputs/reports/
                                 priority score · visit plan · site reports
                                          │
                                 Streamlit app (app/)
```

### Use cases

| # | Use case | Component | Code | App page |
|---|---|---|---|---|
| 1 | Backlog map: where orphan wells are concentrated (shares with 95% Wilson CIs) | Data | `eda/analysis.py` | Backlog Map |
| 2 | Licensee analysis: which bankrupt companies left the most wells (Pareto, HHI) | Data | `eda/analysis.py` | Licensees |
| 3 | Cleanup stage profile by county and site type (chi-square, Cramér's V) | Data | `eda/analysis.py` | Cleanup Stages |
| 4 | Well age and status (medians, bootstrap CIs, Kruskal-Wallis) | Data | `eda/analysis.py`, `eda/aer.py` | Well Age |
| 5 | Record audit: OWA vs AER disagreements | Data | `eda/aer.py` | Record Audit |
| 6 | Vegetation recovery check (NDVI, cloud mask, pad vs field ratio) | Satellite | `cv/vegetation.py` | Satellite Check |
| 7 | Stalled or outdated sites: image vs recorded stage | Satellite | `cv/pipeline.py` | Stage Agreement |
| 8 | Pad finder: locate the pad inside the LSD square (thresholding, morphology, connected components) | Satellite | `cv/vegetation.py` | Satellite Check |
| 9 | Reclamation timeline from 2017–2025 images | Satellite | `cv/vegetation.py` | Satellite Check |
| 10 | Field visit plan, weight sensitivity, baseline comparison and site reports | Both | `plan/`, `eda/priority.py` | Visit Plan, Site Report |

### Folder layout

```
config.yaml                every setting and threshold, documented
reclaimcheck/
  common/locations.py      ATS legal land location parser and converter
  common/counties.py       county assignment
  eda/                     DATA COMPONENT: ingest, aer, analysis, priority, pipeline
  cv/                      SATELLITE COMPONENT: imagery, vegetation, pipeline
  plan/                    visit plan and site reports
  sample.py                SAMPLE input generator
app/                       Streamlit app (Home + 10 pages)
tests/                     pytest suite
data/raw/                  put real input files here (not committed)
outputs/                   everything the pipeline produces
```

## Methods and limits (summary)

* **Cleaning:** each rule is logged with a row count (`outputs/data/quality_log.csv`); excluded rows are kept
  with a reason (`excluded_rows.csv`). No row is dropped silently.
* **Statistics:** chosen for the data type: chi-square and Cramér's V for counts, Wilson intervals for shares,
  medians, bootstrap CIs and Kruskal-Wallis for skewed ages, HHI for concentration.
* **Satellite:** NDVI from bands B04/B08 with reflectance scale and offset from the image metadata; SCL classes
  0, 1, 3, 8–11 masked; mid-summer only; a year is skipped if over 30% of the window is cloudy.
* **Evaluation:** with real data there are no field-verified labels, so results are reported as **agreement
  with OWA records, not accuracy**. The synthetic provider has known answers and is used only to check the
  method (verdict accuracy, pad IoU), clearly labelled as sample results.
* **Known limits:** 10 m pixels (a pad is ~10 × 10 pixels); NDVI cannot tell weeds from crops or reclaimed
  cover; fallow or harvested neighbouring fields change the comparison; records may lag behind the ground.
  Screening supports and never replaces field verification or certification.

## AI use

Built with AI assistance (Claude). I reviewed, ran and tested the code myself.
