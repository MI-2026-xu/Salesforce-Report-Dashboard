"use client";

/**
 * ResultChart — renders bar or pie chart from SOQL aggregate results.
 *
 * Pie: percentage labels inside each slice (white text), full names in legend.
 * Bar: coloured bars, rotated X-axis labels, K-suffix on Y axis.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const COLOURS = [
  "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
  "#8B5CF6", "#06B6D4", "#F97316", "#84CC16",
  "#EC4899", "#6B7280",
];

const RADIAN = Math.PI / 180;

interface PieLabelProps {
  cx?: number;
  cy?: number;
  midAngle?: number;
  innerRadius?: number;
  outerRadius?: number;
  percent?: number;
}

/** Renders the % value inside the slice. Skips slices < 5% to avoid clutter. */
function PieLabel({
  cx = 0, cy = 0, midAngle = 0,
  innerRadius = 0, outerRadius = 0, percent = 0,
}: PieLabelProps) {
  if (percent < 0.05) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x} y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={12}
      fontWeight={600}
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

interface Props {
  rows: Record<string, unknown>[];
  chartType: "bar" | "pie";
}

export default function ResultChart({ rows, chartType }: Props) {
  if (!rows.length) return null;

  const fields = Object.keys(rows[0]);
  const labelField = fields.find((f) => typeof rows[0][f] === "string") ?? fields[0];
  const valueField = fields.find((f) => typeof rows[0][f] === "number") ?? fields[1];

  const data = rows.map((r) => ({
    name: String(r[labelField] ?? ""),
    value: Number(r[valueField] ?? 0),
  }));

  // Shorten legend labels > 20 chars to keep layout clean
  const shortName = (s: string) => s.length > 22 ? s.slice(0, 20) + "…" : s;

  return (
    <div className="px-4 pt-4 pb-2">
      <ResponsiveContainer width="100%" height={300}>
        {chartType === "pie" ? (
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="42%"
              outerRadius={100}
              dataKey="value"
              nameKey="name"
              labelLine={false}
              label={(props) => <PieLabel {...props} />}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLOURS[i % COLOURS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v) => [Number(v ?? 0).toLocaleString(), valueField]}
            />
            <Legend
              formatter={(value) => (
                <span className="text-xs text-gray-600">{shortName(value)}</span>
              )}
              wrapperStyle={{ paddingTop: "8px", fontSize: "12px" }}
            />
          </PieChart>
        ) : (
          <BarChart
            data={data}
            margin={{ top: 4, right: 12, left: 0, bottom: 48 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: "#6B7280" }}
              angle={-35}
              textAnchor="end"
              interval={0}
              height={60}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6B7280" }}
              tickFormatter={(v: number) =>
                v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M`
                : v >= 1_000   ? `${(v / 1_000).toFixed(0)}k`
                : String(v)
              }
              width={45}
            />
            <Tooltip
              formatter={(v) => [Number(v ?? 0).toLocaleString(), valueField]}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={60}>
              {data.map((_, i) => (
                <Cell key={i} fill={COLOURS[i % COLOURS.length]} />
              ))}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
