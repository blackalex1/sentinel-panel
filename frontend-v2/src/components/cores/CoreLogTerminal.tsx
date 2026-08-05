import React, { useState, useEffect } from 'react';
import { Play, Square, RotateCw, Copy, Trash2, Terminal } from 'lucide-react';

interface CoreLogTerminalProps {
  coreName: 'hysteria' | 'xray' | 'singbox';
  title: string;
  isRunning?: boolean;
  onRestart?: () => void;
  onStop?: () => void;
}

export const CoreLogTerminal: React.FC<CoreLogTerminalProps> = ({
  coreName,
  title,
  isRunning = true,
  onRestart,
  onStop,
}) => {
  const [logs, setLogs] = useState<string[]>([
    `[INFO] Service ${coreName} initialized...`,
    `[INFO] Listening for active TLS/QUIC connections...`,
  ]);

  const handleCopyLogs = () => {
    navigator.clipboard.writeText(logs.join('\n'));
  };

  const handleClearLogs = () => {
    setLogs([]);
  };

  return (
    <div className="space-y-6">
      {/* Control Panel */}
      <div className="p-6 rounded-2xl bg-[#0f1426]/60 backdrop-blur-xl border border-white/10 flex justify-between items-center">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Terminal className="w-5 h-5 text-purple-400" /> {title}
          </h3>
          <p className="text-xs text-slate-400 mt-1">Управление сервисом ядра и просмотр логов в реальном времени</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onRestart}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600/20 text-purple-300 border border-purple-500/30 hover:bg-purple-600/30 rounded-xl text-sm font-semibold transition-all"
          >
            <RotateCw className="w-4 h-4" /> Перезапустить
          </button>
          <button
            onClick={onStop}
            className="flex items-center gap-2 px-4 py-2 bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20 rounded-xl text-sm font-semibold transition-all"
          >
            <Square className="w-4 h-4" /> Остановить
          </button>
        </div>
      </div>

      {/* Log Terminal Window */}
      <div className="p-6 rounded-2xl bg-[#0f1426]/60 backdrop-blur-xl border border-white/10 space-y-4">
        <div className="flex justify-between items-center border-b border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-rose-500/80" />
            <span className="w-3 h-3 rounded-full bg-amber-500/80" />
            <span className="w-3 h-3 rounded-full bg-emerald-500/80" />
            <span className="text-xs text-slate-400 font-mono ml-2">logs/{coreName}.log</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLogs}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg transition-colors"
              title="Копировать"
            >
              <Copy className="w-4 h-4" />
            </button>
            <button
              onClick={handleClearLogs}
              className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg transition-colors"
              title="Очистить"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Console Body */}
        <div className="h-96 bg-[#04060d] border border-white/10 rounded-xl p-4 font-mono text-xs text-emerald-400 overflow-y-auto space-y-1 shadow-inner">
          {logs.map((line, idx) => (
            <div key={idx} className="leading-relaxed">
              {line}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
