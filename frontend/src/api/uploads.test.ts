import { describe, expect, it, vi } from "vitest";
import errorFormat from "../../../docs/api/examples/error-format-not-accepted.json";
import uploadAccepted from "../../../docs/api/examples/upload-accepted.json";
import { mockXhr } from "../test/fakeXhr";
import { ApiError } from "./errors";
import { FILE_TOO_LARGE_MESSAGE, uploadFile } from "./uploads";

const file = () => new File(["[]"], "events.json", { type: "application/json" });

describe("uploadFile", () => {
  it("posts multipart form data to /api/uploads and reports progress", async () => {
    const requests = mockXhr();
    const onProgress = vi.fn();

    const result = uploadFile("fixture", file(), onProgress);
    const xhr = requests[0]!;
    xhr.progress(21, 50);
    xhr.progress(50, 50);
    xhr.respond(202, uploadAccepted);

    await expect(result).resolves.toEqual(uploadAccepted);
    expect(onProgress.mock.calls).toEqual([[0.42], [1]]);
    expect([xhr.method, xhr.url]).toEqual(["POST", "/api/uploads"]);
    const form = xhr.body as FormData;
    expect(form.get("dataset_id")).toBe("fixture");
    expect((form.get("file") as File).name).toBe("events.json");
  });

  it("never sets Content-Type, so the browser adds the multipart boundary", async () => {
    const requests = mockXhr();
    const result = uploadFile("fixture", file(), () => {});
    requests[0]!.respond(202, uploadAccepted);
    await result;

    expect(requests[0]!.headers.has("content-type")).toBe(false);
  });

  it("turns C1's JSON error into an ApiError with C1's code and message", async () => {
    const requests = mockXhr();
    const result = uploadFile("fixture", file(), () => {});
    requests[0]!.respond(415, errorFormat);

    const error = await result.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: "http",
      status: 415,
      code: "format_not_accepted",
      message: errorFormat.error.message,
    });
  });

  it("treats the HTML 413 answer of nginx as file_too_large", async () => {
    const requests = mockXhr();
    const result = uploadFile("fixture", file(), () => {});
    requests[0]!.respond(413, "<html><body><h1>413 Request Entity Too Large</h1></body></html>");

    await expect(result).rejects.toMatchObject({
      kind: "http",
      status: 413,
      code: "file_too_large",
      message: FILE_TOO_LARGE_MESSAGE,
    });
  });

  it("reports a network error", async () => {
    const requests = mockXhr();
    const result = uploadFile("fixture", file(), () => {});
    requests[0]!.fail();

    await expect(result).rejects.toMatchObject({ kind: "network" });
  });

  it("aborts through the signal and rejects with an AbortError", async () => {
    const requests = mockXhr();
    const controller = new AbortController();
    const result = uploadFile("fixture", file(), () => {}, controller.signal);

    controller.abort();

    await expect(result).rejects.toMatchObject({ name: "AbortError" });
    expect(requests[0]!.aborted).toBe(true);
  });

  it("does not start when the signal is already aborted", async () => {
    const requests = mockXhr();
    const controller = new AbortController();
    controller.abort();

    await expect(uploadFile("fixture", file(), () => {}, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(requests).toHaveLength(0);
  });
});
