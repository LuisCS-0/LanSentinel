import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import MainLayout from "@/components/layout/MainLayout";
import { AuthGate } from "@/components/AuthGate";
import DashboardPage from "@/pages/DashboardPage";
import DevicesPage from "@/pages/DevicesPage";
import AlertsPage from "@/pages/AlertsPage";
import FirewallPage from "@/pages/FirewallPage";
import TrafficPage from "@/pages/TrafficPage";

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
              <Route path="traffic" element={<TrafficPage />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="firewall" element={<FirewallPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthGate>
    </QueryClientProvider>
  );
}
