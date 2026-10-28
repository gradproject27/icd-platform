import type { DatasetList } from "./c1";
import { request } from "./client";

/** GET /datasets: the dataset choices, accepted extensions and size limit for the upload form. */
export function getDatasets(signal?: AbortSignal): Promise<DatasetList> {
  return request<DatasetList>("/datasets", { signal });
}
