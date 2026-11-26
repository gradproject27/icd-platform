import { INCIDENT_SUBPAGE_LABELS, PAGE_LABELS } from "../labels";

/** One breadcrumb. The last one is the current page and has no link. */
export type Crumb = { label: string; to?: string; mono?: boolean };

const TOP_PAGES: Record<string, string> = {
  overview: PAGE_LABELS.overview,
  incidents: PAGE_LABELS.incidents,
  review: PAGE_LABELS.review,
  entities: PAGE_LABELS.entities,
  upload: PAGE_LABELS.upload,
  configuration: PAGE_LABELS.configuration,
};

const decode = (segment: string) => {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
};

/** Breadcrumbs for a route, built from the path alone (no data is read). */
export function breadcrumbsFor(pathname: string): Crumb[] {
  const [top, id, sub, ...rest] = pathname.split("/").filter(Boolean);
  if (top === undefined) return [];
  const topLabel = Object.hasOwn(TOP_PAGES, top) ? TOP_PAGES[top] : undefined;
  if (topLabel === undefined) return [{ label: PAGE_LABELS.notFound }];
  if (id === undefined) return [{ label: topLabel }];
  if (top !== "incidents" || rest.length > 0) return [{ label: PAGE_LABELS.notFound }];

  const incidentId = decode(id);
  const list: Crumb = { label: PAGE_LABELS.incidents, to: "/incidents" };
  if (sub === undefined) return [list, { label: incidentId, mono: true }];
  if (!Object.hasOwn(INCIDENT_SUBPAGE_LABELS, sub)) return [{ label: PAGE_LABELS.notFound }];
  return [
    list,
    { label: incidentId, to: `/incidents/${encodeURIComponent(incidentId)}`, mono: true },
    { label: INCIDENT_SUBPAGE_LABELS[sub as keyof typeof INCIDENT_SUBPAGE_LABELS] },
  ];
}
