"""Garmin Connect source adapter (via the python-garminconnect library).

Resumes from a serialized session token (GARMINTOKENS) so no password is ever
stored. Mint the token once with scripts/garmin_login.py.

Besides the activity summary row (-> data/activities.csv) this adapter writes a
per-activity detail file (-> data/details/garmin-<id>.json) holding laps/splits,
heart-rate zones and running dynamics. Detail files are fetched once and kept,
so scheduled refreshes only hit Garmin for new activities.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..schema import Activity, canonical_sport


def _login():
    from garminconnect import Garmin

    tokens = os.environ.get("GARMINTOKENS")
    if tokens:
        g = Garmin()
        g.login(tokens)  # >512-char arg is treated as token data, not a path
        return g
    raise RuntimeError(
        "Garmin: no session token. Run scripts/garmin_login.py once to mint "
        "GARMINTOKENS (handles MFA; no password stored)."
    )


def _parse_start(raw: dict) -> datetime | None:
    """Activity start as LOCAL wall-clock time (the time shown on the watch).

    Garmin gives both startTimeLocal and startTimeGMT. We keep the local one so
    a 05:30 run on the 15th stays on the 15th for every user, whatever their
    timezone; the worker treats the stored value as wall-clock, not UTC.
    """
    s = raw.get("startTimeLocal") or raw.get("startTimeGMT")
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _download_track(g, activity_id, data_dir: str) -> str | None:
    rel = f"tracks/garmin-{activity_id}.gpx"
    if Path(data_dir, rel).exists():
        return rel  # already have it - refreshes stay incremental
    try:
        from garminconnect import Garmin
        data = g.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)
        Path(data_dir, rel).write_bytes(data)
        return rel
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Detail (laps / HR zones / running dynamics)
# ---------------------------------------------------------------------------

def _f(v, ndigits: int = 2):
    """Round a numeric value or pass None through."""
    if v is None:
        return None
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return None


def _pace(distance_m, seconds) -> str | None:
    """'m:ss/km' for a distance/duration pair, or None."""
    if not distance_m or not seconds or float(distance_m) <= 0:
        return None
    s = float(seconds) / (float(distance_m) / 1000.0)
    m, ss = divmod(int(round(s)), 60)
    return f"{m}:{ss:02d}/km"


def _cadence(raw: dict, prefix: str = "") -> tuple[float | None, float | None]:
    """(avg, max) cadence. Garmin names the key per sport family."""
    avg = (raw.get(f"{prefix}averageRunningCadenceInStepsPerMinute")
           or raw.get(f"{prefix}averageBikingCadenceInRevPerMinute")
           or raw.get("averageRunCadence") or raw.get("averageBikeCadence"))
    mx = (raw.get(f"{prefix}maxRunningCadenceInStepsPerMinute")
          or raw.get(f"{prefix}maxBikingCadenceInRevPerMinute")
          or raw.get("maxRunCadence") or raw.get("maxBikeCadence"))
    return _f(avg, 1), _f(mx, 1)


def _running_dynamics(raw: dict) -> dict:
    avg_cad, max_cad = _cadence(raw)
    stride_cm = raw.get("avgStrideLength")
    return {
        "avg_cadence_spm": avg_cad,
        "max_cadence_spm": max_cad,
        "avg_stride_length_m": _f(stride_cm / 100.0, 3) if stride_cm else None,
        "avg_vertical_oscillation_cm": _f(raw.get("avgVerticalOscillation"), 2),
        "avg_ground_contact_time_ms": _f(raw.get("avgGroundContactTime"), 0),
        "avg_vertical_ratio_pct": _f(raw.get("avgVerticalRatio"), 2),
    }


def _lap(i: int, lap: dict) -> dict:
    dist = lap.get("distance")
    dur = lap.get("duration")
    mov = lap.get("movingDuration") or dur
    avg_cad, max_cad = _cadence(lap)
    stride_cm = lap.get("strideLength")
    return {
        "lap": lap.get("lapIndex", i + 1),
        "distance_km": _f(dist / 1000.0, 3) if dist else None,
        "duration_s": _f(dur, 0),
        "moving_s": _f(mov, 0),
        "pace": _pace(dist, mov),
        "avg_speed_ms": _f(lap.get("averageSpeed"), 3),
        "max_speed_ms": _f(lap.get("maxSpeed"), 3),
        "avg_hr": _f(lap.get("averageHR"), 0),
        "max_hr": _f(lap.get("maxHR"), 0),
        "avg_cadence_spm": avg_cad,
        "max_cadence_spm": max_cad,
        "stride_length_m": _f(stride_cm / 100.0, 3) if stride_cm else None,
        "elevation_gain_m": _f(lap.get("elevationGain"), 1),
        "elevation_loss_m": _f(lap.get("elevationLoss"), 1),
        "avg_power_w": _f(lap.get("averagePower"), 0),
        "calories": _f(lap.get("calories"), 0),
        "intensity": lap.get("intensityType"),
    }


def _hr_zones(zones) -> list[dict]:
    out = []
    for z in zones or []:
        if not isinstance(z, dict):
            continue
        out.append({
            "zone": z.get("zoneNumber"),
            "seconds": _f(z.get("secsInZone"), 0),
            "low_bpm": _f(z.get("zoneLowBoundary"), 0),
        })
    return out


def _download_detail(g, activity_id, raw: dict, data_dir: str) -> str | None:
    rel = f"details/garmin-{activity_id}.json"
    path = Path(data_dir, rel)
    if path.exists():
        return rel  # fetched on an earlier run

    laps: list[dict] = []
    try:
        splits = g.get_activity_splits(activity_id) or {}
        laps = [_lap(i, lap) for i, lap in enumerate(splits.get("lapDTOs") or [])]
    except Exception:
        pass

    zones: list[dict] = []
    try:
        zones = _hr_zones(g.get_activity_hr_in_timezones(activity_id))
    except Exception:
        pass

    detail = {
        "id": f"garmin-{activity_id}",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "running_dynamics": _running_dynamics(raw),
        "training_effect": {
            "aerobic": _f(raw.get("aerobicTrainingEffect"), 1),
            "anaerobic": _f(raw.get("anaerobicTrainingEffect"), 1),
            "label": raw.get("trainingEffectLabel"),
        },
        "vo2max": _f(raw.get("vO2MaxValue"), 1),
        "avg_speed_ms": _f(raw.get("averageSpeed"), 3),
        "max_speed_ms": _f(raw.get("maxSpeed"), 3),
        "laps": laps,
        "hr_zones": zones,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
        return rel
    except Exception:
        return None


def fetch(days_back: int = 90, download_tracks: bool = True, download_details: bool = True,
          data_dir: str = "data") -> list[Activity]:
    g = _login()
    start = (date.today() - timedelta(days=days_back)).isoformat()
    end = date.today().isoformat()
    raw_list = g.get_activities_by_date(start, end)

    out: list[Activity] = []
    for r in raw_list:
        aid = r.get("activityId")
        type_key = (r.get("activityType") or {}).get("typeKey")
        dist_m = r.get("distance")
        avg_cad, max_cad = _cadence(r)
        stride_cm = r.get("avgStrideLength")
        out.append(Activity(
            source="garmin",
            source_id=str(aid),
            start=_parse_start(r),
            sport=canonical_sport(type_key),
            raw_sport=type_key,
            name=r.get("activityName"),
            distance_km=(dist_m / 1000.0) if dist_m else None,
            moving_s=int(r["movingDuration"]) if r.get("movingDuration") else (
                int(r["duration"]) if r.get("duration") else None),
            elapsed_s=int(r["duration"]) if r.get("duration") else None,
            elevation_gain_m=r.get("elevationGain"),
            avg_hr=r.get("averageHR"),
            max_hr=r.get("maxHR"),
            avg_watts=r.get("avgPower") or r.get("averagePower"),
            calories=r.get("calories"),
            track_file=_download_track(g, aid, data_dir) if download_tracks else None,
            avg_cadence=avg_cad,
            max_cadence=max_cad,
            stride_length_m=(stride_cm / 100.0) if stride_cm else None,
            max_speed_ms=r.get("maxSpeed"),
            aerobic_te=r.get("aerobicTrainingEffect"),
            anaerobic_te=r.get("anaerobicTrainingEffect"),
            vo2max=r.get("vO2MaxValue"),
            detail_file=_download_detail(g, aid, r, data_dir) if download_details else None,
        ))
    return out
