import type { GroupPolicy } from './types'

export function defaultGroupPolicy(): GroupPolicy {
  return {
    strategy: 'select',
    test_url: 'https://www.gstatic.com/generate_204',
    test_interval: 300,
    test_tolerance: 50,
  }
}

export function groupStrategyLabel(strategy: GroupPolicy['strategy']): string {
  return { select: '手动选择', 'url-test': '自动测速', fallback: '故障转移' }[strategy]
}
