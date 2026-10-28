import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import type { DatasetList, IntakeCounts, Job, UploadAccepted } from "../api/c1";
import { getDatasets } from "../api/datasets";
import { ApiError } from "../api/errors";
import { FILE_TOO_LARGE_MESSAGE, uploadFile } from "../api/uploads";
import { PageState } from "../components/PageState";
import { useJob } from "../hooks/useJob";
import { checkFile, formatBytes } from "../upload/format";

// Upload page (wireframes.md 4.2) on C1's upload and job API (docs/api-upload-jobs.md).
// The job ID is kept in the URL (?job=), so a refresh keeps following the same job and never
// uploads again.

type DatasetsState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; list: DatasetList };

type UploadPhase =
  | { kind: "idle" }
  | { kind: "uploading"; fraction: number }
  | { kind: "rejected"; fileName: string; message: string }
  | { kind: "failed"; message: string };

const numberFormat = new Intl.NumberFormat("en-US");
const formatCount = (value: number) => numberFormat.format(value);

export function UploadPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const jobId = searchParams.get("job");

  const [datasets, setDatasets] = useState<DatasetsState>({ kind: "loading" });
  const [datasetsAttempt, setDatasetsAttempt] = useState(0);
  const [datasetId, setDatasetId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [localError, setLocalError] = useState<string | null>(null);
  const [phase, setPhase] = useState<UploadPhase>({ kind: "idle" });
  const [accepted, setAccepted] = useState<UploadAccepted | null>(null);
  const uploadController = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDatasets(controller.signal).then(
      (list) => setDatasets({ kind: "ready", list }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setDatasets({ kind: "error", message: `Could not load the dataset sources. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [datasetsAttempt]);

  // Leaving the page cancels an upload in progress.
  useEffect(() => () => uploadController.current?.abort(), []);

  const retryDatasets = () => {
    setDatasets({ kind: "loading" });
    setDatasetsAttempt((attempt) => attempt + 1);
  };

  const clearFile = () => {
    setFile(null);
    setFileInputKey((key) => key + 1);
    setLocalError(null);
  };

  const startOver = () => {
    clearFile();
    setPhase({ kind: "idle" });
    setAccepted(null);
    setSearchParams({}, { replace: true });
  };

  const send = async (list: DatasetList, chosen: File) => {
    const refusal = checkFile(chosen, list.accepted_extensions, list.max_upload_bytes, FILE_TOO_LARGE_MESSAGE);
    setLocalError(refusal);
    if (refusal !== null) return;

    const controller = new AbortController();
    uploadController.current = controller;
    setPhase({ kind: "uploading", fraction: 0 });
    try {
      const result = await uploadFile(
        datasetId,
        chosen,
        (fraction) => setPhase({ kind: "uploading", fraction }),
        controller.signal,
      );
      setAccepted(result);
      setPhase({ kind: "idle" });
      setSearchParams({ job: result.job_id }, { replace: true });
    } catch (error) {
      if (controller.signal.aborted) {
        setPhase({ kind: "idle" });
      } else if (error instanceof ApiError && error.kind === "http" && error.status !== undefined && error.status < 500) {
        setPhase({ kind: "rejected", fileName: chosen.name, message: error.message });
      } else {
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setPhase({ kind: "failed", message: reason });
      }
    } finally {
      uploadController.current = null;
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>, list: DatasetList) => {
    event.preventDefault();
    if (file !== null && datasetId !== "") void send(list, file);
  };

  return (
    <section>
      <h1>Upload logs</h1>
      <p>Upload a dataset file. ICD parses it and stores its events; correlation into incidents follows in Week 3.</p>

      {jobId !== null ? (
        <JobPanel jobId={jobId} acceptedUploadId={accepted?.job_id === jobId ? accepted.upload_id : null} onStartOver={startOver} />
      ) : datasets.kind === "loading" ? (
        <PageState kind="loading" message="Loading dataset sources…" />
      ) : datasets.kind === "error" ? (
        <PageState kind="error" message={datasets.message} onRetry={retryDatasets} />
      ) : datasets.list.items.length === 0 ? (
        <PageState kind="empty" message="No dataset source is registered." />
      ) : (
        <UploadForm
          list={datasets.list}
          datasetId={datasetId}
          file={file}
          fileInputKey={fileInputKey}
          phase={phase}
          localError={localError}
          onDataset={setDatasetId}
          onFile={(chosen) => {
            setFile(chosen);
            setLocalError(null);
            setPhase({ kind: "idle" });
          }}
          onSubmit={(event) => onSubmit(event, datasets.list)}
          onCancel={() => uploadController.current?.abort()}
          onChooseAnother={() => {
            clearFile();
            setPhase({ kind: "idle" });
          }}
          onRetry={() => {
            if (file !== null) void send(datasets.list, file);
          }}
        />
      )}
    </section>
  );
}

interface UploadFormProps {
  list: DatasetList;
  datasetId: string;
  file: File | null;
  fileInputKey: number;
  phase: UploadPhase;
  localError: string | null;
  onDataset: (datasetId: string) => void;
  onFile: (file: File | null) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  onChooseAnother: () => void;
  onRetry: () => void;
}

function UploadForm(props: UploadFormProps) {
  const { list, datasetId, file, phase } = props;
  const uploading = phase.kind === "uploading";
  const chosen = list.items.find((item) => item.dataset_id === datasetId);
  const ready = datasetId !== "" && file !== null;
  const percent = uploading ? Math.round(phase.fraction * 100) : 0;

  return (
    <>
      <form className="upload-form" onSubmit={props.onSubmit}>
        <label className="field">
          Dataset source
          <select value={datasetId} disabled={uploading} onChange={(event) => props.onDataset(event.target.value)}>
            <option value="">Choose a dataset source</option>
            {list.items.map((item) => (
              <option key={item.dataset_id} value={item.dataset_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {chosen && !chosen.parser_available && (
          <p className="note">No parser yet: the job will fail with no_parser.</p>
        )}

        <label className="field">
          File
          <input
            key={props.fileInputKey}
            type="file"
            accept={list.accepted_extensions.join(",")}
            disabled={uploading}
            onChange={(event) => props.onFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <p className="note">
          Accepted: {list.accepted_extensions.join(", ")}. Maximum size: {formatBytes(list.max_upload_bytes)}.
        </p>

        {!ready && !uploading && <p className="note">Choose a dataset source and a file.</p>}
        {props.localError && (
          <p className="upload-error" role="alert">
            {props.localError}
          </p>
        )}

        <div className="upload-actions">
          <button type="submit" disabled={!ready || uploading}>
            Upload
          </button>
          {uploading && (
            <button type="button" onClick={props.onCancel}>
              Cancel
            </button>
          )}
        </div>
      </form>

      <div aria-live="polite">
        {uploading && (
          <div className="upload-progress">
            <p>Uploading… {percent}%</p>
            <div
              className="progress"
              role="progressbar"
              aria-label="Upload progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
            >
              <div className="progress__bar" style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}
      </div>

      {phase.kind === "rejected" && (
        <div className="box box--bad" role="alert">
          <h2>Upload rejected</h2>
          <p>
            {phase.fileName} was not accepted. Nothing was stored.
          </p>
          <p>Reason: {phase.message}</p>
          <button type="button" onClick={props.onChooseAnother}>
            Choose another file
          </button>
        </div>
      )}
      {phase.kind === "failed" && (
        <PageState kind="error" message={`Upload failed. The file was not processed. ${phase.message}`} onRetry={props.onRetry} />
      )}
    </>
  );
}

type StepStatus = "done" | "current" | "not yet" | "not reached" | "from Week 3";

interface Step {
  label: string;
  status: StepStatus;
}

/** The wireframe's processing steps on C1's job states (docs/api-upload-jobs.md, "Wireframe stages"). */
function processingSteps(job: Job | null): Step[] {
  const state = job?.state;
  const stage = job?.stage;
  const parsing = state === "running" && (stage === "parsing" || stage === "storing");
  const validating = state === "queued" || (state === "running" && !parsing);
  const failed = state === "failed";
  const later: StepStatus = failed ? "not reached" : "not yet";

  return [
    { label: "Uploaded", status: "done" },
    {
      label: "Validating",
      status: job === null ? "not yet" : validating ? "current" : parsing || state === "done" ? "done" : later,
    },
    { label: "Parsing", status: parsing ? "current" : state === "done" ? "done" : later },
    { label: "Correlation (from Week 3)", status: "from Week 3" },
    { label: "Done", status: state === "done" ? "done" : later },
  ];
}

interface JobPanelProps {
  jobId: string;
  acceptedUploadId: string | null;
  onStartOver: () => void;
}

function JobPanel({ jobId, acceptedUploadId, onStartOver }: JobPanelProps) {
  const { job, connectionLost, notFound } = useJob(jobId);
  const uploadId = job?.upload_id ?? acceptedUploadId;

  if (notFound) {
    return (
      <>
        <PageState kind="error" message="Job not found." />
        <button type="button" onClick={onStartOver}>
          Upload another file
        </button>
      </>
    );
  }

  return (
    <div className="processing" aria-live="polite">
      <h2>Processing</h2>
      <dl className="ids">
        <dt>Job ID</dt>
        <dd>
          <code className="copyable">{jobId}</code>
        </dd>
        {uploadId && (
          <>
            <dt>Upload ID</dt>
            <dd>
              <code className="copyable">{uploadId}</code>
            </dd>
          </>
        )}
      </dl>

      {connectionLost && <p className="note">Connection lost, retrying…</p>}
      {job === null && !connectionLost && <p className="note">Loading the job status…</p>}

      <ol className="steps" aria-label="Processing steps">
        {processingSteps(job).map((step) => (
          <li key={step.label} className={`steps__item steps__item--${step.status.replace(/ /g, "-")}`}>
            {step.label}: <span className="steps__status">{step.status}</span>
          </li>
        ))}
      </ol>

      {job?.counts && <Counts counts={job.counts} />}

      {job?.state === "done" && job.counts && job.counts.quarantined > 0 && <QuarantineBox counts={job.counts} />}

      {job?.state === "done" && (
        <div className="next-step">
          <p>
            <Link to="/incidents">View incidents</Link>
          </p>
          <p className="note">Incidents appear after correlation (Week 3).</p>
          <button type="button" onClick={onStartOver}>
            Upload another file
          </button>
        </div>
      )}

      {job?.state === "failed" && job.error && (
        <div className="box box--bad" role="alert">
          <h2>Processing failed</h2>
          <p>{job.error.message}</p>
          <p>Error code: {job.error.code}</p>
          <p>
            Attempts: {job.attempts} of {job.max_attempts}
          </p>
          {job.kind === "ingest" && <p>Nothing from this upload was stored.</p>}
          <button type="button" onClick={onStartOver}>
            Upload another file
          </button>
        </div>
      )}
    </div>
  );
}

function Counts({ counts }: { counts: IntakeCounts }) {
  return (
    <dl className="counts" aria-label="Intake summary">
      <dt>Records read</dt>
      <dd>{formatCount(counts.records_read)}</dd>
      <dt>Events stored</dt>
      <dd>{formatCount(counts.events_stored)}</dd>
      <dt>Labelled</dt>
      <dd>
        {formatCount(counts.flagged + counts.unflagged)}
        <span className="counts__detail">
          flagged {formatCount(counts.flagged)}, unflagged {formatCount(counts.unflagged)}
        </span>
      </dd>
      <dt>Unlabelled</dt>
      <dd>
        {formatCount(counts.unlabelled)}
        <span className="counts__detail">never guessed</span>
      </dd>
      <dt>Quarantined</dt>
      <dd>{formatCount(counts.quarantined)}</dd>
    </dl>
  );
}

function QuarantineBox({ counts }: { counts: IntakeCounts }) {
  const reasons = Object.entries(counts.quarantined_by_reason ?? {})
    .map(([code, count]) => [code, count ?? 0] as const)
    .sort(([codeA, a], [codeB, b]) => b - a || codeA.localeCompare(codeB));

  return (
    <div className="box box--warn">
      <h2>Done, with rejected records</h2>
      <p>
        Events stored {formatCount(counts.events_stored)} of {formatCount(counts.records_read)} records.{" "}
        {formatCount(counts.quarantined)} records were quarantined:
      </p>
      <table className="table" aria-label="Quarantined records by reason">
        <thead>
          <tr>
            <th scope="col">Reason code</th>
            <th scope="col">Records</th>
          </tr>
        </thead>
        <tbody>
          {reasons.map(([code, count]) => (
            <tr key={code}>
              <td>
                <code>{code}</code>
              </td>
              <td>{formatCount(count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
