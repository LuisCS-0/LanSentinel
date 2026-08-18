// Gráfica de área que muestra el consumo total de la red en tiempo real.
// Usa Recharts para el renderizado y los datos vienen del backend cada 5s.

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Activity } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { useTrafficHistory } from "@/hooks/useTrafficHistory";
import { formatBps } from "@/lib/format";

export function TrafficChart() {
  const { data, isLoading } = useTrafficHistory();

  // Adaptamos las muestras: secondsAgo como número para que el eje X
  // pueda tratarse como continuo y colocar marcadores a intervalos fijos.
  const chartData = (data || []).map(s => ({
    secondsAgo: Math.round(s.seconds_ago),
    rx: s.rx_bps,
    tx: s.tx_bps,
    total: s.total_bps,
  })).reverse();

  // Tasa actual (última muestra)
  const latest = chartData.length > 0 ? chartData[chartData.length - 1] : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-4 w-4" />
          Tráfico de la red
        </CardTitle>
        <CardDescription>
          {latest
            ? `Consumo actual: ${formatBps(latest.total)}`
            : "Recopilando datos…"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading || chartData.length === 0 ? (
          <p className="text-center py-12 text-muted-foreground text-sm">
            Esperando muestras del medidor de tráfico…
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <defs>
                <linearGradient id="colorRx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.6}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.05}/>
                </linearGradient>
                <linearGradient id="colorTx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.6}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05}/>
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="secondsAgo"
                type="number"
                domain={[600, 0]}
                ticks={[600, 540, 480, 420, 360, 300, 240, 180, 120, 60, 0]}
                tickFormatter={(v) => v === 0 ? "ahora" : `${v / 60}:00`}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => formatBps(v)}
              />
              <Tooltip
                formatter={(value) => formatBps(Number(value) || 0)}
                labelFormatter={(v) => v === 0 ? "Ahora mismo" : `Hace ${v}s`}
                labelStyle={{ fontSize: 12 }}
                contentStyle={{ fontSize: 12, borderRadius: 6 }}
              />

              <Area
                type="monotone"
                dataKey="rx"
                name="Descarga"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#colorRx)"
              />
              <Area
                type="monotone"
                dataKey="tx"
                name="Subida"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#colorTx)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}