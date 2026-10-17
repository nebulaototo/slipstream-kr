"""Garmin daily wellness source: sleep, resting HR, HRV, body battery, stress,
steps, training readiness.

One JSON per calendar day -> data/health/YYYY-MM-DD.json (fetched once and
kept; the two most recent days are re-fetched because Garmin keeps revising
them as the watch syncs), plus a flat data/health/daily.csv rebuilt from every
JSON on disk, which is what the MCP worker reads.

Four Garmin calls per new day: get_stats, get_sleep_data, get_hrv_data,
get_training_readiness. All responses are passed through defensively - any
missing block just leaves its columns blank.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .garmin import _login

_HEADERS = [
    "Date", "Sleep Score", "Sleep Quality", "Sleep Hours", "Deep Min", "Light Min",
    "REM Min", "Awake Min", "Nap Min", "Bedtime", "Wake Time", "Sleep Avg SpO2",
    "Sleep Avg Respiration", "Resting HR", "HRV Last Night", "HRV Weekly Avg", "HRV Status",
    "Body Battery High", "Body Battery Low", "Body Battery Change", "Avg Stress", "Max Stress",
    "Steps", "Training Readiness", "Readiness Level", "Readiness Note",
]


def _f(v, nd=1):
    if v is None:
        return None
    try:
        r = round(float(v), nd)
        return int(r) if nd == 0 or r == int(r) else r
    except (TypeError, ValueError):
        return None


def _mins(seconds):
    return _f(seconds / 60.0, 0) if seconds else None


def _hhmm(ts_ms):
    """Garmin local timestamps are 'local wall clock encoded as if UTC'."""
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%H:%M")
    except (TypeError, ValueError, OSError):
        return None


def _get(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _call(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # one failed block shouldn't sink the day
        print(f"[garmin-health] {fn.__name__}{a}: {e}", file=sys.stderr)
        return None


def fetch_day(g, day: str) -> dict:
    stats = _call(g.get_stats, day) or {}
    sleep = _call(g.get_sleep_data, day) or {}
    hrv = _call(g.get_hrv_data, day) or {}
    readiness = _call(g.get_training_readiness, day) or []

    dto = sleep.get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    hrv_sum = hrv.get("hrvSummary") or {}
    rd = readiness[0] if isinstance(readiness, list) and readiness else (
        readiness if isinstance(readiness, dict) else {})

    sleep_s = dto.get("sleepTimeSeconds")
    return {
        "date": day,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sleep": {
            "score": _get(scores, "overall", "value"),
            "quality": _get(scores, "overall", "qualifierKey"),
            "hours": _f(sleep_s / 3600.0, 2) if sleep_s else None,
            "deep_min": _mins(dto.get("deepSleepSeconds")),
            "light_min": _mins(dto.get("lightSleepSeconds")),
            "rem_min": _mins(dto.get("remSleepSeconds")),
            "awake_min": _mins(dto.get("awakeSleepSeconds")),
            "nap_min": _mins(dto.get("napTimeSeconds")),
            "bedtime": _hhmm(dto.get("sleepStartTimestampLocal")),
            "wake_time": _hhmm(dto.get("sleepEndTimestampLocal")),
            "avg_spo2": _f(dto.get("averageSpO2Value"), 0),
            "lowest_spo2": _f(dto.get("lowestSpO2Value"), 0),
            "avg_respiration": _f(dto.get("averageRespirationValue"), 1),
            "avg_sleep_stress": _f(dto.get("avgSleepStress"), 0),
            "restless_moments": sleep.get("restlessMomentsCount"),
            "body_battery_change": sleep.get("bodyBatteryChange"),
            "score_breakdown": {k: _get(v, "value") for k, v in scores.items()
                                if isinstance(v, dict) and k != "overall"},
        },
        "resting_hr": stats.get("restingHeartRate") or sleep.get("restingHeartRate"),
        "hrv": {
            "last_night": _f(hrv_sum.get("lastNightAvg"), 0),
            "last_night_5min_high": _f(hrv_sum.get("lastNight5MinHigh"), 0),
            "weekly_avg": _f(hrv_sum.get("weeklyAvg"), 0),
            "status": hrv_sum.get("status"),
            "baseline": hrv_sum.get("baseline"),
            "feedback": hrv_sum.get("feedbackPhrase"),
        },
        "body_battery": {
            "high": stats.get("bodyBatteryHighestValue"),
            "low": stats.get("bodyBatteryLowestValue"),
            "at_wake": stats.get("bodyBatteryAtWakeTime"),
            "charged": stats.get("bodyBatteryChargedValue"),
            "drained": stats.get("bodyBatteryDrainedValue"),
        },
        "stress": {
            "avg": stats.get("averageStressLevel"),
            "max": stats.get("maxStressLevel"),
            "rest_min": _mins(stats.get("restStressDuration")),
            "low_min": _mins(stats.get("lowStressDuration")),
            "medium_min": _mins(stats.get("mediumStressDuration")),
            "high_min": _mins(stats.get("highStressDuration")),
        },
        "activity_summary": {
            "steps": stats.get("totalSteps"),
            "active_kcal": stats.get("activeKilocalories"),
            "intensity_min": (stats.get("moderateIntensityMinutes") or 0)
                             + 2 * (stats.get("vigorousIntensityMinutes") or 0) or None,
            "floors_up": stats.get("floorsAscended"),
        },
        "training_readiness": {
            "score": rd.get("score"),
            "level": rd.get("level"),
            "note": rd.get("feedbackShort"),
            "recovery_time_h": _f((rd.get("recoveryTime") or 0) / 60.0, 1) if rd.get("recoveryTime") else None,
            "factors_pct": {
                "sleep": rd.get("sleepScoreFactorPercent"),
                "sleep_history": rd.get("sleepHistoryFactorPercent"),
                "hrv": rd.get("hrvFactorPercent"),
                "recovery": rd.get("recoveryTimeFactorPercent"),
                "load": rd.get("acwrFactorPercent"),
                "stress_history": rd.get("stressHistoryFactorPercent"),
            },
        },
    }


def _row(d: dict) -> list:
    s, h, bb, st, tr = d["sleep"], d["hrv"], d["body_battery"], d["stress"], d["training_readiness"]
    v = lambda x: "" if x is None else x  # noqa: E731
    return [v(x) for x in [
        d["date"], s["score"], s["quality"], s["hours"], s["deep_min"], s["light_min"],
        s["rem_min"], s["awake_min"], s["nap_min"], s["bedtime"], s["wake_time"], s["avg_spo2"],
        s["avg_respiration"], d["resting_hr"], h["last_night"], h["weekly_avg"], h["status"],
        bb["high"], bb["low"], s["body_battery_change"], st["avg"], st["max"],
        d["activity_summary"]["steps"], tr["score"], tr["level"], tr["note"],
    ]]


def write_daily_csv(data_dir: str) -> int:
    hdir = Path(data_dir, "health")
    days = sorted(hdir.glob("????-??-??.json"), reverse=True)
    with (hdir / "daily.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_HEADERS)
        for p in days:
            try:
                w.writerow(_row(json.loads(p.read_text(encoding="utf-8"))))
            except Exception as e:
                print(f"[garmin-health] skip {p.name}: {e}", file=sys.stderr)
    return len(days)


def fetch(days_back: int = 90, data_dir: str = "data", refetch_recent: int = 2,
          pause_s: float = 0.3) -> dict:
    g = _login()
    hdir = Path(data_dir, "health")
    hdir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    fetched = 0
    for i in range(days_back + 1):
        day = today - timedelta(days=i)
        p = hdir / f"{day.isoformat()}.json"
        if p.exists() and i >= refetch_recent:
            continue
        d = fetch_day(g, day.isoformat())
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        fetched += 1
        time.sleep(pause_s)
    total = write_daily_csv(data_dir)
    return {"health_days_fetched": fetched, "health_days_total": total}
