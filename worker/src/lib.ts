/**
 * Pure data helpers (CSV parsing, filtering, and stats). Kept separate from the
 * MCP wiring in index.ts so they can be unit-tested without a Worker runtime.
 */

export interface Activity {
  id: string;
  date: Date | null;
  name: string;
  type: string;
  distanceKm?: number;
  movingS?: number;
  elapsedS?: number;
  maxHr?: number;
  avgHr?: number;
  elevGain?: number;
  calories?: number;
  source: string;
  avgCadence?: number;
  maxCadence?: number;
  strideM?: number;
  maxSpeedMs?: number;
  aerobicTe?: number;
  anaerobicTe?: number;
  vo2max?: number;
  detailFile?: string;
}

export function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inq = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inq) {
      if (c === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else inq = false;
      } else cur += c;
    } else if (c === ",") { out.push(cur); cur = ""; }
    else if (c === '"') inq = true;
    else cur += c;
  }
  out.push(cur);
  return out;
}

export function parseDate(s: string): Date | null {
  if (!s) return null;
  // Writer emits LOCAL wall-clock "YYYY-MM-DD HH:MM:SS"; tagging it as Z keeps
  // the calendar date stable (we only ever slice the date / month back out).
  const d = new Date(s.replace(" ", "T") + "Z");
  return isNaN(d.getTime()) ? null : d;
}

export function parseCsv(text: string): Activity[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 2) return [];
  const header = parseCsvLine(lines[0]);
  const ix = (name: string) => header.indexOf(name);
  const iId = ix("Activity ID"), iDate = ix("Activity Date"), iName = ix("Activity Name"),
    iType = ix("Activity Type"), iDist = ix("Distance"), iMov = ix("Moving Time"),
    iEl = ix("Elapsed Time"), iMax = ix("Max Heart Rate"), iAvg = ix("Average Heart Rate"),
    iElev = ix("Elevation Gain"), iCal = ix("Calories"), iSrc = ix("Source"),
    iCad = ix("Average Cadence"), iMaxCad = ix("Max Cadence"), iStride = ix("Stride Length"),
    iMaxSpd = ix("Max Speed"), iAte = ix("Aerobic TE"), iAnte = ix("Anaerobic TE"),
    iVo2 = ix("VO2max"), iDetail = ix("Detail File");
  const acts: Activity[] = [];
  for (let r = 1; r < lines.length; r++) {
    const c = parseCsvLine(lines[r]);
    const num = (i: number) => {
      const v = i >= 0 ? c[i] : "";
      if (!v) return undefined;
      const n = parseFloat(v);
      return isNaN(n) ? undefined : n;
    };
    acts.push({
      id: c[iId] ?? "", date: parseDate(c[iDate] ?? ""), name: c[iName] ?? "",
      type: c[iType] ?? "", distanceKm: num(iDist), movingS: num(iMov), elapsedS: num(iEl),
      maxHr: num(iMax), avgHr: num(iAvg), elevGain: num(iElev), calories: num(iCal),
      source: c[iSrc] ?? "garmin",
      avgCadence: num(iCad), maxCadence: num(iMaxCad), strideM: num(iStride),
      maxSpeedMs: num(iMaxSpd), aerobicTe: num(iAte), anaerobicTe: num(iAnte), vo2max: num(iVo2),
      detailFile: iDetail >= 0 && c[iDetail] ? c[iDetail] : undefined,
    });
  }
  return acts;
}

export function fmtDuration(sec?: number): string | undefined {
  if (sec == null) return undefined;
  const s = Math.round(sec);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
    : `${m}:${String(ss).padStart(2, "0")}`;
}

export function filterActs(acts: Activity[], o: {
  sport_type?: string; start_date?: string; end_date?: string; name_contains?: string;
}): Activity[] {
  let out = acts;
  if (o.sport_type) { const s = o.sport_type.toLowerCase(); out = out.filter((a) => a.type.toLowerCase() === s); }
  if (o.name_contains) { const q = o.name_contains.toLowerCase(); out = out.filter((a) => a.name.toLowerCase().includes(q)); }
  if (o.start_date) { const t = new Date(o.start_date + "T00:00:00Z").getTime(); out = out.filter((a) => a.date && a.date.getTime() >= t); }
  if (o.end_date) { const t = new Date(o.end_date + "T23:59:59Z").getTime(); out = out.filter((a) => a.date && a.date.getTime() <= t); }
  return out;
}

export function summarize(acts: Activity[]) {
  const sum = (f: (a: Activity) => number | undefined) => acts.reduce((t, a) => t + (f(a) ?? 0), 0);
  const hrs = acts.map((a) => a.avgHr).filter((x): x is number => x != null);
  return {
    activities: acts.length,
    total_distance_km: Math.round(sum((a) => a.distanceKm) * 100) / 100,
    total_moving_time: fmtDuration(sum((a) => a.movingS)) ?? "0:00",
    total_elevation_gain_m: Math.round(sum((a) => a.elevGain) * 10) / 10,
    total_calories: Math.round(sum((a) => a.calories)) || null,
    avg_hr: hrs.length ? Math.round((hrs.reduce((t, x) => t + x, 0) / hrs.length) * 10) / 10 : null,
  };
}

export function toSummary(a: Activity) {
  const pace = a.distanceKm && a.movingS && a.distanceKm > 0
    ? fmtDuration(a.movingS / a.distanceKm) + "/km" : undefined;
  return {
    id: a.id, date: a.date ? a.date.toISOString().slice(0, 10) : null, name: a.name,
    type: a.type, distance_km: a.distanceKm ?? null, moving_time: fmtDuration(a.movingS) ?? null,
    pace: pace ?? null, avg_hr: a.avgHr ?? null, elevation_gain_m: a.elevGain ?? null,
    avg_cadence: a.avgCadence ?? null,
    has_detail: !!a.detailFile,
  };
}

/** Full activity row (everything the CSV holds), for get_activity_detail. */
export function toFull(a: Activity) {
  return {
    ...toSummary(a),
    elapsed_time: fmtDuration(a.elapsedS) ?? null,
    max_hr: a.maxHr ?? null,
    calories: a.calories ?? null,
    max_cadence: a.maxCadence ?? null,
    avg_stride_length_m: a.strideM ?? null,
    max_speed_ms: a.maxSpeedMs ?? null,
    aerobic_training_effect: a.aerobicTe ?? null,
    anaerobic_training_effect: a.anaerobicTe ?? null,
    vo2max: a.vo2max ?? null,
    source: a.source,
  };
}

export function bucketKey(a: Activity, by: string): string | null {
  if (by === "sport") return a.type || "Unknown";
  if (!a.date) return null;
  const y = a.date.getUTCFullYear(), m = a.date.getUTCMonth() + 1;
  if (by === "year") return `${y}`;
  if (by === "month") return `${y}-${String(m).padStart(2, "0")}`;
  return null;
}

// ---------------------------------------------------------------------------
// Daily health (data/health/daily.csv, written by pipeline/sources/garmin_health.py)
// ---------------------------------------------------------------------------

export interface HealthDay {
  date: string;
  sleep_score?: number; sleep_quality?: string; sleep_hours?: number;
  deep_min?: number; light_min?: number; rem_min?: number; awake_min?: number; nap_min?: number;
  bedtime?: string; wake_time?: string; sleep_avg_spo2?: number; sleep_avg_respiration?: number;
  resting_hr?: number; hrv_last_night?: number; hrv_weekly_avg?: number; hrv_status?: string;
  body_battery_high?: number; body_battery_low?: number; body_battery_change?: number;
  avg_stress?: number; max_stress?: number; steps?: number;
  training_readiness?: number; readiness_level?: string; readiness_note?: string;
}

const HEALTH_COLS: Array<[keyof HealthDay, string, "n" | "s"]> = [
  ["sleep_score", "Sleep Score", "n"], ["sleep_quality", "Sleep Quality", "s"],
  ["sleep_hours", "Sleep Hours", "n"], ["deep_min", "Deep Min", "n"], ["light_min", "Light Min", "n"],
  ["rem_min", "REM Min", "n"], ["awake_min", "Awake Min", "n"], ["nap_min", "Nap Min", "n"],
  ["bedtime", "Bedtime", "s"], ["wake_time", "Wake Time", "s"],
  ["sleep_avg_spo2", "Sleep Avg SpO2", "n"], ["sleep_avg_respiration", "Sleep Avg Respiration", "n"],
  ["resting_hr", "Resting HR", "n"], ["hrv_last_night", "HRV Last Night", "n"],
  ["hrv_weekly_avg", "HRV Weekly Avg", "n"], ["hrv_status", "HRV Status", "s"],
  ["body_battery_high", "Body Battery High", "n"], ["body_battery_low", "Body Battery Low", "n"],
  ["body_battery_change", "Body Battery Change", "n"], ["avg_stress", "Avg Stress", "n"],
  ["max_stress", "Max Stress", "n"], ["steps", "Steps", "n"],
  ["training_readiness", "Training Readiness", "n"], ["readiness_level", "Readiness Level", "s"],
  ["readiness_note", "Readiness Note", "s"],
];

export function parseHealthCsv(text: string): HealthDay[] {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 2) return [];
  const header = parseCsvLine(lines[0]);
  const iDate = header.indexOf("Date");
  const idx = HEALTH_COLS.map(([k, h, t]) => [k, header.indexOf(h), t] as const);
  const out: HealthDay[] = [];
  for (let r = 1; r < lines.length; r++) {
    const c = parseCsvLine(lines[r]);
    const d: Record<string, unknown> = { date: c[iDate] ?? "" };
    if (!d.date) continue;
    for (const [k, i, t] of idx) {
      const v = i >= 0 ? c[i] : "";
      if (!v) continue;
      if (t === "n") { const n = parseFloat(v); if (!isNaN(n)) d[k] = n; }
      else d[k] = v;
    }
    out.push(d as unknown as HealthDay);
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

export function filterHealth(days: HealthDay[], o: { start_date?: string; end_date?: string }) {
  let out = days;
  if (o.start_date) out = out.filter((d) => d.date >= o.start_date!);
  if (o.end_date) out = out.filter((d) => d.date <= o.end_date!);
  return out;
}

export function healthAverages(days: HealthDay[]) {
  const avg = (k: keyof HealthDay, nd = 1) => {
    const xs = days.map((d) => d[k]).filter((x): x is number => typeof x === "number");
    if (!xs.length) return null;
    const m = xs.reduce((t, x) => t + x, 0) / xs.length;
    return Math.round(m * 10 ** nd) / 10 ** nd;
  };
  return {
    days: days.length,
    days_with_sleep: days.filter((d) => d.sleep_hours != null).length,
    avg_sleep_score: avg("sleep_score", 0), avg_sleep_hours: avg("sleep_hours", 2),
    avg_deep_min: avg("deep_min", 0), avg_rem_min: avg("rem_min", 0),
    avg_resting_hr: avg("resting_hr", 1), avg_hrv_last_night: avg("hrv_last_night", 0),
    avg_body_battery_high: avg("body_battery_high", 0), avg_stress: avg("avg_stress", 0),
    avg_steps: avg("steps", 0), avg_training_readiness: avg("training_readiness", 0),
  };
}
