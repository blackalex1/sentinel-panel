import React, { useState, useEffect } from 'react';
import { Sidebar, NavTab } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { DashboardPage } from './components/dashboard/DashboardPage';
import { InboundsPage } from './components/inbounds/InboundsPage';
import { ClientModal } from './components/inbounds/ClientModal';
import { CoreLogTerminal } from './components/cores/CoreLogTerminal';
import { RoutingPage } from './components/routing/RoutingPage';
import { SettingsPage } from './components/settings/SettingsPage';

import { Inbound, InboundFormData } from './types/inbound';
import { ClientStats, ClientFormData } from './types/client';
import { SystemStats } from './types/system';
import { api } from './services/api';

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [inbounds, setInbounds] = useState<Inbound[]>([]);
  const [clients, setClients] = useState<ClientStats[]>([]);

  const [systemStats, setSystemStats] = useState<SystemStats>({
    cpu_percent: 0,
    memory_percent: 0,
    memory_used_mb: 0,
    memory_total_mb: 0,
    swap_percent: 0,
    swap_used_mb: 0,
    swap_total_mb: 0,
    disk_percent: 0,
    disk_used_gb: 0,
    disk_total_gb: 0,
    uptime_seconds: 0,
    download_speed_kbps: 0,
    upload_speed_kbps: 0,
    total_download_gb: 0,
    total_upload_gb: 0,
    server_domain: '',
    bbr_enabled: false,
    cores_status: {
      xray: false,
      hysteria: false,
      singbox: false,
    },
    active_connections_count: 0,
  });

  const [selectedInboundForClients, setSelectedInboundForClients] = useState<Inbound | null>(null);
  const [clientModalOpen, setClientModalOpen] = useState(false);

  useEffect(() => {
    // Fetch live real data from backend API
    const loadData = async () => {
      try {
        const ibs = await api.getInbounds();
        if (ibs && Array.isArray(ibs)) setInbounds(ibs);

        const cls = await api.getClients();
        if (cls && Array.isArray(cls)) setClients(cls);

        const stats = await api.getSystemStats();
        if (stats) setSystemStats(stats);
      } catch (err) {
        // API error handled
      }
    };
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCreateInbound = async (data: InboundFormData) => {
    try {
      await api.createInbound(data as any);
      const updated = await api.getInbounds();
      setInbounds(updated);
    } catch (err) {
      // error handled
    }
  };

  const handleUpdateInbound = async (id: number, data: InboundFormData) => {
    try {
      await api.updateInbound(id, data as any);
      const updated = await api.getInbounds();
      setInbounds(updated);
    } catch (err) {
      // error handled
    }
  };

  const handleDeleteInbound = async (id: number) => {
    try {
      await api.deleteInbound(id);
      setInbounds(inbounds.filter((ib) => ib.id !== id));
    } catch (err) {
      setInbounds(inbounds.filter((ib) => ib.id !== id));
    }
  };

  const handleOpenClients = (ib: Inbound) => {
    setSelectedInboundForClients(ib);
    setClientModalOpen(true);
  };

  const handleAddClient = async (data: ClientFormData) => {
    try {
      await api.addClient(data);
      const updatedCls = await api.getClients();
      setClients(updatedCls);
    } catch (err) {
      // error handled
    }
    setClientModalOpen(false);
  };

  const getTitle = () => {
    switch (activeTab) {
      case 'dashboard': return 'Мониторинг ресурсов';
      case 'inbounds': return 'Подключения (Inbounds)';
      case 'xray': return 'Ядро Xray';
      case 'hysteria': return 'Ядро Hysteria 2';
      case 'singbox': return 'Ядро sing-box';
      case 'routing': return 'Правила маршрутизации';
      case 'settings': return 'Настройки системы';
      default: return 'Spectre Panel';
    }
  };

  return (
    <div className="flex bg-[#060812] text-slate-100 min-h-screen font-sans selection:bg-purple-500/30 selection:text-purple-200">
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab)}
        username="Admin"
      />

      {/* Main Content Area */}
      <main className="flex-1 p-8 overflow-y-auto max-h-screen">
        <Header title={getTitle()} coreStatus={systemStats.cores_status} />

        {activeTab === 'dashboard' && (
          <DashboardPage
            stats={systemStats}
            clients={clients}
            onOpenQr={(c) => alert(`QR код для ${c.email}`)}
            onCopyLinks={(c) => alert(`Ссылка для ${c.email} скопирована`)}
            onEditClient={(c) => {
              const ib = inbounds.find((i) => i.id === c.inbound_id) || inbounds[0];
              setSelectedInboundForClients(ib);
              setClientModalOpen(true);
            }}
            onDeleteClient={async (c) => {
              if (confirm(`Удалить клиента ${c.email}?`)) {
                try {
                  await api.deleteClient(c.email);
                } catch {
                  // ignore
                }
                setClients(clients.filter((cl) => cl.email !== c.email));
              }
            }}
          />
        )}

        {activeTab === 'inbounds' && (
          <InboundsPage
            inbounds={inbounds}
            onCreateInbound={handleCreateInbound}
            onUpdateInbound={handleUpdateInbound}
            onDeleteInbound={handleDeleteInbound}
            onOpenClients={handleOpenClients}
          />
        )}

        {activeTab === 'xray' && (
          <CoreLogTerminal
            coreName="xray"
            title="Логи и управление ядром Xray"
            onRestart={() => api.restartCore('xray')}
            onStop={() => api.stopCore('xray')}
          />
        )}

        {activeTab === 'hysteria' && (
          <CoreLogTerminal
            coreName="hysteria"
            title="Логи и управление ядром Hysteria 2"
            onRestart={() => api.restartCore('hysteria')}
            onStop={() => api.stopCore('hysteria')}
          />
        )}

        {activeTab === 'singbox' && (
          <CoreLogTerminal
            coreName="singbox"
            title="Логи и управление ядром sing-box"
            onRestart={() => api.restartCore('singbox')}
            onStop={() => api.stopCore('singbox')}
          />
        )}

        {activeTab === 'routing' && <RoutingPage />}
        {activeTab === 'settings' && <SettingsPage />}

        {/* Client Management Modal */}
        {selectedInboundForClients && (
          <ClientModal
            isOpen={clientModalOpen}
            onClose={() => setClientModalOpen(false)}
            onSubmit={handleAddClient}
            inboundId={selectedInboundForClients.id}
          />
        )}
      </main>
    </div>
  );
}

export default App;
