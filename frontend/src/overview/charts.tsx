import type { ReactNode } from "react";
import { Link } from "react-router";
import { formatLocalDateTime } from "../countdown/clock";
import type { TimeSeries } from "./metrics";

// Hand-written inline-SVG charts (decision D3). Every chart has a text alternative: the bar list
// and the legend are real tables or lists, and the time chart has a table under "Show as table".
// Colour is never the only signal: every bar has its label and count as text next to it.

export type BarRow = { key: string; label: string; count: number; to: string; tone: string; shape?: ReactNode };

/** Horizontal bars as a table: label, count (a link to the list behind it), bar. */
export function BarTable({ caption, rows }: { caption: string; rows: BarRow[] }) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  return (
    <table className="bar-table">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Group</th>
          <th scope="col">Incidents</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={`tone--${row.tone}`}>
            <th scope="row">
              {row.shape}
              {row.label}
            </th>
            <td className="bar-table__count">
              <Link to={row.to} aria-label={`${row.count} ${row.label} incidents`}>
                {row.count}
              </Link>
            </td>
            <td className="bar-table__bar" aria-hidden="true">
              <svg viewBox="0 0 100 10" preserveAspectRatio="none">
                <rect className="bar-table__track" x="0" y="1" width="100" height="8" rx="2" />
                {row.count > 0 && (
                  <rect className="bar-table__fill" x="0" y="1" width={(row.count / max) * 100} height="8" rx="2" />
                )}
              </svg>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** One stacked bar of shares, then a legend list with each count as a link. */
export function StackedBar({ label, rows }: { label: string; rows: BarRow[] }) {
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  let x = 0;
  const summary = rows.map((row) => `${row.label} ${row.count}`).join(", ");
  return (
    <div className="stacked">
      <svg className="stacked__bar" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label={`${label}: ${summary}`}>
        <rect className="stacked__track" x="0" y="0" width="100" height="8" rx="2" />
        {total > 0 &&
          rows
            .filter((row) => row.count > 0)
            .map((row) => {
              const width = (row.count / total) * 100;
              const rect = <rect key={row.key} className={`stacked__part tone--${row.tone}`} x={x} y="0" width={width} height="8" />;
              x += width;
              return rect;
            })}
      </svg>
      <ul className="legend">
        {rows.map((row) => (
          <li key={row.key} className={`tone--${row.tone}${row.count === 0 ? " legend__item--zero" : ""}`}>
            <span className="legend__swatch" aria-hidden="true" />
            <span className="legend__label">{row.label}</span>
            <Link to={row.to} className="legend__count" aria-label={`${row.count} ${row.label} incidents`}>
              {row.count}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

const bucketLabel = (start: number, unit: TimeSeries["unit"]) => {
  const text = formatLocalDateTime(new Date(start).toISOString());
  return unit === "hour" ? text.slice(0, 16) : text.slice(0, 10);
};

/** Columns per hour (or day), with axis labels at both ends and a table alternative. */
export function TimeColumns({ series, what }: { series: TimeSeries; what: string }) {
  const { buckets, unit } = series;
  const max = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const first = buckets[0];
  const last = buckets.at(-1);
  if (!first || !last) return null;
  const peak = buckets.reduce((best, bucket) => (bucket.count > best.count ? bucket : best), first);
  const width = buckets.length * 10;
  const summary =
    `${what} per ${unit}, from ${bucketLabel(first.start, unit)} to ${bucketLabel(last.start, unit)}. ` +
    `Highest: ${peak.count} at ${bucketLabel(peak.start, unit)}.`;

  return (
    <figure className="columns">
      <svg className="columns__chart" viewBox={`0 0 ${width} 60`} preserveAspectRatio="none" role="img" aria-label={summary}>
        <line className="columns__axis" x1="0" y1="59.5" x2={width} y2="59.5" />
        {buckets.map((bucket, index) => {
          const height = (bucket.count / max) * 54;
          return (
            <rect key={bucket.start} className="columns__bar" x={index * 10 + 1.5} y={59 - height} width="7" height={height}>
              <title>{`${bucketLabel(bucket.start, unit)}: ${bucket.count}`}</title>
            </rect>
          );
        })}
      </svg>
      <figcaption className="columns__axis-labels">
        <span>{bucketLabel(first.start, unit)}</span>
        <span>
          Highest {peak.count} per {unit}
        </span>
        <span>{bucketLabel(last.start, unit)}</span>
      </figcaption>
      <details className="columns__table">
        <summary>Show as table</summary>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{unit === "hour" ? "Hour (local, dataset time)" : "Day (local, dataset time)"}</th>
              <th scope="col">Incidents</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket) => (
              <tr key={bucket.start}>
                <td>{bucketLabel(bucket.start, unit)}</td>
                <td>{bucket.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
