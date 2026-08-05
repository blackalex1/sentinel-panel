import React, { useState, useEffect } from 'react';
import { Inbound, ProtocolType, CoreType, InboundFormData } from '../../types/inbound';
import { X, Sparkles } from 'lucide-react';
import { generateRandomPassword, validateAllowedIPs } from '../../utils/security';

interface InboundModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: InboundFormData) => void;
  initialData?: Inbound | null;
}

export const InboundModal: React.FC<InboundModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  initialData,
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'stream' | 'security' | 'json'>('basic');
  
  const [formData, setFormData] = useState<InboundFormData>({
    remark: '',
    port: 8443,
    protocol: 'hysteria2',
    core: 'hysteria',
    enable: true,
    hysteriaMode: 'masq',
    obfsPassword: '',
    masqType: 'proxy',
    masqValue: 'https://google.com',
    upMbps: 100,
    downMbps: 100,
    ignoreClientBandwidth: false,
    sni: '',
    certMode: 'self',
    certPath: '',
    keyPath: '',
    hop: '',
    routingViaXray: false,
  });

  useEffect(() => {
    if (initialData) {
      let streamOpts: any = {};
      try {
        if (typeof initialData.stream_settings === 'string') {
          streamOpts = JSON.parse(initialData.stream_settings);
        } else if (initialData.stream_settings) {
          streamOpts = initialData.stream_settings;
        }
      } catch (e) {
        // ignore json parse error
      }
      const hystOpts = streamOpts.hysteria || {};

      setFormData({
        remark: initialData.remark || '',
        port: initialData.port || 8443,
        protocol: initialData.protocol || 'hysteria2',
        core: (initialData.core || (initialData.protocol === 'hysteria2' ? 'hysteria' : 'xray')) as CoreType,
        enable: initialData.enable === 1,
        hysteriaMode: hystOpts.mode || 'masq',
        obfsPassword: hystOpts.obfsPassword || '',
        masqType: hystOpts.masqType || 'proxy',
        masqValue: hystOpts.masqValue || '',
        upMbps: hystOpts.upMbps || 100,
        downMbps: hystOpts.downMbps || 100,
        ignoreClientBandwidth: hystOpts.ignoreClientBandwidth || false,
        sni: hystOpts.sni || streamOpts.sni || '',
        certMode: hystOpts.certMode || 'self',
        certPath: hystOpts.certPath || '',
        keyPath: hystOpts.keyPath || '',
        hop: hystOpts.hop || '',
        routingViaXray: hystOpts.routingViaXray || false,
      });
    } else {
      setFormData({
        remark: 'hyst_' + Math.floor(Math.random() * 1000),
        port: 8443,
        protocol: 'hysteria2',
        core: 'hysteria',
        enable: true,
        hysteriaMode: 'masq',
        obfsPassword: generateRandomPassword(16),
        masqType: 'proxy',
        masqValue: 'https://google.com',
        upMbps: 100,
        downMbps: 100,
        ignoreClientBandwidth: false,
        sni: '',
        certMode: 'self',
        certPath: '',
        keyPath: '',
        hop: '',
        routingViaXray: false,
      });
    }
  }, [initialData, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  const isHysteria = formData.protocol === 'hysteria2';

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-[#0e1324] border border-purple-500/30 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center pb-4 border-b border-white/10">
          <h2 className="text-xl font-bold text-white">
            {initialData ? 'Редактирование подключения' : 'Создание подключения'}
          </h2>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-white rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Tabs */}
        <div className="flex gap-2 border-b border-white/10 pb-3">
          <button
            type="button"
            onClick={() => setActiveTab('basic')}
            className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all ${
              activeTab === 'basic' ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40' : 'text-slate-400 hover:text-white'
            }`}
          >
            Основное
          </button>

          {/* Stream tab is visible for Hysteria 2 and VLESS */}
          {(isHysteria || formData.protocol === 'vless') && (
            <button
              type="button"
              onClick={() => setActiveTab('stream')}
              className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all ${
                activeTab === 'stream' ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40' : 'text-slate-400 hover:text-white'
              }`}
            >
              Поток (Stream)
            </button>
          )}

          <button
            type="button"
            onClick={() => setActiveTab('json')}
            className={`px-4 py-2 text-sm font-semibold rounded-xl transition-all ${
              activeTab === 'json' ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40' : 'text-slate-400 hover:text-white'
            }`}
          >
            JSON шаблон
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* TAB 1: Basic */}
          {activeTab === 'basic' && (
            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Название (Remark)</label>
                <input
                  type="text"
                  value={formData.remark}
                  onChange={(e) => setFormData({ ...formData, remark: e.target.value })}
                  className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                  required
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Порт</label>
                  <input
                    type="number"
                    value={formData.port}
                    onChange={(e) => setFormData({ ...formData, port: Number(e.target.value) })}
                    className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Протокол</label>
                  <select
                    value={formData.protocol}
                    onChange={(e) => {
                      const proto = e.target.value as ProtocolType;
                      setFormData({
                        ...formData,
                        protocol: proto,
                        core: proto === 'hysteria2' ? 'hysteria' : 'xray',
                      });
                    }}
                    className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                  >
                    <option value="hysteria2">Hysteria 2</option>
                    <option value="vless">VLESS</option>
                    <option value="vmess">VMess</option>
                    <option value="trojan">Trojan</option>
                    <option value="shadowsocks">Shadowsocks</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Движок ядра</label>
                  <select
                    value={formData.core}
                    onChange={(e) => setFormData({ ...formData, core: e.target.value as CoreType })}
                    className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                  >
                    {isHysteria ? (
                      <>
                        <option value="hysteria">Hysteria 2</option>
                        <option value="singbox">sing-box</option>
                      </>
                    ) : (
                      <>
                        <option value="xray">Xray-core</option>
                        <option value="singbox">sing-box</option>
                      </>
                    )}
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Stream Settings (Hysteria 2 / VLESS) */}
          {activeTab === 'stream' && isHysteria && (
            <div className="space-y-4 bg-purple-500/5 p-4 rounded-xl border border-purple-500/20">
              <h4 className="text-sm font-bold text-purple-300 uppercase tracking-wider">Настройки Hysteria 2</h4>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Режим защиты Hysteria 2</label>
                <select
                  value={formData.hysteriaMode}
                  onChange={(e) => setFormData({ ...formData, hysteriaMode: e.target.value as 'masq' | 'obfs' })}
                  className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                >
                  <option value="masq">Маскировка (Masquerade)</option>
                  <option value="obfs">Обфускация (Obfuscation / Salamander)</option>
                </select>
              </div>

              {formData.hysteriaMode === 'obfs' && (
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Пароль обфускации (obfs password)</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={formData.obfsPassword}
                      onChange={(e) => setFormData({ ...formData, obfsPassword: e.target.value })}
                      className="flex-1 bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, obfsPassword: generateRandomPassword(16) })}
                      className="px-3 py-2 bg-purple-600/20 text-purple-300 border border-purple-500/40 rounded-xl hover:bg-purple-600/30"
                      title="Сгенерировать"
                    >
                      <Sparkles className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}

              {formData.hysteriaMode === 'masq' && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Тип маскировки</label>
                    <select
                      value={formData.masqType}
                      onChange={(e) => setFormData({ ...formData, masqType: e.target.value as any })}
                      className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                    >
                      <option value="proxy">Proxy (Перенаправление)</option>
                      <option value="file">File (Каталог)</option>
                      <option value="status">Status Code</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Значение маскировки</label>
                    <input
                      type="text"
                      value={formData.masqValue}
                      onChange={(e) => setFormData({ ...formData, masqValue: e.target.value })}
                      placeholder="https://google.com"
                      className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Up Mbps (Отдача)</label>
                  <input
                    type="number"
                    value={formData.upMbps}
                    onChange={(e) => setFormData({ ...formData, upMbps: Number(e.target.value) })}
                    className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">Down Mbps (Загрузка)</label>
                  <input
                    type="number"
                    value={formData.downMbps}
                    onChange={(e) => setFormData({ ...formData, downMbps: Number(e.target.value) })}
                    className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-slate-400 block mb-2">SNI (Server Name Indication)</label>
                <input
                  type="text"
                  value={formData.sni}
                  onChange={(e) => setFormData({ ...formData, sni: e.target.value })}
                  placeholder="domain.com"
                  className="w-full bg-[#12182e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:border-purple-500 outline-none"
                />
              </div>
            </div>
          )}

          {/* TAB 3: JSON Template */}
          {activeTab === 'json' && (
            <div>
              <pre className="p-4 bg-black/40 border border-white/10 rounded-xl text-xs text-slate-300 font-mono overflow-x-auto">
                {JSON.stringify(formData, null, 2)}
              </pre>
            </div>
          )}

          {/* Submit Buttons */}
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
