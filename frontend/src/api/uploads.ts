import type { UploadAccepted } from "./c1";
import { API_BASE_URL, parseJson } from "./client";
import { ApiError, c1ErrorOf } from "./errors";

export const FILE_TOO_LARGE_MESSAGE = "The file is larger than the upload limit.";

/**
 * POST /uploads (docs/api-upload-jobs.md section 3). The second network entry point next to
 * request(): fetch reports no upload progress, so this uses XMLHttpRequest. There is no client
 * timeout, because a large upload takes longer than request()'s 5 seconds; the caller cancels
 * through `signal`. Content-Type is left to the browser, which adds the multipart boundary.
 */
export function uploadFile(
  datasetId: string,
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<UploadAccepted> {
  return new Promise((resolve, reject) => {
    const abortError = () => new DOMException("The upload was cancelled.", "AbortError");
    if (signal?.aborted) {
      reject(abortError());
      return;
    }

    const form = new FormData();
    form.append("dataset_id", datasetId);
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    const onAbortSignal = () => xhr.abort();
    const done = () => signal?.removeEventListener("abort", onAbortSignal);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      done();
      const body = parseJson(xhr.responseText);
      if (xhr.status === 202) {
        if (body === undefined) {
          reject(new ApiError("parse", "The ICD API sent a response that is not valid JSON."));
        } else {
          resolve(body as UploadAccepted);
        }
        return;
      }
      const c1Error = c1ErrorOf(body);
      if (xhr.status === 413 && c1Error === undefined) {
        // nginx answers an oversized body itself, with HTML (docs/api-upload-jobs.md section 3).
        reject(new ApiError("http", FILE_TOO_LARGE_MESSAGE, { status: 413, body, code: "file_too_large" }));
        return;
      }
      reject(
        new ApiError("http", c1Error?.message ?? `The ICD API answered with HTTP ${xhr.status}.`, {
          status: xhr.status,
          body,
          code: c1Error?.code,
        }),
      );
    };
    xhr.onerror = () => {
      done();
      reject(new ApiError("network", "Cannot reach the ICD API."));
    };
    xhr.onabort = () => {
      done();
      reject(abortError());
    };

    signal?.addEventListener("abort", onAbortSignal);
    xhr.open("POST", `${API_BASE_URL}/uploads`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.send(form);
  });
}
