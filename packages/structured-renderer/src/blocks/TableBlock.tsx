import { useMemo, useState } from "react";

import type {
  TableBlock as TableBlockContract,
  TableColumn,
} from "@vibedesk/contracts";

import { formatValue } from "../formatValue";
import { resolvePath } from "../resolvePath";

interface TableBlockProps {
  block: TableBlockContract;
  data: unknown;
  onRowSelect?: (blockId: string, row: Record<string, unknown>) => void;
}

interface SortState {
  key: string;
  direction: "ascending" | "descending";
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (row): row is Record<string, unknown> =>
      row !== null && typeof row === "object" && !Array.isArray(row),
  );
}

function compareValues(left: unknown, right: unknown): number {
  if (left === right) return 0;
  if (left === null || left === undefined) return 1;
  if (right === null || right === undefined) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;

  return String(left).localeCompare(String(right), "zh-CN", {
    numeric: true,
    sensitivity: "base",
  });
}

function nextDirection(column: TableColumn, sort: SortState | undefined) {
  if (!column.sortable) return undefined;
  if (sort?.key !== column.key) return "ascending" as const;
  return sort.direction === "ascending" ? "descending" : "ascending";
}

export function TableBlock({ block, data, onRowSelect }: TableBlockProps) {
  const [sort, setSort] = useState<SortState>();
  const rows = asRows(resolvePath(data, block.rowsPath));
  const sortedRows = useMemo(() => {
    if (!sort) return rows;

    const direction = sort.direction === "ascending" ? 1 : -1;
    return [...rows].sort(
      (left, right) => compareValues(left[sort.key], right[sort.key]) * direction,
    );
  }, [rows, sort]);

  return (
    <section
      className="vv-view-block vv-table-block"
      data-block-id={block.id}
      data-vibe-block="table"
      data-vibe-block-id={block.id}
      data-vibe-rows-path={block.rowsPath}
    >
      {block.title ? <h2>{block.title}</h2> : null}
      <div className="vv-table-scroll">
        <table>
          <thead>
            <tr>
              {block.columns.map((column) => {
                const direction = nextDirection(column, sort);
                const isSorted = sort?.key === column.key;

                return (
                  <th
                    aria-sort={isSorted ? sort.direction : undefined}
                    key={column.key}
                    scope="col"
                  >
                    {column.sortable && direction ? (
                      <button
                        aria-label={`按${column.label}${direction === "ascending" ? "升序" : "降序"}排列`}
                        onClick={() => setSort({ key: column.key, direction })}
                        type="button"
                      >
                        {column.label}
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length > 0 ? (
              sortedRows.map((row, rowIndex) => (
                <tr
                  className={onRowSelect ? "vv-selectable-row" : undefined}
                  key={rowIndex}
                  onClick={() => onRowSelect?.(block.id, row)}
                  onKeyDown={(event) => {
                    if (
                      onRowSelect &&
                      (event.key === "Enter" || event.key === " ")
                    ) {
                      event.preventDefault();
                      onRowSelect(block.id, row);
                    }
                  }}
                  tabIndex={onRowSelect ? 0 : undefined}
                >
                  {block.columns.map((column) => (
                    <td key={column.key}>{formatValue(row[column.key], column.format)}</td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={Math.max(block.columns.length, 1)}>
                  {block.emptyText || "—"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
