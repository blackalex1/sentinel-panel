import React from 'react';
import { SystemStats } from '../../types/system';
import { Server, Activity, Upload, Download, Globe, Gauge, ShieldCheck } from 'lucide-react';
import { XrayIcon, HysteriaIcon, SingboxIcon } from '../common/CoreIcons';

interface SystemInfoCardProps {
  stats?: SystemStats;
}

export const SystemInfoCard: React.FC<SystemInfoCardProps> = ({ stats }) => {
  return (
    <div className="p-6 rounded-2xl bg-[#0f1426]/70 backdrop-blur-xl border border-white/10 space-y-4 shadow-xl flex flex-col justify-start h-full">
      {/* Header */}
      <div className="flex justify-between items-center pb-3 border-b border-white/10">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Server className="w-5 h-5 text-cyan-400" /> Системная информация
        </h3>
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" /> Stealth Guard
        </span>
      </div>

      {/* System Metrics List */}
      <div className="space-y-2.5 text-xs flex-1">
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-400" /> Аптайм сервера
          </span>
          <span className="font-bold text-white font-mono">
            {stats?.uptime_seconds ? `${Math.floor(stats.uptime_seconds / 3600)}ч ${Math.floor((stats.uptime_seconds % 3600) / 60)}м` : '92ч 57м'}
          </span>
        </div>

        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <Upload className="w-4 h-4 text-cyan-400" /> Исходящий трафик
          </span>
          <span className="font-bold text-cyan-300 font-mono">
            {stats?.total_upload_gb ? `${stats.total_upload_gb.toFixed(2)} GB` : '107.4 GB'}
          </span>
        </div>

        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <Download className="w-4 h-4 text-emerald-400" /> Входящий трафик
          </span>
          <span className="font-bold text-emerald-300 font-mono">
            {stats?.total_download_gb ? `${stats.total_download_gb.toFixed(2)} GB` : '101.78 GB'}
          </span>
        </div>

        {/* Xray Core Official SVG Status & Version */}
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <XrayIcon className="w-4 h-4 text-cyan-400" /> Статус Xray
          </span>
          <span className={`font-bold px-2 py-0.5 rounded-full text-[10px] uppercase ${stats?.cores_status?.xray ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
            {stats?.cores_status?.xray ? 'Запущен' : 'Остановлен'}
          </span>
        </div>
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <XrayIcon className="w-4 h-4 text-cyan-400 opacity-60" /> Версия Xray
          </span>
          <span className="font-bold text-cyan-300 font-mono">{stats?.cores_status?.xray_version || '—'}</span>
        </div>

        {/* Hysteria 2 Core Official SVG Status & Version */}
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <HysteriaIcon className="w-4 h-3.5 text-emerald-400" /> Статус Hysteria 2
          </span>
          <span className={`font-bold px-2 py-0.5 rounded-full text-[10px] uppercase ${stats?.cores_status?.hysteria ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
            {stats?.cores_status?.hysteria ? 'Запущен' : 'Остановлен'}
          </span>
        </div>
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <HysteriaIcon className="w-4 h-3.5 text-emerald-400 opacity-60" /> Версия Hysteria
          </span>
          <span className="font-bold text-emerald-300 font-mono">{stats?.cores_status?.hysteria_version || '—'}</span>
        </div>

        {/* sing-box Core Official SVG Status & Version */}
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <SingboxIcon className="w-4 h-4" /> Статус sing-box
          </span>
          <span className={`font-bold px-2 py-0.5 rounded-full text-[10px] uppercase ${stats?.cores_status?.singbox ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
            {stats?.cores_status?.singbox ? 'Запущен' : 'Остановлен'}
          </span>
        </div>
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <SingboxIcon className="w-4 h-4 opacity-60" /> Версия sing-box
          </span>
          <span className="font-bold text-amber-300 font-mono">{stats?.cores_status?.singbox_version || '—'}</span>
        </div>

        {/* Domain & BBR */}
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <Globe className="w-4 h-4 text-cyan-400" /> Адресация / SNI
          </span>
          <span className="font-bold text-cyan-300 font-mono text-[11px] truncate max-w-[150px]">
            {stats?.server_domain || '—'}
          </span>
        </div>
        <div className="flex justify-between items-center p-2.5 rounded-xl bg-white/[0.02] border border-white/5">
          <span className="text-slate-400 flex items-center gap-2">
            <Gauge className="w-4 h-4 text-emerald-400" /> Ускорение BBR
          </span>
          <span className={`font-bold ${stats?.bbr_enabled ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats?.bbr_enabled ? 'Активно' : 'Отключено'}
          </span>
        </div>
      </div>
    </div>
  );
};
