import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import MainLayout from "@/components/layout/MainLayout";
import { AuthGate } from "@/components/AuthGate";
import DashboardPage from "@/pages/DashboardPage";
import DevicesPage from "@/pages/DevicesPage";
import AlertsPage from "@/pages/AlertsPage";
import FirewallPage from "@/pages/FirewallPage";
import TrafficPage from "@/pages/TrafficPage";
import ConnectionsPage from "@/pages/ConnectionsPage";
import SettingsPage from "@/pages/SettingsPage";
import AuditPage from "@/pages/AuditPage";
import { ExpertOnly } from "@/components/ExpertOnly";

// Cliente de React Query — configuración global de caché y reintentos
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,       // datos "frescos" durante 30 segundos
      retry: 1,                   // un solo reintento ante fallo
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Sin sesión se muestra el login en lugar del panel */}
      <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route element={<MainLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="devices" element={<DevicesPage />} />
              <Route path="connections" element={<ExpertOnly><ConnectionsPage /></ExpertOnly>} />
              <Route path="traffic" element={<ExpertOnly><TrafficPage /></ExpertOnly>} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="firewall" element={<ExpertOnly><FirewallPage /></ExpertOnly>} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthGate>
    </QueryClientProvider>
  );
}
