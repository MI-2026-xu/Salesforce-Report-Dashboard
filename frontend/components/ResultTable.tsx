"use client";

/**
 * ResultTable — renders SOQL results as a clean, scrollable table.
 *
 * Features:
 *   - Column headers formatted: FirstName → First Name, ISCONVERTED → Is Converted
 *   - Salesforce Id column rendered in small monospace (not a prominent column)
 *   - Shows "X of Y total" when backend returned a subset
 *   - Truncates long cell values with a title tooltip
 */

interface Props {
  rows: Record<string, unknown>[];
  totalSize: number;
}

const MAX_CELL_LEN = 55;

/** Convert Salesforce field name to readable header label */
function formatHeader(key: string): string {
  if (key === "Id") return "ID";
  return (
    key
      // camelCase → words: "FirstName" → "First Name"
      .replace(/([A-Z])/g, " $1")
      // Remove leading space
      .trim()
      // Title-case each word
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString();
  const str = String(value);
  return str.length > MAX_CELL_LEN ? str.slice(0, MAX_CELL_LEN) + "…" : str;
}

export default function ResultTable({ rows, totalSize }: Props) {
  if (!rows.length) {
    return (
      <div className="p-6 text-center text-sm text-gray-400">
        No records found.
      </div>
    );
  }

  const columns = Object.keys(rows[0]);
  const isIdCol = (col: string) => col === "Id";

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              {columns.map((col) => (
                <th
                  key={col}
                  className={`px-4 py-2.5 text-left font-semibold tracking-wide whitespace-nowrap ${
                    isIdCol(col)
                      ? "text-xs text-gray-400 uppercase"
                      : "text-xs text-gray-500 uppercase"
                  }`}
                >
                  {formatHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-50 transition-colors">
                {columns.map((col) => (
                  <td
                    key={col}
                    title={String(row[col] ?? "")}
                    className={`px-4 py-2.5 whitespace-nowrap ${
                      isIdCol(col)
                        ? "font-mono text-xs text-gray-400"
                        : "text-gray-700"
                    }`}
                  >
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 text-xs text-gray-400">
        Showing {rows.length.toLocaleString()}
        {totalSize > rows.length && ` of ${totalSize.toLocaleString()} total`}{" "}
        record{rows.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}
