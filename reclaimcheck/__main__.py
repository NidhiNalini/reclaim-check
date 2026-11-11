"""Command line for ReclaimCheck.

    python -m reclaimcheck sample      create SAMPLE input files in data/sample/
    python -m reclaimcheck data        AIDA 2156 component: clean, join, analyse
    python -m reclaimcheck satellite   AIDA 2154 component: images, NDVI, pads, evaluation
                     [--provider stac|synthetic] [--limit N]
    python -m reclaimcheck plan        priority list, visit plan and site reports
    python -m reclaimcheck all         everything above, in order
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from .config import load_config, resolve


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="reclaimcheck", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sample", "data", "satellite", "plan", "all"])
    ap.add_argument("--provider", choices=["synthetic", "stac"], default=None)
    ap.add_argument("--limit", type=int, default=None, help="only the first N sites (for a quick test)")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)

    if a.command in ("sample", "all"):
        from .sample import write_sample
        print("Sample files:", *write_sample(cfg), sep="\n  ")
    if a.command in ("data", "all"):
        from .eda.pipeline import run
        s = run(cfg)
        print(f"\n[2156 data] {'SAMPLE DATA' if s['sample_data'] else 'real data'}: "
              f"{s['rows_received']} rows -> {s['wells_clean']} clean wells; AER match {s['aer']['match_rate_pct']}%")
        for k, v in s["findings"].items():
            print(f"  {k}: {v}")
    if a.command in ("satellite", "all"):
        from .cv.pipeline import run
        e = run(cfg, a.provider, a.limit)
        print(f"\n[2154 satellite] provider={e['provider']}: {e['sites_checked']} sites, "
              f"agreement with records {e['agreement_pct']}%, pads detected {e['pad_detected_pct']}%")
        if "sample_truth" in e:
            st = e["sample_truth"]
            print(f"  on SAMPLE images with known answers: accuracy {st['verdict_accuracy_pct']}%, "
                  f"pad IoU median {st['pad_iou_median']}")
    if a.command in ("plan", "all"):
        from .plan.reports import write_reports
        from .plan.visits import run
        s = run(cfg)
        scored = pd.read_csv(resolve("outputs/plan/priority_list.csv"), dtype={"licence_norm": str})
        yp = resolve("outputs/cv/year_results.csv")
        years = pd.read_csv(yp, dtype={"licence_norm": str}) if yp.exists() else pd.DataFrame(columns=["licence_norm"])
        sample = json.loads(resolve("outputs/data/summary.json").read_text())["sample_data"]
        n = write_reports(scored, years, cfg, sample)
        print(f"\n[plan] {s['visit_first']} visit first, {s['visit']} visit -> {s['crew_days']} crew-days, "
              f"{s['km']} km (vs {s['crew_days_if_all_checked_sites_visited']} days if every checked site "
              f"were visited). {n} site reports written.")
        if s["baseline"]:
            b = s["baseline"]
            print(f"  same {b['visits']} visits: ranked list finds {b['found_by_ranked_list']} poorly recovered "
                  f"sites, oldest-first finds {b['found_by_oldest_first']} (of {b['poorly_recovered_total']})")


if __name__ == "__main__":
    main()
