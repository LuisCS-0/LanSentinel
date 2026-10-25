// Gráfica de barras apiladas con el consumo histórico (descarga + subida)
// por horas, días o meses. Se usa en la página de tráfico y en el detalle
// de cada dispositivo.

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { es } from "date-fns/locale";
import { formatBytes } from "@/lib/format";
import type { UsageBucket, UsageUnit } from "@/lib/types";

// Etiqueta corta del eje y etiqueta larga del tooltip según el tramo
const AXIS_FORMAT: Record<UsageUnit, string> = {
  hour: "HH:mm",
  day: "dd/MM",
  month: "MMM yy",
};
const TOOLTIP_FORMAT: Record<UsageUnit, string> = {
  hour: "EEEE d 'de' MMMM, HH:mm",
  day: "EEEE d 'de' MMMM",
  month: "MMMM 'de' yyyy",
};

interface UsageChartProps {
  buckets: UsageBucket[];
  unit: UsageUnit;
  height?: number;
}

export function UsageChart({ buckets, unit, height = 260 }: UsageChartProps) {
  const data = buckets.map(b => ({
    start: b.start,
    recv: b.bytes_recv,
    sent: b.bytes_sent,
  }));

  const formatDate = (iso: string, pattern: string) => {
    try {
      return format(parseISO(iso), pattern, { locale: es });
    } catch {
      return iso;
    }
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
        <XAxis
          dataKey="start"
          tickFormatter={(v: string) => formatDate(v, AXIS_FORMAT[unit])}
          tick={{ fontSize: 11 }}
          minTickGap={16}
        />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatBytes(v)} width={70} />
        <Tooltip
          formatter={(value) => formatBytes(Number(value) || 0)}
          labelFormatter={(v) => formatDate(String(v), TOOLTIP_FORMAT[unit])}
          labelStyle={{ fontSize: 12 }}
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="recv" name="Descarga" stackId="usage" fill="#10b981" />
        <Bar dataKey="sent" name="Subida" stackId="usage" fill="#3b82f6" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
