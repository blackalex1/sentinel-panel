import React, { useState } from 'react';
import { Inbound, InboundFormData } from '../../types/inbound';
import { Plus, Search, Edit3, Trash2, Users, Shield, Radio } from 'lucide-react';
import { InboundModal } from './InboundModal';

interface InboundsPageProps {
  inbounds: Inbound[];
  onCreateInbound: (data: InboundFormData) => void;
  onUpdateInbound: (id: number, data: InboundFormData) => void;
  onDeleteInbound: (id: number) => void;
  onOpenClients: (inbound: Inbound) => void;
}

export const InboundsPage: React.FC<InboundsPageProps> = ({
  inbounds,
  onCreateInbound,
  onUpdateInbound,
  onDeleteInbound,
  onOpenClients,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingInbound, setEditingInbound] = useState<Inbound | null>(null);

  const filteredInbounds = inbounds.filter(
    (ib) =>
      ib.remark.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ib.protocol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ib.port.toString().includes(searchQuery)
  );

  const handleOpenCreate = () => {
    setEditingInbound(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (ib: Inbound) => {
    setEditingInbound(ib);
    setModalOpen(true);
  };

  const handleFormSubmit = (data: InboundFormData) => {
    if (editingInbound) {
      onUpdateInbound(editingInbound.id, data);
    } else {
      onCreateInbound(data);
    }
    setModalOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex justify-between items-center">
        <div className="relative w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск по названию/порту..."
            className="w-full bg-[#0f1426]/70 border border-white/10 rounded-xl pl-10 pr-4 py-2 text-sm text-white focus:border-purple-500 outline-none"
          />
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-sm font-semibold rounded-xl shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" /> Создать подключение
        </button>
      </div>

      {/* Inbounds Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filteredInbounds.map((ib) => {
          const isHysteria = ib.protocol === 'hysteria2';
          return (
            <div
              key={ib.id}
              className="p-5 rounded-2xl bg-[#0f1426]/60 backdrop-blur-xl border border-white/10 hover:border-purple-500/30 transition-all duration-300 flex flex-col justify-between space-y-4 hover:-translate-y-1 shadow-lg"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="text-base font-bold text-white">{ib.remark}</h4>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
                      {ib.protocol}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
                      Порт: {ib.port}
                    </span>
                  </div>
                </div>
                <div
                  className={`w-3 h-3 rounded-full ${
                    ib.enable === 1 ? 'bg-emerald-400 shadow-[0_0_8px_#10b981]' : 'bg-rose-500'
                  }`}
                />
              </div>

              {/* Details */}
              <div className="space-y-2 text-xs text-slate-300 bg-black/20 p-3 rounded-xl border border-white/5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Движок ядра:</span>
                  <span className="font-semibold text-white">{ib.core || (isHysteria ? 'hysteria' : 'xray')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Клиентов:</span>
                  <span className="font-semibold text-purple-400">{ib.client_count ?? 1}</span>
                </div>
              </div>

              {/* Actions Footer */}
              <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                <button
                  onClick={() => onOpenClients(ib)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-purple-600/15 border border-purple-500/30 hover:bg-purple-600/30 text-purple-300 text-xs font-semibold rounded-xl transition-all"
                >
                  <Users className="w-3.5 h-3.5" /> Клиенты
                </button>
                <button
                  onClick={() => handleOpenEdit(ib)}
                  className="p-2 bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 hover:text-white rounded-xl transition-all"
                  title="Редактировать"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onDeleteInbound(ib.id)}
                  className="p-2 bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20 text-rose-400 rounded-xl transition-all"
                  title="Удалить"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal Dialog */}
      <InboundModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleFormSubmit}
        initialData={editingInbound}
      />
    </div>
  );
};
