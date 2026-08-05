import React from 'react';
import { Route, Server, Shield } from 'lucide-react';
import { Outbound, RoutingRule } from '../../types/routing';

interface RoutingPageProps {
  outbounds?: Outbound[];
  rules?: RoutingRule[];
}

export const RoutingPage: React.FC<RoutingPageProps> = ({ outbounds = [], rules = [] }) => {
  return (
    <div className="space-y-6">
      {/* Outbounds Card */}
      <div className="p-6 rounded-2xl bg-[#0f1426]/60 backdrop-blur-xl border border-white/10 space-y-4">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Server className="w-5 h-5 text-purple-400" /> Выходящие соединения (Outbounds)
        </h3>

        <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/20">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-black/40 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/10">
              <tr>
                <th className="p-3.5">Тег (Tag)</th>
                <th className="p-3.5">Протокол</th>
                <th className="p-3.5">Статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              <tr className="hover:bg-white/5">
                <td className="p-3.5 font-bold text-white">direct</td>
                <td className="p-3.5">freedom (Прямой выход)</td>
                <td className="p-3.5"><span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Активен</span></td>
              </tr>
              <tr className="hover:bg-white/5">
                <td className="p-3.5 font-bold text-white">block</td>
                <td className="p-3.5">blackhole (Запрет)</td>
                <td className="p-3.5"><span className="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">Блокировка</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
