export interface PageStateProps {
  kind: "loading" | "empty" | "error";
  message: string;
  onRetry?: () => void;
}

/** The shared loading / empty / error block, so every screen shows these states the same way. */
export function PageState({ kind, message, onRetry }: PageStateProps) {
  return (
    <div className={`page-state page-state--${kind}`} role={kind === "error" ? "alert" : "status"}>
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
