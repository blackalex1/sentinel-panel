import React, { useState } from 'react';
import { Settings as SettingsIcon, Database, Key, Shield, Globe, HardDrive } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [telegramEnabled, setTelegramEnabled] = useState(true);

  return (
    <div className="space-y-6">
      <div className="p-6 rounded-2xl bg-[#0f1426]/60 backdrop-blur-xl border border-white/10 space-y-6">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-purple-400" /> Настройки системы и бота
        </h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 rounded-xl bg-white/5 border border-white/5">
            <div>
              <h4 className="text-sm font-bold text-white">Уведомления в Telegram-боте</h4>
              <p className="text-xs text-slate-400">Отправка алертов о подключениях с новых IP и статистике</p>
            </div>
            <input
              type="checkbox"
              checked={telegramEnabled}
              onChange={(e) => setTelegramEnabled(e.target.checked)}
              className="w-5 h-5 accent-purple-500 cursor-pointer"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
