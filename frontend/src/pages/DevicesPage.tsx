import { useState, useMemo } from "react";
import { Search, RefreshCw, ScanSearch, AlertCircle } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DeviceTable } from "@/components/DeviceTable";
import { DeviceDetailDialog } from "@/components/DeviceDetailDialog";
import { useDevices } from "@/hooks/useApi";
import {
  useTrustDevice, useBlockDevice, useScanPorts, useForceNetworkScan,
} from "@/hooks/useDevices";
import { useQuarantine } from "@/hooks/useQuarantine";
import { extractErrorMessage } from "@/lib/api";
import type { Device } from "@/lib/types";

type FilterKey = "all" | "trusted" | "blocked" | "unmarked";

export default function DevicesPage() {
  const devices = useDevices();
  const trustMutation = useTrustDevice();
  const blockMutation = useBlockDevice();
  const scanMutation = useScanPorts();
  const networkScan = useForceNetworkScan();
  const quarantine = useQuarantine();

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [detailDevice, setDetailDevice] = useState<Device | null>(null);

  // Filtrado de dispositivos según búsqueda y filtro activo
  const filtered = useMemo(() => {
    const list = devices.data || [];
    return list.filter(d => {
      // Filtro de búsqueda (IP, MAC, hostname, vendor)
      if (search) {
        const q = search.toLowerCase();
        const matchesSearch =
          (d.ip || "").toLowerCase().includes(q) ||
          d.mac.toLowerCase().includes(q) ||
          (d.hostname || "").toLowerCase().includes(q) ||
          (d.vendor || "").toLowerCase().includes(q);
        if (!matchesSearch) return false;
      }
      // Filtro por estado
      switch (filter) {
        case "trusted":  return d.is_trusted;
        case "blocked":  return d.is_blocked;
        case "unmarked": return !d.is_trusted && !d.is_blocked;
        default:         return true;
      }
    });
  }, [devices.data, search, filter]);

  // Handlers de acciones
  const handleTrust = (d: Device) => {
    trustMutation.mutate({ id: d.id, trusted: !d.is_trusted });
  };

  const handleBlock = (d: Device) => {
    blockMutation.mutate({ id: d.id, blocked: !d.is_blocked });
  };

  const handleScan = (d: Device) => {
    scanMutation.mutate({ id: d.id });
  };

  return (
    <div className="container py-8 space-y-6">
      {/* Cabecera */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dispositivos</h1>
          <p className="text-muted-foreground mt-1">
            Gestiona los dispositivos detectados en tu red
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => networkScan.mutate()}
            disabled={networkScan.isPending}
          >
            <ScanSearch className="h-4 w-4 mr-2" />
            Escanear red
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => devices.refetch()}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refrescar
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Lista de dispositivos</CardTitle>
          <CardDescription>
            {devices.data?.length ?? 0} dispositivos detectados en total
          </CardDescription>

          {/* Buscador y filtros */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por IP, MAC, nombre o fabricante…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            <div className="flex gap-1">
              {(["all", "trusted", "blocked", "unmarked"] as FilterKey[]).map(k => (
                <Button
                  key={k}
                  variant={filter === k ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFilter(k)}
                >
                  {k === "all"     && "Todos"}
                  {k === "trusted" && "Confiables"}
                  {k === "blocked" && "Bloqueados"}
                  {k === "unmarked" && "Sin marcar"}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {blockMutation.isError && (
            <div className="flex gap-2 items-start text-sm text-destructive bg-destructive/10 p-3 rounded-md mb-4">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{extractErrorMessage(blockMutation.error)}</span>
            </div>
          )}
          {devices.isLoading ? (
            <p className="text-center py-12 text-muted-foreground">
              Cargando dispositivos…
            </p>
          ) : (
            <DeviceTable
              devices={filtered}
              onTrust={handleTrust}
              onBlock={handleBlock}
              onScan={handleScan}
              onView={setDetailDevice}
              quarantineEnabled={quarantine.data?.enabled ?? false}
              scanningId={
                scanMutation.isPending
                  ? (scanMutation.variables?.id ?? null)
                  : null
              }
            />
          )}
        </CardContent>
      </Card>

      {/* Modal de detalle */}
      <DeviceDetailDialog
        device={detailDevice}
        onClose={() => setDetailDevice(null)}
      />
    </div>
  );
}
