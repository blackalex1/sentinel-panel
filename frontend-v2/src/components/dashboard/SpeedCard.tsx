import React from 'react';
import { Download, Upload } from 'lucide-react';

interface SpeedCardProps {
  type: 'download' | 'upload';
  speedKbps?: number;
  fallbackValue?: string;
}

export const SpeedCard: React.FC<SpeedCardProps> = ({
  type,
  speedKbps,
  fallbackValue,
}) => {
  const isDownload = type === 'download';
  const Icon = isDownload ? Download : Upload;
  const label = isDownload ? 'Скорость скачивания' : 'Скорость отправки';
  const speedText = speedKbps ? `${speedKbps.toFixed(2)} KB/s` : fallbackValue;

  const bgStyle = isDownload
    ? 'bg-cyan-500/10 border-cyan-500/20'
    : 'bg-purple-500/10 border-purple-500/20';

  const iconStyle = isDownload
    ? 'bg-cyan-500/20 text-cyan-300'
    : 'bg-purple-500/20 text-purple-300';

  return (
    <div className={`p-4 rounded-xl border ${bgStyle} flex items-center justify-between`}>
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${iconStyle}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block">{label}</span>
          <span className="text-lg font-extrabold text-white font-mono">{speedText}</span>
        </div>
      </div>
    </div>
  );
};
