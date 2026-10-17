import { describe, it, expect } from "vitest";
import {
  parseCsv, summarize, filterActs, toSummary, bucketKey, fmtDuration,
  parseHealthCsv, filterHealth, healthAverages,
} from "../src/lib";

const CSV = [
  "Activity ID,Activity Date,Activity Name,Activity Type,Raw Sport,Distance,Filename,Moving Time,Elapsed Time,Max Heart Rate,Average Heart Rate,Elevation Gain,Average Speed,Average Watts,Calories,Source",
  "garmin-1,2026-06-01 06:30:00,Morning Run,Run,running,10,,3000,3100,180,160,50,3.33,,600,garmin",
  'garmin-2,2026-06-02 07:00:00,"Hill, Repeats",Run,running,8,,2400,2500,185,168,200,3.33,,500,garmin',
  "garmin-3,2026-05-20 08:00:00,Long Ride,Ride,cycling,40,,7200,7300,160,140,500,5.56,200,1200,garmin",
].join("\n");

describe("parseCsv", () => {
  const acts = parseCsv(CSV);
  it("parses every row", () => expect(acts).toHaveLength(3));
  it("handles a quoted field containing a comma", () =>
    expect(acts[1].name).toBe("Hill, Repeats"));
  it("reads numeric and date fields", () => {
    expect(acts[0].distanceKm).toBe(10);
    expect(acts[0].avgHr).toBe(160);
    expect(acts[0].date?.toISOString()).toBe("2026-06-01T06:30:00.000Z");
  });
  it("returns nothing for header-only input", () =>
    expect(parseCsv("a,b,c")).toHaveLength(0));
});

describe("parseCsv detail columns", () => {
  const CSV2 = [
    "Activity ID,Activity Date,Activity Name,Activity Type,Raw Sport,Distance,Filename,Moving Time,Elapsed Time,Max Heart Rate,Average Heart Rate,Elevation Gain,Average Speed,Average Watts,Calories,Source,Average Cadence,Max Cadence,Stride Length,Max Speed,Aerobic TE,Anaerobic TE,VO2max,Detail File",
    "garmin-9,2026-10-14 06:00:00,Run,Run,running,5.007,,2048,2100,150,127,28,2.44,,420,garmin,168.5,182,0.87,3.1,2.9,0.3,49,details/garmin-9.json",
  ].join("\n");
  const a = parseCsv(CSV2)[0];
  it("reads cadence/stride/TE/VO2max", () => {
    expect(a.avgCadence).toBe(168.5);
    expect(a.strideM).toBe(0.87);
    expect(a.aerobicTe).toBe(2.9);
    expect(a.vo2max).toBe(49);
    expect(a.detailFile).toBe("details/garmin-9.json");
  });
  it("summary exposes cadence and has_detail", () => {
    const s = toSummary(a);
    expect(s.avg_cadence).toBe(168.5);
    expect(s.has_detail).toBe(true);
  });
  it("old CSV without the columns still parses", () => {
    const old = parseCsv(CSV)[0];
    expect(old.avgCadence).toBeUndefined();
    expect(toSummary(old).has_detail).toBe(false);
  });
});

describe("summarize", () => {
  it("totals distance and averages heart rate", () => {
    const s = summarize(parseCsv(CSV));
    expect(s.activities).toBe(3);
    expect(s.total_distance_km).toBe(58);
    expect(s.avg_hr).toBe(156); // (160 + 168 + 140) / 3
  });
});

describe("filterActs", () => {
  const acts = parseCsv(CSV);
  it("filters by sport (case-insensitive)", () =>
    expect(filterActs(acts, { sport_type: "run" })).toHaveLength(2));
  it("filters by start date inclusive", () =>
    expect(filterActs(acts, { start_date: "2026-06-01" })).toHaveLength(2));
  it("filters by name substring", () =>
    expect(filterActs(acts, { name_contains: "hill" })).toHaveLength(1));
});

describe("toSummary", () => {
  it("computes pace per km", () =>
    expect(toSummary(parseCsv(CSV)[0]).pace).toBe("5:00/km")); // 3000s / 10km
});

describe("bucketKey", () => {
  const a = parseCsv(CSV)[0];
  it("buckets by month/year/sport", () => {
    expect(bucketKey(a, "month")).toBe("2026-06");
    expect(bucketKey(a, "year")).toBe("2026");
    expect(bucketKey(a, "sport")).toBe("Run");
  });
});

describe("fmtDuration", () => {
  it("formats with and without hours", () => {
    expect(fmtDuration(3661)).toBe("1:01:01");
    expect(fmtDuration(125)).toBe("2:05");
    expect(fmtDuration(undefined)).toBeUndefined();
  });
});

describe("daily health", () => {
  const H = [
    "Date,Sleep Score,Sleep Quality,Sleep Hours,Deep Min,Light Min,REM Min,Awake Min,Nap Min,Bedtime,Wake Time,Sleep Avg SpO2,Sleep Avg Respiration,Resting HR,HRV Last Night,HRV Weekly Avg,HRV Status,Body Battery High,Body Battery Low,Body Battery Change,Avg Stress,Max Stress,Steps,Training Readiness,Readiness Level,Readiness Note",
    "2026-10-14,75,FAIR,6.5,70,250,70,20,,23:10,05:40,96,14.1,52,45,46,BALANCED,88,20,52,30,90,9800,58,MODERATE,MODERATE_READY",
    "2026-10-15,81,GOOD,7,90,240,90,15,,22:00,05:00,96,14.2,51,48,46,BALANCED,92,23,58,27,88,10432,64,MODERATE,MODERATE_READY",
  ].join("\n");
  const days = parseHealthCsv(H);
  it("parses and sorts newest first", () => {
    expect(days).toHaveLength(2);
    expect(days[0].date).toBe("2026-10-15");
    expect(days[0].sleep_hours).toBe(7);
    expect(days[0].bedtime).toBe("22:00");
    expect(days[0].hrv_status).toBe("BALANCED");
  });
  it("filters by date and averages", () => {
    expect(filterHealth(days, { start_date: "2026-10-15" })).toHaveLength(1);
    const a = healthAverages(days);
    expect(a.avg_sleep_hours).toBe(6.75);
    expect(a.avg_resting_hr).toBe(51.5);
    expect(a.avg_training_readiness).toBe(61);
  });
  it("returns nothing for header-only", () => expect(parseHealthCsv("Date,Sleep Score")).toHaveLength(0));
});
