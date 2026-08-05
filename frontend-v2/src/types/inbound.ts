export type ProtocolType = 'vless' | 'vmess' | 'trojan' | 'shadowsocks' | 'hysteria2' | 'socks' | 'http';
export type CoreType = 'xray' | 'hysteria' | 'singbox';

export interface HysteriaStreamSettings {
  mode?: 'masq' | 'obfs';
  obfsPassword?: string;
  masqType?: 'proxy' | 'file' | 'status';
  masqValue?: string;
  upMbps?: number;
  downMbps?: number;
  ignoreClientBandwidth?: boolean;
  sni?: string;
  certMode?: 'self' | 'custom';
  certPath?: string;
  keyPath?: string;
  hop?: string;
  routingViaXray?: boolean;
}

export interface StreamSettings {
  network?: string;
  security?: 'none' | 'tls' | 'reality';
  sni?: string;
  alpn?: string[];
  certFile?: string;
  keyFile?: string;
  hysteria?: HysteriaStreamSettings;
}

export interface Inbound {
  id: number;
  remark: string;
  port: number;
  protocol: ProtocolType;
  core?: CoreType;
  enable: number;
  settings?: string | Record<string, any>;
  stream_settings?: string | StreamSettings;
  sniffing?: string | Record<string, any>;
  client_count?: number;
}

export interface InboundFormData {
  remark: string;
  port: number;
  protocol: ProtocolType;
  core: CoreType;
  enable: boolean;
  network?: string;
  security?: string;
  sni?: string;
  certMode?: 'self' | 'custom';
  certPath?: string;
  keyPath?: string;
  hysteriaMode?: 'masq' | 'obfs';
  obfsPassword?: string;
  masqType?: 'proxy' | 'file' | 'status';
  masqValue?: string;
  upMbps?: number;
  downMbps?: number;
  ignoreClientBandwidth?: boolean;
  hop?: string;
  routingViaXray?: boolean;
}
