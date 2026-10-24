export function UploadPage() {
  return (
    <section>
      <h1>Upload logs</h1>
      <p>This page will let an analyst upload security log files for ingestion and correlation.</p>
      <label className="field">
        Log file
        <input type="file" disabled />
      </label>
      <p className="note">Upload is built in Week 2 (C2 ingestion).</p>
    </section>
  );
}
