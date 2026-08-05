export interface Outbound {
  id: number;
  tag: string;
  protocol: string;
  settings?: Record<string, any>;
  stream_settings?: Record<string, any>;
}

export interface RoutingRule {
  id: number;
  type?: string;
  outbound_tag: string;
  domain?: string[];
  ip?: string[];
  port?: string;
  protocol?: string[];
  inbound_tag?: string[];
  enabled: boolean;
}
