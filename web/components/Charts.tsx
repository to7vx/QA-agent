"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TrendPoint } from "@/lib/types";
import { fmtDate } from "@/lib/utils";

const AXIS = "#5b6678";
const GRID = "#161c26";
const ACCENT = "#34e0a1";

const tooltipStyle = {
  background: "#11161f",
  border: "1px solid #1d2430",
  borderRadius: 12,
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  boxShadow: "0 8px 30px -12px rgba(0,0,0,0.7)",
};

export function PassRateTrend({ data }: { data: TrendPoint[] }) {
  const series = data.map((d) => ({
    name: fmtDate(d.created_at),
    pass_rate: Math.round(d.pass_rate),
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={series} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
        <defs>
          <linearGradient id="passFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.32} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="name" stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis
          domain={[0, 100]}
          stroke={AXIS}
          fontSize={11}
          unit="%"
          tickLine={false}
          axisLine={false}
          width={42}
        />
        <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "#e9eef6" }} cursor={{ stroke: GRID }} />
        <Area
          type="monotone"
          dataKey="pass_rate"
          stroke={ACCENT}
          strokeWidth={2}
          fill="url(#passFill)"
          dot={{ r: 2.5, fill: ACCENT, strokeWidth: 0 }}
          activeDot={{ r: 4, fill: ACCENT }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const HEAL_COLORS: Record<string, string> = {
  healed: "#34e0a1",
  failed: "#ff6b6b",
  refused: "#f5c451",
  error: "#ff6b6b",
};

export function HealingBars({ data }: { data: Record<string, number> }) {
  const series = Object.entries(data).map(([outcome, count]) => ({ outcome, count }));
  if (series.length === 0) {
    return <p className="text-sm text-muted">No healing attempts recorded yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={series} margin={{ top: 10, right: 12, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="outcome"
          stroke={AXIS}
          fontSize={11}
          tickLine={false}
          axisLine={false}
          fontFamily="var(--font-mono)"
        />
        <YAxis allowDecimals={false} stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} width={28} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#11161f" }} />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={64}>
          {series.map((s) => (
            <Cell key={s.outcome} fill={HEAL_COLORS[s.outcome] ?? ACCENT} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
