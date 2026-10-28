/** Helpers for the upload page. The server still checks everything; these only spare a pointless upload. */

/** 536870912 -> "512 MB", 1536 -> "1.5 KB". Binary units, as the API's MAX_UPLOAD_MB. */
export function formatBytes(bytes: number): string {
  const units = ["bytes", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  if (unit === 0) return `${bytes} ${bytes === 1 ? "byte" : "bytes"}`;
  const rounded = Math.round(value * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)} ${units[unit]}`;
}

/** The lower-case extension with its dot, as in accepted_extensions; "" when there is none. */
export function extensionOf(fileName: string): string {
  const dot = fileName.lastIndexOf(".");
  return dot > 0 ? fileName.slice(dot).toLowerCase() : "";
}

export const FILE_EMPTY_MESSAGE = "The file is empty.";

export function notAcceptedMessage(acceptedExtensions: readonly string[]): string {
  return `This file type is not accepted. Accepted: ${acceptedExtensions.join(", ")}.`;
}

/** Why the browser refuses this file before sending it, or null when it may be sent. */
export function checkFile(
  file: Pick<File, "name" | "size">,
  acceptedExtensions: readonly string[],
  maxUploadBytes: number,
  tooLargeMessage: string,
): string | null {
  if (!acceptedExtensions.includes(extensionOf(file.name))) return notAcceptedMessage(acceptedExtensions);
  if (file.size === 0) return FILE_EMPTY_MESSAGE;
  if (file.size > maxUploadBytes) return tooLargeMessage;
  return null;
}
