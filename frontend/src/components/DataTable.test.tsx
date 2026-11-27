import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataTable, type DataTableColumn } from "./DataTable";

type Row = { id: string; state: string };
const rows = [
  { id: "inc-1", state: "Open" },
  { id: "inc-2", state: "Closed" },
];
const columns: DataTableColumn<Row>[] = [
  { key: "id", header: "ID", renderCell: (row) => row.id },
  { key: "state", header: "State", renderCell: (row) => row.state },
];

describe("DataTable", () => {
  it("renders accessible column headers, caption, and rows", () => {
    render(<DataTable caption="Incident queue" columns={columns} rows={rows} rowKey={(row) => row.id} />);

    expect(screen.getByRole("table", { name: "Incident queue" })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual(["ID", "State"]);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("activates a row by click, Enter, or Space and ignores interactive children", () => {
    const activate = vi.fn();
    const interactiveColumns: DataTableColumn<Row>[] = [
      {
        key: "id",
        header: "ID",
        renderCell: (row) => <a href={`/incidents/${row.id}`}>{row.id}</a>,
      },
    ];
    render(
      <DataTable
        caption="Incident queue"
        columns={interactiveColumns}
        rows={rows.slice(0, 1)}
        rowKey={(row) => row.id}
        rowLabel={(row) => row.id}
        onRowActivate={activate}
      />,
    );
    const row = screen.getByRole("row", { name: "inc-1" });
    fireEvent.click(row);
    expect(activate).toHaveBeenCalledWith(rows[0]);
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.keyDown(row, { key: " " });
    expect(activate).toHaveBeenCalledTimes(3);
    fireEvent.keyDown(screen.getByRole("link", { name: "inc-1" }), { key: "Enter" });
    expect(activate).toHaveBeenCalledTimes(3);
  });
});
