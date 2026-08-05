import React, { useState, useEffect } from 'react';
import { ClientStats, ClientFormData } from '../../types/client';
import { X, Sparkles, ShieldCheck } from 'lucide-react';
import { validateAllowedIPs, generateRandomPassword } from '../../utils/security';

interface ClientModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ClientFormData) => void;
  inboundId: number;
  initialData?: ClientStats | null;
}

export const ClientModal: React.FC<ClientModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  inboundId,
  initialData,
}) => {
  const [formData, setFormData] = useState<ClientFormData>({
    inbound_id: inboundId,
    email: '',
    client_uuid_or_pwd: '',
    total_gb: 0,
    expiry_time: 0,
    limit_ip: 0,
    enable: true,
    allowed_ips: '',
  });

  const [ipError, setIpError] = useState<string | null>(null);

  useEffect(() => {
    if (initialData) {
      setFormData({
        inbound_id: initialData.inbound_id || inboundId,
        email: initialData.email || '',
        client_uuid_or_pwd: initialData.client_uuid_or_pwd || '',
        total_gb: initialData.total_gb || 0,
        expiry_time: initialData.expiry_time || 0,
        limit_ip: initialData.limit_ip || 0,
        enable: initialData.enable === 1,
        allowed_ips: initialData.allowed_ips || '',
      });
    } else {
      setFormData({
        inbound_id: inboundId,
        email: 'user_' + Math.floor(Math.random() * 1000),
        client_uuid_or_pwd: generateRandomPassword(12),
        total_gb: 0,
        expiry_time: 0,
        limit_ip: 0,
        enable: true,
        allowed_ips: '',
      });
    }
    setIpError(null);
  }, [initialData, inboundId, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = validateAllowedIPs(formData.allowed_ips);
    if (!val.valid) {
      setIpError(val.error || 'Некорректный IP адрес в белом списке');
      return;
    }
    onSubmit(formData);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-[#0e1324] border border-purple-500/30 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-6">
        <div className="flex justify-between items-center pb-4 border-b border-white/10">
          <h2 className="text-lg font-bold text-white">
            {initialData ? `Редактирование клиента (${initialData.email})` : 'Добавление клиента'}
          </h2>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-white rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">
              Email / Имя пользователя
            </label>
            <input
              type="text"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
              required
              disabled={!!initialData}
            />
          </div>

          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">
              UUID / Пароль клиента
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={formData.client_uuid_or_pwd}
                onChange={(e) => setFormData({ ...formData, client_uuid_or_pwd: e.target.value })}
                className="flex-1 bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none font-mono text-xs"
                required
              />
              <button
                type="button"
                onClick={() => setFormData({ ...formData, client_uuid_or_pwd: generateRandomPassword(16) })}
                className="px-3 py-2 bg-purple-600/20 text-purple-300 border border-purple-500/40 rounded-xl hover:bg-purple-600/30"
                title="Сгенерировать"
              >
                <Sparkles className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* White List Allowed IPs */}
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" /> Белый список IP-адресов (через запятую)
            </label>
            <input
              type="text"
              value={formData.allowed_ips}
              onChange={(e) => {
                setFormData({ ...formData, allowed_ips: e.target.value });
                setIpError(null);
              }}
              placeholder="198.51.100.42, 203.0.113.162"
              className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none font-mono text-xs"
            />
            {ipError && <div className="text-xs text-rose-400 font-semibold mt-1.5">{ipError}</div>}
            <small className="text-[11px] text-slate-400 mt-1 block">
              Оставьте пустым, чтобы разрешить подключение с любых IP-адресов.
            </small>
          </div>

          <div className="pt-4 flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-white/10 text-slate-300 font-semibold hover:bg-white/5"
            >
              Отмена
            </button>
            <button
              type="submit"
              className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-semibold shadow-lg hover:from-purple-500 hover:to-indigo-500"
            >
              Сохранить
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
