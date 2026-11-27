import { formatLocalDateTime } from "../countdown/clock";
import { formatListTime } from "../incidents/format";
import { formatRelativeTime } from "../incidents/relativeTime";

export function RelativeAbsoluteTime({ iso, absoluteTitle }: { iso: string; absoluteTitle?: string }) {
  const absolute = formatLocalDateTime(iso);
  const relative = formatRelativeTime(iso);
  return (
    <time dateTime={iso} aria-label={`${relative}, ${absolute}`}>
      <span className="time-relative">{relative}</span>
      <span className="time-separator" aria-hidden="true">
        {" · "}
      </span>
      <span title={absoluteTitle ?? absolute}>{formatListTime(iso)}</span>
    </time>
  );
}
