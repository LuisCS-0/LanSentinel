// Gráficas del panel (Recharts) con los colores del tema: descarga en el
// color principal y subida en violeta, igual en todas las pantallas.

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { es } from "date-fns/locale";
import { formatBps, formatBytes } from "@/lib/format";
import type { TrafficSample } from "@/hooks/useTrafficHistory";
import type { UsageBucket, UsageUnit } from "@/lib/types";

const DOWN = "hsl(var(--primary))";
const UP = "hsl(var(--upload))";
const GRID = "hsl(var(--border))";
const AXIS = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };

function ChartTooltip({ active, payload, label, labelFormatter, valueFormatter }: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string }[];
  label?: string | number;
  labelFormatter: (l: string | number) => string;
  valueFormatter: (v: number) => string;
}) {
  if (!active || !payload?.length || label === undefined) return null;
  return (
    <div className="rounded-lg border bg-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <p className="mb-1.5 font-medium capitalize">{labelFormatter(label)}</p>
      {payload.map(p => (
        <p key={p.name} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          {p.name}
          <span className="tabular ml-auto pl-4 font-mono text-foreground">{valueFormatter(Number(p.value) || 0)}</span>
        </p>
      ))}
    </div>
  );
}

// ─── Tráfico en directo (últimos 10 minutos) ────────────────────────────────

function toLiveSeries(samples: TrafficSample[] | undefined) {
  return (samples ?? [])
    .map(s => ({ secondsAgo: Math.round(s.seconds_ago), rx: s.rx_bps, tx: s.tx_bps }))
    .reverse();
}

export function LiveTrafficChart({ samples, height = 260 }: { samples: TrafficSample[] | undefined; height?: number }) {
  const data = toLiveSeries(samples);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="live-down" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={DOWN} stopOpacity={0.45} />
            <stop offset="100%" stopColor={DOWN} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="live-up" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={UP} stopOpacity={0.4} />
            <stop offset="100%" stopColor={UP} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 6" vertical={false} />
        <XAxis
          dataKey="secondsAgo" type="number" domain={[0, 600]} reversed
          ticks={[600, 480, 360, 240, 120, 0]}
          tickFormatter={v => (v === 0 ? "ahora" : `-${v / 60} min`)}
          tick={AXIS} axisLine={false} tickLine={false}
        />
        <YAxis tick={AXIS} tickFormatter={v => formatBps(v)} width={72} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={{ stroke: GRID }}
          content={<ChartTooltip labelFormatter={v => (v === 0 ? "Ahora mismo" : `Hace ${v} s`)} valueFormatter={formatBps} />}
        />
        <Area type="monotone" dataKey="rx" name="Descarga" stroke={DOWN} strokeWidth={2} fill="url(#live-down)" isAnimationActive={false} />
        <Area type="monotone" dataKey="tx" name="Subida" stroke={UP} strokeWidth={2} fill="url(#live-up)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// Mini gráfica sin ejes para las tarjetas de indicadores
export function Sparkline({ values, height = 36 }: { values: number[]; height?: number }) {
  const data = values.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={DOWN} stopOpacity={0.35} />
            <stop offset="100%" stopColor={DOWN} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area type="monotone" dataKey="v" stroke={DOWN} strokeWidth={1.5} fill="url(#spark)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ─── Consumo histórico (barras por hora, día o mes) ─────────────────────────

const AXIS_FORMAT: Record<UsageUnit, string> = { hour: "HH:mm", day: "dd/MM", month: "MMM yy" };
const TOOLTIP_FORMAT: Record<UsageUnit, string> = {
  hour: "EEEE d 'de' MMMM, HH:mm",
  day: "EEEE d 'de' MMMM",
  month: "MMMM 'de' yyyy",
};

function formatDate(iso: string, pattern: string) {
  try {
    return format(parseISO(iso), pattern, { locale: es });
  } catch {
    return iso;
  }
}

export function UsageChart({ buckets, unit, height = 260 }: { buckets: UsageBucket[]; unit: UsageUnit; height?: number }) {
  const data = buckets.map(b => ({ start: b.start, recv: b.bytes_recv, sent: b.bytes_sent }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 14, right: 8, left: 0, bottom: 0 }} barCategoryGap="18%">
        <CartesianGrid stroke={GRID} strokeDasharray="3 6" vertical={false} />
        <XAxis
          dataKey="start" tickFormatter={(v: string) => formatDate(v, AXIS_FORMAT[unit])}
          tick={AXIS} minTickGap={18} axisLine={false} tickLine={false}
        />
        <YAxis tick={AXIS} tickFormatter={(v: number) => formatBytes(v)} width={72} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={{ fill: "hsl(var(--muted) / 0.6)" }}
          content={<ChartTooltip labelFormatter={v => formatDate(String(v), TOOLTIP_FORMAT[unit])} valueFormatter={formatBytes} />}
        />
        <Bar dataKey="recv" name="Descarga" stackId="u" fill={DOWN} />
        <Bar dataKey="sent" name="Subida" stackId="u" fill={UP} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// Leyenda compacta común a las gráficas de tráfico
export function TrafficLegend() {
  return (
    <div className="flex items-center gap-4 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-primary" />Descarga</span>
      <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-upload" />Subida</span>
    </div>
  );
}
