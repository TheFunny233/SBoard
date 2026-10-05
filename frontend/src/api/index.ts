import { apiRequest, withQuery } from './client'
import type {
  Agent,
  AgentCreateResult,
  BatchDeleteResult,
  Group,
  ImportResult,
  NodePayload,
  NodeRecord,
  Overview,
  Paged,
  RuleSet,
  RuleSetPayload,
  Subscription,
  SubscriptionCreateResult,
  SubscriptionPreview,
  Tag,
} from '../types'

const json = (value: unknown): string => JSON.stringify(value)

export const api = {
  overview: () => apiRequest<Overview>('/api/v1/overview'),
  agents: (params: Record<string, unknown> = {}) =>
    apiRequest<Paged<Agent>>(withQuery('/api/v1/agents', params)),
  createAgent: (name: string) =>
    apiRequest<AgentCreateResult>('/api/v1/agents', {
      method: 'POST',
      body: json({ name }),
    }),
  updateAgent: (id: string, payload: Partial<Pick<Agent, 'name' | 'enabled'>>) =>
    apiRequest<Agent>(`/api/v1/agents/${id}`, { method: 'PATCH', body: json(payload) }),
  rotateAgentToken: (id: string) =>
    apiRequest<{ agent_id: string; token: string }>(`/api/v1/agents/${id}/rotate-token`, {
      method: 'POST',
    }),
  deleteAgent: (id: string) => apiRequest<void>(`/api/v1/agents/${id}`, { method: 'DELETE' }),

  nodes: (params: Record<string, unknown> = {}) =>
    apiRequest<Paged<NodeRecord>>(withQuery('/api/v1/nodes', params)),
  createNode: (payload: NodePayload) =>
    apiRequest<NodeRecord>('/api/v1/nodes', { method: 'POST', body: json(payload) }),
  updateNode: (id: string, payload: Partial<NodePayload>) =>
    apiRequest<NodeRecord>(`/api/v1/nodes/${id}`, { method: 'PATCH', body: json(payload) }),
  deleteNode: (id: string) => apiRequest<void>(`/api/v1/nodes/${id}`, { method: 'DELETE' }),
  deleteNodes: (ids: string[]) =>
    apiRequest<BatchDeleteResult>('/api/v1/nodes/batch', {
      method: 'DELETE',
      body: json({ ids }),
    }),
  importNodes: (payload: Record<string, unknown>) =>
    apiRequest<ImportResult>('/api/v1/nodes/import', { method: 'POST', body: json(payload) }),

  rules: () => apiRequest<RuleSet[]>('/api/v1/rules'),
  createRule: (payload: RuleSetPayload) =>
    apiRequest<RuleSet>('/api/v1/rules', { method: 'POST', body: json(payload) }),
  updateRule: (id: string, payload: Partial<RuleSetPayload>) =>
    apiRequest<RuleSet>(`/api/v1/rules/${id}`, { method: 'PATCH', body: json(payload) }),
  deleteRule: (id: string) => apiRequest<void>(`/api/v1/rules/${id}`, { method: 'DELETE' }),

  groups: () => apiRequest<Group[]>('/api/v1/groups'),
  createGroup: (payload: Pick<Group, 'name' | 'description' | 'sort_order'>) =>
    apiRequest<Group>('/api/v1/groups', { method: 'POST', body: json(payload) }),
  updateGroup: (id: string, payload: Partial<Group>) =>
    apiRequest<Group>(`/api/v1/groups/${id}`, { method: 'PATCH', body: json(payload) }),
  deleteGroup: (id: string) => apiRequest<void>(`/api/v1/groups/${id}`, { method: 'DELETE' }),

  tags: () => apiRequest<Tag[]>('/api/v1/tags'),
  createTag: (payload: Pick<Tag, 'name' | 'color'>) =>
    apiRequest<Tag>('/api/v1/tags', { method: 'POST', body: json(payload) }),
  updateTag: (id: string, payload: Partial<Tag>) =>
    apiRequest<Tag>(`/api/v1/tags/${id}`, { method: 'PATCH', body: json(payload) }),
  deleteTag: (id: string) => apiRequest<void>(`/api/v1/tags/${id}`, { method: 'DELETE' }),

  subscriptions: () => apiRequest<Subscription[]>('/api/v1/subscriptions'),
  createSubscription: (payload: Record<string, unknown>) =>
    apiRequest<SubscriptionCreateResult>('/api/v1/subscriptions', {
      method: 'POST',
      body: json(payload),
    }),
  updateSubscription: (id: string, payload: Record<string, unknown>) =>
    apiRequest<Subscription>(`/api/v1/subscriptions/${id}`, {
      method: 'PATCH',
      body: json(payload),
    }),
  rotateSubscriptionToken: (id: string) =>
    apiRequest<{ subscription_id: string; token: string; urls: Record<string, string> }>(
      `/api/v1/subscriptions/${id}/rotate-token`,
      { method: 'POST' },
    ),
  previewSubscription: (id: string, format: 'clash' | 'v2ray') =>
    apiRequest<SubscriptionPreview>(
      withQuery(`/api/v1/subscriptions/${id}/preview`, { format }),
    ),
  deleteSubscription: (id: string) =>
    apiRequest<void>(`/api/v1/subscriptions/${id}`, { method: 'DELETE' }),
}
