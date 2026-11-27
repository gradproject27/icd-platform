import type { KeyboardEvent, MouseEvent, ReactNode } from "react";

export type DataTableColumn<T> = {
  key: string;
  header: ReactNode;
  renderCell: (row: T) => ReactNode;
  ariaSort?: "ascending" | "descending" | "none" | "other";
  rowHeader?: boolean;
  cellTitle?: (row: T) => string | undefined;
};

type DataTableProps<T> = {
  caption: string;
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  className?: string;
  captionClassName?: string;
  onRowActivate?: (row: T) => void;
  rowLabel?: (row: T) => string;
};

const isInteractive = (target: EventTarget | null): boolean =>
  target instanceof Element && target.closest("a, button, input, select, textarea, [contenteditable='true']") !== null;

/** Shared semantic table with optional click and keyboard activation for a row. */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  className = "",
  captionClassName = "sr-only",
  onRowActivate,
  rowLabel,
}: DataTableProps<T>) {
  const activate = (row: T, event: MouseEvent<HTMLTableRowElement> | KeyboardEvent<HTMLTableRowElement>) => {
    if (!onRowActivate || isInteractive(event.target)) return;
    onRowActivate(row);
  };

  return (
    <div className="data-table-wrap">
      <table className={`table data-table ${className}`.trim()}>
        <caption className={captionClassName}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" aria-sort={column.ariaSort}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              tabIndex={onRowActivate ? 0 : undefined}
              aria-label={rowLabel?.(row)}
              className={onRowActivate ? "data-table__row--interactive" : undefined}
              onClick={(event) => activate(row, event)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                if (isInteractive(event.target)) return;
                event.preventDefault();
                activate(row, event);
              }}
            >
              {columns.map((column) =>
                column.rowHeader ? (
                  <th key={column.key} scope="row" title={column.cellTitle?.(row)}>
                    {column.renderCell(row)}
                  </th>
                ) : (
                  <td key={column.key} title={column.cellTitle?.(row)}>
                    {column.renderCell(row)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
