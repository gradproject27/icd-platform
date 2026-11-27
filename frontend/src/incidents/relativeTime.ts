const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** Compact relative text for an ISO timestamp; `now` is injectable for deterministic tests. */
export function formatRelativeTime(iso: string, now = Date.now()): string {
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return "Time unavailable";

  const seconds = Math.round((timestamp - now) / 1_000);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.34524, "week"],
    [12, "month"],
    [Number.POSITIVE_INFINITY, "year"],
  ];
  let value = seconds;
  for (const [limit, unit] of units) {
    if (Math.abs(value) < limit) return formatter.format(value, unit);
    value = Math.round(value / limit);
  }
  return formatter.format(value, "year");
}
