export interface CoreStatus {
  xray: boolean;
  hysteria: boolean;
  singbox: boolean;
  xray_version?: string;
  hysteria_version?: string;
  singbox_version?: string;
}

export interface SystemStats {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  swap_percent?: number;
  swap_used_mb?: number;
  swap_total_mb?: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  uptime_seconds: number;
  download_speed_kbps?: number;
  upload_speed_kbps?: number;
  total_download_gb?: number;
  total_upload_gb?: number;
  cores_status: CoreStatus;
  active_connections_count: number;
  server_domain?: string;
  bbr_enabled?: boolean;
  daily_traffic_history?: Array<{
    date: string;
    download_gb: number;
    upload_gb: number;
  }>;
}
