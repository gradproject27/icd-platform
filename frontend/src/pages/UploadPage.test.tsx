import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";
import datasetList from "../../../docs/api/examples/dataset-list.json";
import errorDatasetUnknown from "../../../docs/api/examples/error-dataset-unknown.json";
import jobDoneWithQuarantine from "../../../docs/api/examples/job-ingest-done-with-quarantine.json";
import jobDone from "../../../docs/api/examples/job-ingest-done.json";
import jobFailed from "../../../docs/api/examples/job-ingest-failed.json";
import jobQueued from "../../../docs/api/examples/job-ingest-queued.json";
import jobRunning from "../../../docs/api/examples/job-ingest-running.json";
import uploadAccepted from "../../../docs/api/examples/upload-accepted.json";
import { JOB_POLL_INTERVAL_MS } from "../hooks/useJob";
import { mockXhr } from "../test/fakeXhr";
import { jsonResponse, mockFetch } from "../test/fetch";
import { UploadPage } from "./UploadPage";

// The test data are C1's own examples (docs/api/examples); the app never imports them.

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/upload"
          element={
            <>
              <UploadPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

/** Serves GET /datasets, and GET /jobs/{id} from `jobs` in order (the last one repeats). */
function serveApi(jobs: unknown[] = []) {
  const fetchMock = mockFetch();
  let next = 0;
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/datasets") return jsonResponse(datasetList);
    if (path.startsWith("/api/jobs/")) {
      const job = jobs[Math.min(next, jobs.length - 1)];
      next += 1;
      return jsonResponse(job);
    }
    return jsonResponse({ error: { code: "not_found", message: "Not in this test." } }, 404);
  });
  return fetchMock;
}

const flush = () => act(() => vi.advanceTimersByTimeAsync(0));
const poll = () => act(() => vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS));

function chooseDataset(datasetId: string) {
  fireEvent.change(screen.getByLabelText("Dataset source"), { target: { value: datasetId } });
}

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText("File"), { target: { files: [file] } });
}

const jsonFile = (name = "events.json", content = "[]") => new File([content], name, { type: "application/json" });

describe("UploadPage", () => {
  it("lists the datasets from GET /datasets with the limits, and needs both choices", async () => {
    vi.useFakeTimers();
    serveApi();
    renderAt("/upload");
    expect(screen.getByText("Loading dataset sources…")).toBeInTheDocument();
    await flush();

    const select = screen.getByLabelText("Dataset source");
    for (const item of datasetList.items) {
      expect(within(select).getByRole("option", { name: item.name })).toBeInTheDocument();
    }
    expect(screen.getByText("Accepted: .csv, .json, .jsonl, .log, .txt. Maximum size: 512 MB.")).toBeInTheDocument();
    expect(screen.getByLabelText("File")).toHaveAttribute("accept", ".csv,.json,.jsonl,.log,.txt");

    const upload = screen.getByRole("button", { name: "Upload" });
    expect(upload).toBeDisabled();
    chooseDataset("fixture");
    expect(upload).toBeDisabled();
    chooseFile(jsonFile());
    expect(upload).toBeEnabled();

    chooseDataset("precinct6");
    expect(screen.getByText("No parser yet: the job will fail with no_parser.")).toBeInTheDocument();
  });

  it("refuses a wrong extension and an empty file before sending", async () => {
    vi.useFakeTimers();
    serveApi();
    const requests = mockXhr();
    renderAt("/upload");
    await flush();

    chooseDataset("fixture");
    chooseFile(new File(["M"], "tool.exe"));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This file type is not accepted. Accepted: .csv, .json, .jsonl, .log, .txt.",
    );

    chooseFile(jsonFile("empty.json", ""));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The file is empty.");
    expect(requests).toHaveLength(0);
  });

  it("uploads, follows the job to done and shows the counts and the quarantine box", async () => {
    vi.useFakeTimers();
    const doneWithQuarantine = {
      ...jobDoneWithQuarantine,
      job_id: uploadAccepted.job_id,
      upload_id: uploadAccepted.upload_id,
    };
    serveApi([jobQueued, jobRunning, doneWithQuarantine]);
    const requests = mockXhr();
    renderAt("/upload");
    await flush();

    chooseDataset("fixture");
    chooseFile(jsonFile());
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    const xhr = requests[0]!;
    act(() => xhr.progress(42, 100));
    expect(screen.getByText("Uploading… 42%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByLabelText("Dataset source")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();

    await act(async () => xhr.respond(202, uploadAccepted));
    await flush();
    expect(screen.getByTestId("location")).toHaveTextContent(`/upload?job=${uploadAccepted.job_id}`);
    expect(screen.getByText(uploadAccepted.job_id)).toBeInTheDocument();
    expect(screen.getByText(uploadAccepted.upload_id)).toBeInTheDocument();

    const steps = () => screen.getByRole("list", { name: "Processing steps" });
    expect(steps()).toHaveTextContent("Uploaded: done");
    expect(steps()).toHaveTextContent("Validating: current");
    expect(steps()).toHaveTextContent("Correlation (from Week 3): from Week 3");

    await poll();
    expect(steps()).toHaveTextContent("Parsing: current");
    const progress = screen.getByLabelText("Intake summary");
    expect(progress).toHaveTextContent("Records read20");
    expect(progress).toHaveTextContent("flagged 10, unflagged 9");

    await poll();
    expect(steps()).toHaveTextContent("Done: done");
    const summary = screen.getByLabelText("Intake summary");
    expect(summary).toHaveTextContent("Records read12,480");
    expect(summary).toHaveTextContent("Events stored12,455");
    expect(summary).toHaveTextContent("Labelled12,211");
    expect(summary).toHaveTextContent("flagged 1,210, unflagged 11,001");
    expect(summary).toHaveTextContent("Unlabelled244never guessed");
    expect(summary).toHaveTextContent("Quarantined25");

    expect(screen.getByRole("heading", { name: "Done, with rejected records" })).toBeInTheDocument();
    const rows = within(screen.getByRole("table", { name: "Quarantined records by reason" })).getAllByRole("row");
    expect(rows.slice(1).map((row) => row.textContent)).toEqual([
      "bad_timestamp12",
      "missing_required_field9",
      "invalid_ip4",
    ]);
    expect(screen.getByRole("link", { name: "View incidents" })).toHaveAttribute("href", "/incidents");
    expect(screen.getByText("Incidents appear after correlation (Week 3).")).toBeInTheDocument();
  });

  it("shows a failed job with the message and code from C1", async () => {
    vi.useFakeTimers();
    serveApi([jobFailed]);
    renderAt(`/upload?job=${jobFailed.job_id}`);
    await flush();

    expect(screen.getByRole("heading", { name: "Processing failed" })).toBeInTheDocument();
    expect(screen.getByText(jobFailed.error.message)).toBeInTheDocument();
    expect(screen.getByText("Error code: no_parser")).toBeInTheDocument();
    expect(screen.getByText("Attempts: 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("Nothing from this upload was stored.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Upload another file" }));
    await flush();
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/upload$/);
    expect(screen.getByLabelText("Dataset source")).toBeInTheDocument();
  });

  it("shows the rejected box when POST /uploads answers 422 dataset_unknown", async () => {
    vi.useFakeTimers();
    serveApi();
    const requests = mockXhr();
    renderAt("/upload");
    await flush();

    chooseDataset("fixture");
    chooseFile(jsonFile("auth.json"));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await act(async () => requests[0]!.respond(422, errorDatasetUnknown));

    const box = screen.getByRole("alert");
    expect(within(box).getByRole("heading", { name: "Upload rejected" })).toBeInTheDocument();
    expect(box).toHaveTextContent("auth.json was not accepted. Nothing was stored.");
    expect(box).toHaveTextContent(`Reason: ${errorDatasetUnknown.error.message}`);
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/upload$/);

    fireEvent.click(within(box).getByRole("button", { name: "Choose another file" }));
    expect(screen.queryByRole("heading", { name: "Upload rejected" })).not.toBeInTheDocument();
  });

  it("follows the job in ?job= on load and never uploads", async () => {
    vi.useFakeTimers();
    const fetchMock = serveApi([jobRunning, jobDone]);
    const requests = mockXhr();
    renderAt(`/upload?job=${jobRunning.job_id}`);
    await flush();

    expect(screen.getByText(jobRunning.job_id)).toBeInTheDocument();
    expect(screen.getByText(jobRunning.upload_id)).toBeInTheDocument();
    await poll();
    expect(screen.getByRole("list", { name: "Processing steps" })).toHaveTextContent("Done: done");
    expect(screen.getByLabelText("Intake summary")).toHaveTextContent("Records read37");

    // No POST /uploads (it only goes through XMLHttpRequest); fetch only read the job and datasets.
    expect(requests).toHaveLength(0);
    const paths = fetchMock.mock.calls.map(([url]) => String(url));
    expect(paths.filter((path) => path.startsWith("/api/jobs/"))).toEqual([
      `/api/jobs/${jobRunning.job_id}`,
      `/api/jobs/${jobRunning.job_id}`,
    ]);
    expect(paths.every((path) => path === "/api/datasets" || path.startsWith("/api/jobs/"))).toBe(true);
  });

  it("shows the error block with Retry when the datasets cannot be loaded", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fetchMock.mockImplementation(async () => jsonResponse({ ...datasetList, items: [] }));
    renderAt("/upload");
    await flush();

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the dataset sources. Cannot reach the ICD API.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await flush();
    expect(screen.getByText("No dataset source is registered.")).toBeInTheDocument();
  });
});
