export interface ClientStats {
  id?: number;
  inbound_id: number;
  email: string;
  client_uuid_or_pwd: string;
  total_gb?: number;
  expiry_time?: number;
  limit_ip?: number;
  enable: number;
  block_reason?: string;
  allowed_ips?: string;
  up?: number;
  down?: number;
  total?: number;
  is_online?: boolean;
  inbound_remark?: string;
  protocol?: string;
}

export interface ClientFormData {
  inbound_id: number;
  email: string;
  client_uuid_or_pwd: string;
  total_gb: number;
  expiry_time: string | number;
  limit_ip: number;
  enable: boolean;
  allowed_ips: string;
}
