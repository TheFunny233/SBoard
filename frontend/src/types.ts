export type OnlineStatus = 'online' | 'offline' | 'unknown'
export type NodeProtocol =
  | 'vless'
  | 'vmess'
  | 'trojan'
  | 'ss'
  | 'ss2022'
  | 'hysteria2'
  | 'tuic'
  | 'wireguard'

export interface Overview {
  agents_total: number
  agents_online: number
  agents_offline: number
  managed_nodes: number
  external_nodes: number
  subscriptions: number
  nodes_by_protocol: Record<string, number>
}

export interface Agent {
  id: string
  name: string
  enabled: boolean
  online: boolean
  version: string | null
  protocol_version: number
  last_seen_at: string | null
  last_ip: string | null
  cpu_percent: number | null
  memory_used_bytes: number | null
  memory_total_bytes: number | null
  uptime_seconds: number | null
  xray_status: string
  xray_version: string | null
  xray_message: string | null
  xray_ports: number[]
  xray_nodes: AgentXrayNode[]
  desired_config_version: number
  applied_config_version: number
  created_at: string
  updated_at: string
}

export interface AgentXrayNode {
  tag: string | null
  protocol: string
  port: number
  network: string | null
  security: string | null
  uuid: string | null
  cipher: string | null
  flow: string | null
  sni: string | null
  public_key: string | null
  short_id: string | null
}

export interface AgentCreateResult {
  agent: Agent
  token: string
  config: Record<string, unknown>
}

export interface NodeRecord {
  id: string
  source_type: 'managed' | 'external'
  agent_id: string | null
  name: string
  address: string
  port: number
  protocol: NodeProtocol
  uuid: string | null
  password: string | null
  cipher: string | null
  tls: boolean
  reality: boolean
  sni: string | null
  public_key: string | null
  short_id: string | null
  flow: string | null
  network: string | null
  security: string | null
  path: string | null
  host: string | null
  service_name: string | null
  enabled: boolean
  sort_order: number
  extra: Record<string, unknown>
  group_ids: string[]
  tag_ids: string[]
  online_status: OnlineStatus
  created_at: string
  updated_at: string
}

export interface NodePayload {
  source_type: 'managed' | 'external'
  agent_id: string | null
  name: string
  address: string
  port: number
  protocol: NodeProtocol
  uuid?: string | null
  password?: string | null
  cipher?: string | null
  tls: boolean
  reality: boolean
  sni?: string | null
  public_key?: string | null
  short_id?: string | null
  flow?: string | null
  network?: string | null
  security?: string | null
  path?: string | null
  host?: string | null
  service_name?: string | null
  enabled: boolean
  sort_order: number
  extra: Record<string, unknown>
  group_ids: string[]
  tag_ids: string[]
}

export interface BatchDeleteResult {
  deleted: number
  missing_ids: string[]
}

export type RuleTargetMode = 'node' | 'direct' | 'reject'

export interface RuleSet {
  id: string
  name: string
  description: string | null
  enabled: boolean
  target_mode: RuleTargetMode
  node_id: string | null
  target_node_name: string | null
  rules: string[]
  sort_order: number
  created_at: string
  updated_at: string
}

export interface RuleSetPayload {
  name: string
  description: string | null
  enabled: boolean
  target_mode: RuleTargetMode
  node_id: string | null
  rules: string[]
  sort_order: number
}

export interface Group {
  id: string
  name: string
  description: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Tag {
  id: string
  name: string
  color: string | null
  created_at: string
}

export interface Subscription {
  id: string
  name: string
  enabled: boolean
  include_all_nodes: boolean
  node_ids: string[]
  group_ids: string[]
  tag_ids: string[]
  config: Record<string, unknown>
  token_hint: string
  last_access_at: string | null
  created_at: string
  updated_at: string
}

export interface SubscriptionCreateResult {
  subscription: Subscription
  token: string
  urls: { clash: string; v2ray: string }
}

export interface SubscriptionPreview {
  format: 'clash' | 'v2ray'
  content: string
  included_node_ids: string[]
  warnings: string[]
}

export interface ImportItem {
  index: number
  status: 'valid' | 'created' | 'skipped' | 'error'
  node: Partial<NodePayload> | null
  node_id: string | null
  warning: string | null
  error: string | null
}

export interface ImportResult {
  mode: 'preview' | 'commit'
  total: number
  created: number
  failed: number
  items: ImportItem[]
}

export interface Paged<T> {
  items: T[]
  total: number
}
