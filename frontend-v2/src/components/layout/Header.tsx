import React from 'react';
import { CoreStatus } from '../../types/system';
import { Lock } from 'lucide-react';
import { XrayIcon, HysteriaIcon, SingboxIcon } from '../common/CoreIcons';

interface HeaderProps {
  title: string;
  coreStatus?: CoreStatus;
}

export const Header: React.FC<HeaderProps> = ({ title, coreStatus }) => {
  return (
    <header className="flex justify-between items-center mb-8 pb-5 border-b border-white/10">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
          {title}
        </h1>
        <span className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-300 shadow-[0_0_12px_rgba(139,92,246,0.2)]">
          <Lock className="w-3 h-3 text-purple-400" /> Stealth Protected
        </span>
      </div>

      {/* Core Status Badges with Official SVG Logotypes */}
      <div className="flex items-center gap-3">
        {/* Xray Status */}
        <div
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all ${
            coreStatus?.xray
              ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}
        >
          <XrayIcon className="w-4 h-4 text-cyan-400" />
          <span
            className={`w-2 h-2 rounded-full ${
              coreStatus?.xray ? 'bg-cyan-400 animate-pulse shadow-[0_0_8px_#06b6d4]' : 'bg-rose-400'
            }`}
          />
          <span>Xray: {coreStatus?.xray ? 'Запущен' : 'Остановлен'}</span>
        </div>

        {/* Hysteria Status */}
        <div
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all ${
            coreStatus?.hysteria
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}
        >
          <HysteriaIcon className="w-4 h-3.5 text-emerald-400" />
          <span
            className={`w-2 h-2 rounded-full ${
              coreStatus?.hysteria ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_#10b981]' : 'bg-rose-400'
            }`}
          />
          <span>Hysteria 2: {coreStatus?.hysteria ? 'Активен' : 'Остановлен'}</span>
        </div>

        {/* Singbox Status */}
        <div
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all ${
            coreStatus?.singbox
              ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
          }`}
        >
          <SingboxIcon className="w-4 h-4" />
          <span
            className={`w-2 h-2 rounded-full ${
              coreStatus?.singbox ? 'bg-amber-400 animate-pulse shadow-[0_0_8px_#f59e0b]' : 'bg-rose-400'
            }`}
          />
          <span>sing-box: {coreStatus?.singbox ? 'Активен' : 'Остановлен'}</span>
        </div>
      </div>
    </header>
  );
};
