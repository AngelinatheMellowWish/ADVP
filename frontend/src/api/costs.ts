import { request } from './projects'

export type BudgetStatus = {
  project_limit: number | null
  monthly_limit: number | null
  project_spend: number
  monthly_spend: number
  warning_ratio: number
  currency: string
  warning: boolean
  exceeded: boolean
  reason: string | null
}

export type CostBreakdown = {
  name: string
  cost: number
  requests: number
}

export type CostSummary = {
  project_id: string
  period: string
  total_cost: number
  retry_cost: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  currency: string
  by_provider: CostBreakdown[]
  by_model: CostBreakdown[]
  by_day: CostBreakdown[]
  by_tag: CostBreakdown[]
  by_operation: CostBreakdown[]
  by_run: CostBreakdown[]
  by_chart: CostBreakdown[]
  budget: BudgetStatus
}

export async function getBudget(projectId: string): Promise<BudgetStatus> {
  return request<BudgetStatus>(`/api/projects/${projectId}/budgets`)
}

export async function updateBudget(
  projectId: string,
  input: {
    project_limit: number | null
    monthly_limit: number | null
    warning_ratio: number
    currency: string
  },
): Promise<BudgetStatus> {
  return request<BudgetStatus>(`/api/projects/${projectId}/budgets`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function getCostSummary(
  projectId: string,
  period: 'month' | 'all' = 'month',
): Promise<CostSummary> {
  return request<CostSummary>(`/api/projects/${projectId}/costs?period=${period}`)
}
