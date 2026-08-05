import React from 'react';

interface CircularGaugeProps {
  percent: number;
  label: string;
  sublabel: string;
  color: string;
}

export const CircularGauge: React.FC<CircularGaugeProps> = ({
  percent,
  label,
  sublabel,
  color,
}) => {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percent / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center p-3">
      <div className="relative w-24 h-24 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90">
          <circle
            cx="48"
            cy="48"
            r={radius}
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth="7"
            fill="transparent"
          />
          <circle
            cx="48"
            cy="48"
            r={radius}
            stroke={color}
            strokeWidth="7"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
            className="transition-all duration-500"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-base font-extrabold text-white">{percent}%</span>
        </div>
      </div>
      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mt-2">{label}</span>
      <span className="text-[10px] text-slate-400">{sublabel}</span>
    </div>
  );
};
