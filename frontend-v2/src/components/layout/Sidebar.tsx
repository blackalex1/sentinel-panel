import React from 'react';
import {
  LayoutDashboard,
  Network,
  Route,
  Settings as SettingsIcon,
  LogOut,
} from 'lucide-react';
import { SpectreLogoImg, XrayIcon, HysteriaIcon, SingboxIcon } from '../common/CoreIcons';

export type NavTab = 'dashboard' | 'inbounds' | 'xray' | 'hysteria' | 'singbox' | 'routing' | 'settings';

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  username?: string;
  onLogout?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  username = 'Admin',
  onLogout,
}) => {
  const menuItems = [
    { id: 'dashboard' as NavTab, label: 'Дашборд', icon: ({ className }: { className?: string }) => <LayoutDashboard className={className} /> },
    { id: 'inbounds' as NavTab, label: 'Подключения', icon: ({ className }: { className?: string }) => <Network className={className} /> },
    { id: 'xray' as NavTab, label: 'Ядро Xray', icon: ({ className }: { className?: string }) => <XrayIcon className={className || "w-4 h-4 text-cyan-400"} /> },
    { id: 'hysteria' as NavTab, label: 'Ядро Hysteria', icon: ({ className }: { className?: string }) => <HysteriaIcon className={className || "w-4 h-4 text-emerald-400"} /> },
    { id: 'singbox' as NavTab, label: 'Ядро sing-box', icon: ({ className }: { className?: string }) => <SingboxIcon className={className || "w-4 h-4 text-amber-400"} /> },
    { id: 'routing' as NavTab, label: 'Маршрутизация', icon: ({ className }: { className?: string }) => <Route className={className} /> },
    { id: 'settings' as NavTab, label: 'Настройки', icon: ({ className }: { className?: string }) => <SettingsIcon className={className} /> },
  ];

  return (
    <aside className="w-64 bg-[#0a0d1a]/80 border-r border-white/10 backdrop-blur-xl flex flex-col p-6 h-screen sticky top-0 z-20">
      {/* Brand Header with Official Spectre Logo SVG */}
      <div className="flex items-center gap-3 mb-8 px-2">
        <SpectreLogoImg className="w-10 h-10" />
        <div>
          <h2 className="font-extrabold text-lg tracking-wider bg-gradient-to-r from-white via-purple-300 to-cyan-400 bg-clip-text text-transparent">
            Spectre Panel
          </h2>
          <span className="text-[10px] font-bold uppercase tracking-widest text-purple-400/80 bg-purple-500/10 px-2 py-0.5 rounded-full border border-purple-500/20">
            React v2 TS
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex flex-col gap-2 flex-1">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl font-semibold text-sm transition-all duration-200 text-left ${
                isActive
                  ? 'bg-purple-600/15 text-white border-l-4 border-purple-500 shadow-[inset_4px_0_15px_rgba(139,92,246,0.25)]'
                  : 'text-slate-400 hover:text-white hover:bg-white/5 hover:translate-x-1'
              }`}
            >
              <Icon
                className={`w-5 h-5 transition-transform duration-200 ${
                  isActive ? 'scale-110 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]' : 'text-slate-400'
                }`}
              />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* User Footer */}
      <div className="pt-4 border-t border-white/10 flex items-center justify-between mt-auto">
        <div className="flex items-center gap-2 text-sm text-slate-300 font-medium">
          <div className="w-8 h-8 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
            {username.charAt(0).toUpperCase()}
          </div>
          <span>{username}</span>
        </div>
        <button
          onClick={onLogout}
          className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
          title="Выйти"
        >
          <LogOut className="w-5 h-5" />
        </button>
      </div>
    </aside>
  );
};
