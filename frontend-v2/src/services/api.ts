import { Inbound } from '../types/inbound';
import { ClientStats, ClientFormData } from '../types/client';
import { SystemStats } from '../types/system';
import { Outbound, RoutingRule } from '../types/routing';

const API_BASE = '/panel/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let errMessage = `HTTP Error ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) errMessage = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      else if (data.message) errMessage = data.message;
    } catch {
      // Ignore JSON parse error on non-OK response
    }
    throw new Error(errMessage);
  }

  return res.json();
}

export const api = {
  // Inbounds
  async getInbounds(): Promise<Inbound[]> {
    const data = await fetchJson<{ success: boolean; obj: any[] }>(`${API_BASE}/inbounds/list`);
    const list = data.obj || [];
    return list.map((ib) => ({
      id: ib.id,
      remark: ib.remark,
      port: ib.port,
      protocol: ib.protocol,
      core: ib.core || (ib.protocol === 'hysteria2' ? 'hysteria' : 'xray'),
      enable: ib.enable ? 1 : 0,
      client_count: (ib.clientStats || []).length,
    }));
  },

  async createInbound(data: Partial<Inbound>): Promise<{ success: boolean; id: number }> {
    return fetchJson(`${API_BASE}/inbounds/add`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateInbound(id: number, data: Partial<Inbound>): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/inbounds/update/${id}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deleteInbound(id: number): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/inbounds/delete/${id}`, {
      method: 'POST',
    });
  },

  // Real Clients extracted directly from Inbounds + Online Check
  async getClients(inboundId?: number): Promise<ClientStats[]> {
    let onlineEmails: string[] = [];
    try {
      const onlinesRes = await fetchJson<{ success: boolean; onlines: string[] }>(`${API_BASE}/clients/onlines`, {
        method: 'POST',
      });
      if (onlinesRes && Array.isArray(onlinesRes.onlines)) {
        onlineEmails = onlinesRes.onlines;
      }
    } catch {
      // ignore
    }

    const data = await fetchJson<{ success: boolean; obj: any[] }>(`${API_BASE}/inbounds/list`);
    const inbounds = data.obj || [];
    const allClients: ClientStats[] = [];

    inbounds.forEach((ib) => {
      if (inboundId && ib.id !== inboundId) return;
      const statsList = ib.clientStats || [];
      statsList.forEach((c: any) => {
        allClients.push({
          email: c.email,
          inbound_id: ib.id,
          client_uuid_or_pwd: c.client_uuid_or_pwd || c.uuid || c.password || '',
          enable: c.enable ? 1 : 0,
          up: c.up || 0,
          down: c.down || 0,
          total: c.total || 0,
          expiry_time: c.expiryTime || c.expiry_time,
          limit_ip: c.limitIp || c.limit_ip || 0,
          allowed_ips: c.allowedIps || c.allowed_ips || '',
          is_online: onlineEmails.includes(c.email),
          protocol: (ib.protocol || '').toUpperCase(),
          inbound_remark: ib.remark,
        });
      });
    });

    return allClients;
  },

  async addClient(data: ClientFormData): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/clients/add`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateClient(email: string, data: Partial<ClientFormData>): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/clients/update/${encodeURIComponent(email)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deleteClient(email: string): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/clients/delete/${encodeURIComponent(email)}`, {
      method: 'POST',
    });
  },

  // System & Core Stats
  async getSystemStats(): Promise<SystemStats> {
    const data = await fetchJson<{ success: boolean; obj: any }>(`${API_BASE}/server/status`);
    const obj = data.obj || {};
    
    // Query 30-day traffic history from backend
    let trafficHistory: Array<{ date: string; download_gb: number; upload_gb: number }> = [];
    try {
      const trafficRes = await fetchJson<{ success: boolean; obj: Array<{ date: string; up: number; down: number }> }>(
        `${API_BASE}/system/global-traffic`
      );
      if (trafficRes.obj && Array.isArray(trafficRes.obj)) {
        trafficHistory = trafficRes.obj.map((item) => ({
          date: item.date.slice(5),
          download_gb: Number(((item.down || 0) / (1024 * 1024 * 1024)).toFixed(2)),
          upload_gb: Number(((item.up || 0) / (1024 * 1024 * 1024)).toFixed(2)),
        }));
      }
    } catch {
      // ignore
    }

    // Query real BBR status from backend /api/system/bbr
    let bbrEnabled = false;
    try {
      const bbrRes = await fetchJson<{ success: boolean; bbr_enabled: boolean }>(`/api/system/bbr`);
      if (bbrRes && typeof bbrRes.bbr_enabled === 'boolean') {
        bbrEnabled = bbrRes.bbr_enabled;
      }
    } catch {
      // ignore
    }

    const memCurrent = obj.mem?.current || 0;
    const memTotal = obj.mem?.total || 1;
    const memPercent = Number(((memCurrent / memTotal) * 100).toFixed(1));

    return {
      cpu_percent: obj.cpu || 0,
      memory_percent: memPercent,
      memory_used_mb: Math.round(memCurrent / (1024 * 1024)),
      memory_total_mb: Math.round(memTotal / (1024 * 1024)),
      swap_percent: obj.swap?.percent || 0,
      swap_used_mb: Math.round((obj.swap?.current || 0) / (1024 * 1024)),
      swap_total_mb: Math.round((obj.swap?.total || 0) / (1024 * 1024)),
      disk_percent: obj.disk?.percent || 0,
      disk_used_gb: Number(((obj.disk?.current || 0) / (1024 * 1024 * 1024)).toFixed(1)),
      disk_total_gb: Number(((obj.disk?.total || 0) / (1024 * 1024 * 1024)).toFixed(1)),
      uptime_seconds: obj.uptime || 0,
      download_speed_kbps: Number(((obj.netIO?.down || 0) / 1024).toFixed(2)),
      upload_speed_kbps: Number(((obj.netIO?.up || 0) / 1024).toFixed(2)),
      total_download_gb: Number(((obj.netIO?.down || 0) / (1024 * 1024 * 1024)).toFixed(2)),
      total_upload_gb: Number(((obj.netIO?.up || 0) / (1024 * 1024 * 1024)).toFixed(2)),
      bbr_enabled: bbrEnabled,
      cores_status: {
        xray: obj.xray?.state === 'running',
        hysteria: obj.hysteria?.state === 'running',
        singbox: obj.singbox?.state === 'running',
        xray_version: obj.xray?.version,
        hysteria_version: obj.hysteria?.version,
        singbox_version: obj.singbox?.version,
      },
      active_connections_count: 0,
      daily_traffic_history: trafficHistory,
    };
  },

  async restartCore(core: 'xray' | 'hysteria' | 'singbox'): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/${core}/restart`, {
      method: 'POST',
    });
  },

  async stopCore(core: 'xray' | 'hysteria' | 'singbox'): Promise<{ success: boolean }> {
    return fetchJson(`${API_BASE}/${core}/stop`, {
      method: 'POST',
    });
  },

  // Routing
  async getOutbounds(): Promise<Outbound[]> {
    return fetchJson<Outbound[]>(`${API_BASE}/routing/outbounds`);
  },

  async getRoutingRules(): Promise<RoutingRule[]> {
    return fetchJson<RoutingRule[]>(`${API_BASE}/routing/rules`);
  },
};
