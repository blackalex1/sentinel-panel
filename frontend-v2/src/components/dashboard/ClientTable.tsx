import React, { useState } from 'react';
import { ClientStats } from '../../types/client';
import { Search, Users, QrCode, Copy, Edit3, Trash2 } from 'lucide-react';

interface ClientTableProps {
  clients?: ClientStats[];
  onOpenQr?: (client: ClientStats) => void;
  onCopyLinks?: (client: ClientStats) => void;
  onEditClient?: (client: ClientStats) => void;
  onDeleteClient?: (client: ClientStats) => void;
}

export const ClientTable: React.FC<ClientTableProps> = ({
  clients = [],
  onOpenQr,
  onCopyLinks,
  onEditClient,
  onDeleteClient,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [onlyOnline, setOnlyOnline] = useState(false);
  const [onlyBlocked, setOnlyBlocked] = useState(false);

  const filteredClients = clients.filter((c) => {
    const matchesQuery =
      c.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.inbound_remark || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.protocol || '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchesOnline = !onlyOnline || c.is_online;
    const matchesBlocked = !onlyBlocked || c.enable === 0;
    return matchesQuery && matchesOnline && matchesBlocked;
  });

  return (
    <div className="p-6 rounded-2xl bg-[#0f1426]/70 backdrop-blur-xl border border-white/10 space-y-5 shadow-xl">
      {/* Table Header Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-white/10">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Users className="w-5 h-5 text-purple-400" /> Список клиентов
        </h3>

        <div className="flex flex-wrap items-center gap-4 w-full sm:w-auto">
          {/* Filter Checkboxes */}
          <label className="flex items-center gap-2 text-xs font-semibold text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyOnline}
              onChange={(e) => setOnlyOnline(e.target.checked)}
              className="w-4 h-4 accent-purple-500 rounded cursor-pointer"
            />
            Только онлайн
          </label>

          <label className="flex items-center gap-2 text-xs font-semibold text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyBlocked}
              onChange={(e) => setOnlyBlocked(e.target.checked)}
              className="w-4 h-4 accent-purple-500 rounded cursor-pointer"
            />
            Только заблокированные
          </label>

          {/* Search Input */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по email или подключению..."
              className="w-full bg-[#12182e] border border-white/10 rounded-xl pl-9 pr-4 py-2 text-xs text-white focus:border-purple-500 outline-none"
            />
          </div>
        </div>
      </div>

      {/* Table Body */}
      <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/20">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-black/40 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-white/10">
            <tr>
              <th className="p-4">Пользователь / Email</th>
              <th className="p-4">Статус</th>
              <th className="p-4">Протокол / Подключение</th>
              <th className="p-4">Трафик (Отдача | Скачивание)</th>
              <th className="p-4">Лимит IP</th>
              <th className="p-4">Срок действия</th>
              <th className="p-4 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {filteredClients.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-slate-400 font-medium">
                  Клиенты не найдены
                </td>
              </tr>
            ) : (
              filteredClients.map((client, idx) => {
                const isOnline = client.is_online !== false;
                return (
                  <tr key={idx} className="hover:bg-white/[0.03] transition-colors">
                    <td className="p-4 font-bold text-white max-w-[180px] truncate">
                      {client.email}
                    </td>

                    <td className="p-4">
                      {isOnline ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Онлайн
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-500/10 text-slate-400 border border-slate-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-400" /> Офлайн
                        </span>
                      )}
                    </td>

                    <td className="p-4">
                      <span className="inline-block px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider bg-purple-500/10 text-purple-300 border border-purple-500/20 font-mono">
                        {client.protocol || 'HYSTERIA2'} [{client.inbound_remark || 'hyst_alive'}]
                      </span>
                    </td>

                    <td className="p-4 font-mono font-semibold text-slate-200">
                      {((client.up || 0) / 1073741824).toFixed(2)} GB | {((client.down || 0) / 1048576).toFixed(2)} MB
                    </td>

                    <td className="p-4">
                      <span className="text-slate-300 font-medium">
                        {client.limit_ip ? `IP: ${client.limit_ip}` : 'Безлимит / IP: ∞'}
                      </span>
                    </td>

                    <td className="p-4 text-slate-300 font-medium">
                      {client.expiry_time ? new Date(client.expiry_time).toLocaleDateString() : 'Бессрочно'}
                    </td>

                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => onOpenQr?.(client)}
                          className="p-2 rounded-lg bg-white/5 border border-white/10 hover:bg-purple-600/20 hover:border-purple-500/40 text-slate-300 hover:text-purple-300 transition-all"
                          title="QR-код"
                        >
                          <QrCode className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onCopyLinks?.(client)}
                          className="p-2 rounded-lg bg-white/5 border border-white/10 hover:bg-cyan-600/20 hover:border-cyan-500/40 text-slate-300 hover:text-cyan-300 transition-all"
                          title="Копировать ссылки"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onEditClient?.(client)}
                          className="p-2 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 hover:text-white transition-all"
                          title="Редактировать"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onDeleteClient?.(client)}
                          className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20 text-rose-400 transition-all"
                          title="Удалить"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
