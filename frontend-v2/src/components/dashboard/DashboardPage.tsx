import React from 'react';
import { SystemStats } from '../../types/system';
import { ClientStats } from '../../types/client';
import { CircularGauge } from './CircularGauge';
import { SpeedCard } from './SpeedCard';
import { TrafficBarChart } from './TrafficBarChart';
import { SystemInfoCard } from './SystemInfoCard';
import { ClientTable } from './ClientTable';
import { Activity } from 'lucide-react';

interface DashboardPageProps {
  stats?: SystemStats;
  clients?: ClientStats[];
  onOpenQr?: (client: ClientStats) => void;
  onCopyLinks?: (client: ClientStats) => void;
  onEditClient?: (client: ClientStats) => void;
  onDeleteClient?: (client: ClientStats) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  stats,
  clients = [],
  onOpenQr,
  onCopyLinks,
  onEditClient,
  onDeleteClient,
}) => {
  return (
    <div className="space-y-8 animate-fade-in">
      {/* SECTION 1: Resource Gauges & Speeds */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Resource Gauges Box */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-[#0f1426]/70 backdrop-blur-xl border border-white/10 space-y-6 shadow-xl">
          <div className="flex justify-between items-center pb-3 border-b border-white/10">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-purple-400" /> Использование ресурсов
            </h3>
            <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> LIVE
            </span>
          </div>

          {/* 4 Circular Progress Rings */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-black/20 p-4 rounded-xl border border-white/5">
            <CircularGauge
              percent={stats?.cpu_percent ?? 11.5}
              label="Загрузка CPU"
              sublabel={`${stats?.cpu_percent ?? 11.5}%`}
              color="#06b6d4"
            />
            <CircularGauge
              percent={stats?.memory_percent ?? 23.2}
              label="Использование RAM"
              sublabel={`${(stats?.memory_used_mb ?? 900) / 1000} / ${((stats?.memory_total_mb ?? 3800) / 1000).toFixed(1)} GB`}
              color="#38bdf8"
            />
            <CircularGauge
              percent={stats?.swap_percent ?? 0.1}
              label="SWAP"
              sublabel={`${(stats?.swap_used_mb ?? 0) / 1000} / ${((stats?.swap_total_mb ?? 500) / 1000).toFixed(1)} GB`}
              color="#f59e0b"
            />
            <CircularGauge
              percent={stats?.disk_percent ?? 28.6}
              label="Диск"
              sublabel={`${stats?.disk_used_gb ?? 16.0} / ${stats?.disk_total_gb ?? 55.0} GB`}
              color="#10b981"
            />
          </div>

          {/* Real-time Speed Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SpeedCard
              type="download"
              speedKbps={stats?.download_speed_kbps}
              fallbackValue="243.27 KB/s"
            />
            <SpeedCard
              type="upload"
              speedKbps={stats?.upload_speed_kbps}
              fallbackValue="240.02 KB/s"
            />
          </div>

          {/* 30-Day Traffic Bar Chart */}
          <TrafficBarChart history={stats?.daily_traffic_history} />
        </div>

        {/* System Information Details Card */}
        <SystemInfoCard stats={stats} />
      </div>

      {/* SECTION 2: Full Client List Table ("Список клиентов") */}
      <ClientTable
        clients={clients}
        onOpenQr={onOpenQr}
        onCopyLinks={onCopyLinks}
        onEditClient={onEditClient}
        onDeleteClient={onDeleteClient}
      />
    </div>
  );
};
