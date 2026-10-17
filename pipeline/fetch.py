"""Orchestrator: pull Garmin activities -> write data/.

Runs on a schedule and on-demand (GitHub Actions or locally):

  python -m pipeline.fetch --days 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .writer import write_dataset


def run(days_back: int = 90, data_dir: str = "data", health: bool = True) -> dict:
    from .sources import garmin
    activities = garmin.fetch(days_back=days_back, data_dir=data_dir)
    print(f"[garmin] fetched {len(activities)} activities", file=sys.stderr)
    summary = write_dataset(activities, data_dir)
    if health:
        from .sources import garmin_health
        try:
            summary.update(garmin_health.fetch(days_back=days_back, data_dir=data_dir))
        except Exception as e:  # health is optional; never block the activity refresh
            print(f"[garmin-health] skipped: {e}", file=sys.stderr)
    print(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser(description="Fetch Garmin activities into data/.")
    ap.add_argument("--days", type=int, default=int(os.environ.get("DAYS_BACK", "90")))
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "data"))
    ap.add_argument("--no-health", action="store_true",
                    help="skip daily sleep/HRV/readiness (also HEALTH=0)")
    args = ap.parse_args()
    summary = run(days_back=args.days, data_dir=args.data_dir,
                  health=not args.no_health and os.environ.get("HEALTH", "1") != "0")
    if summary["activities_written"] == 0:
        print("No activities written - check your Garmin token / date range.", file=sys.stderr)


if __name__ == "__main__":
    main()
