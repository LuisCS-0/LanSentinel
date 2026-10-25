// Buscador global (Ctrl+K o "/"): salta a cualquier dispositivo, página o
// acción frecuente sin pasar por los menús. Se maneja con el teclado.

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Moon, Plus, Radar, Search, Sun, type LucideIcon } from "lucide-react";
import { Kbd } from "@/components/ui/misc";
import { useBodyScrollLock } from "@/components/ui/overlay";
import { NAV_ITEMS } from "@/components/layout/nav";
import { useDevices } from "@/hooks/useApi";
import { useDeviceSheet } from "@/hooks/useDeviceSheet";
import { useForceNetworkScan } from "@/hooks/useDevices";
import { deviceIcon, deviceName } from "@/lib/devices";
import { setTheme, useIsDark } from "@/lib/theme";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

interface Item {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  keywords: string;
  run: () => void;
}

const MAX_RESULTS = 40;

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <PaletteBody onClose={onClose} /> : null;
}

function PaletteBody({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const devices = useDevices();
  const sheet = useDeviceSheet();
  const scan = useForceNetworkScan();
  const dark = useIsDark();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  useBodyScrollLock(true);
  const openDevice = sheet.open;
  const scanNow = scan.mutate;

  const items = useMemo<Item[]>(() => {
    const deviceItems: Item[] = (devices.data ?? []).map(d => ({
      id: `device-${d.id}`,
      group: "Dispositivos",
      label: deviceName(d),
      hint: d.ip ?? d.mac,
      icon: deviceIcon(d),
      keywords: `${d.hostname ?? ""} ${d.vendor ?? ""} ${d.ip ?? ""} ${d.mac}`,
      run: () => openDevice(d.id),
    }));
    const pages: Item[] = NAV_ITEMS.map(p => ({
      id: `page-${p.to}`,
      group: "Ir a",
      label: p.label,
      hint: p.description,
      icon: p.icon,
      keywords: `${p.label} ${p.description} ${p.keywords ?? ""}`,
      run: () => navigate(p.to),
    }));
    const actions: Item[] = [
      {
        id: "scan", group: "Acciones", label: "Escanear la red ahora", icon: Radar, keywords: "arp buscar nuevos dispositivos",
        run: () => scanNow(undefined, { onSuccess: () => toast({ title: "Escaneo de la red lanzado", description: "Los dispositivos nuevos aparecerán en unos segundos." }) }),
      },
      {
        id: "block", group: "Acciones", label: "Bloquear una IP…", icon: Plus, keywords: "cortafuegos firewall regla",
        run: () => navigate("/firewall?block=1"),
      },
      {
        id: "theme", group: "Acciones", label: dark ? "Cambiar a tema claro" : "Cambiar a tema oscuro",
        icon: dark ? Sun : Moon, keywords: "tema apariencia modo oscuro claro",
        run: () => setTheme(dark ? "light" : "dark"),
      },
    ];
    return [...deviceItems, ...pages, ...actions];
  }, [devices.data, navigate, openDevice, scanNow, dark]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      // Sin texto: acciones y páginas primero, luego algunos dispositivos
      return [...items.filter(i => i.group !== "Dispositivos"), ...items.filter(i => i.group === "Dispositivos").slice(0, 8)];
    }
    const words = q.split(/\s+/);
    return items
      .filter(i => words.every(w => `${i.label} ${i.keywords}`.toLowerCase().includes(w)))
      .slice(0, MAX_RESULTS);
  }, [items, query]);

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  const run = (item: Item | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex(i => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex(i => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(results[index]);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  let lastGroup = "";
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      <div className="absolute inset-0 animate-fade-in bg-background/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-xl animate-zoom-in overflow-hidden rounded-2xl border bg-card shadow-2xl">
        <div className="flex items-center gap-3 border-b px-4">
          <Search className="size-4 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={e => { setQuery(e.target.value); setIndex(0); }}
            onKeyDown={onKeyDown}
            placeholder="Busca un dispositivo, una IP, una página…"
            className="h-14 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/70"
          />
          <Kbd>Esc</Kbd>
        </div>
        <div ref={listRef} className="max-h-[50vh] overflow-y-auto p-2">
          {results.length === 0 && (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">Sin resultados para «{query}».</p>
          )}
          {results.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <div key={item.id}>
                {header && <p className="px-3 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{header}</p>}
                <button
                  data-index={i}
                  onMouseMove={() => setIndex(i)}
                  onClick={() => run(item)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm",
                    i === index ? "bg-primary/10 text-foreground" : "text-foreground/90",
                  )}
                >
                  <item.icon className={cn("size-4 shrink-0", i === index ? "text-primary" : "text-muted-foreground")} />
                  <span className="truncate font-medium">{item.label}</span>
                  {item.hint && <span className="ml-auto truncate pl-3 font-mono text-xs text-muted-foreground">{item.hint}</span>}
                  {i === index && <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" />}
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4 border-t bg-muted/30 px-4 py-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> moverse</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> abrir</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
