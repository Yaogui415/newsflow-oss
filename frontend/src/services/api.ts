import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 90000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  const raw = localStorage.getItem('newsflow-auth')
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      const token = parsed?.state?.token
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    } catch { /* ignore */ }
  }
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API Error]', err.config?.method, err.config?.url, 'status:', err.response?.status, 'msg:', err.response?.data?.message || err.message)
    if (err.response?.status === 401) {
      const url = err.config?.url || ''
      if (!url.includes('/auth/login') && !url.includes('/auth/register')) {
        console.warn('[Auth] 401 detected, clearing token. URL:', url)
        localStorage.removeItem('newsflow-auth')
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(err)
  },
)

export const authApi = {
  login: async (username: string, password: string) => {
    const res = await apiClient.post('/auth/login', { username, password })
    return res.data as { access_token: string; token_type: string }
  },
  register: async (data: { username: string; display_name: string; email: string; password: string; roles?: string[]; desk?: string; org_name?: string; invite_code?: string }) => {
    const res = await apiClient.post('/auth/register', data)
    return res.data
  },
  getMe: async () => {
    const res = await apiClient.get('/auth/me')
    return res.data
  },
  getLLMSettings: async () => {
    const res = await apiClient.get('/auth/me/llm-settings')
    return res.data
  },
  updateLLMSettings: async (data: { api_key: string; daily_budget_usd: number; model_preference: string; provider: string }) => {
    const res = await apiClient.put('/auth/me/llm-settings', data)
    return res.data
  },
  deleteLLMSettings: async () => {
    const res = await apiClient.delete('/auth/me/llm-settings')
    return res.data
  },
}

export const orgsApi = {
  getMyOrg: async () => {
    const res = await apiClient.get('/orgs/my')
    return res.data
  },
  getMembers: async () => {
    const res = await apiClient.get('/orgs/my/members')
    return res.data
  },
  createOrg: async (data: { name: string; display_name: string; description?: string }) => {
    const res = await apiClient.post('/orgs', data)
    return res.data
  },
  joinOrg: async (invite_code: string) => {
    const res = await apiClient.post('/orgs/join', { invite_code })
    return res.data
  },
  updateOrg: async (data: { display_name?: string; description?: string }) => {
    const res = await apiClient.put('/orgs/my', data)
    return res.data
  },
  regenerateInvite: async () => {
    const res = await apiClient.post('/orgs/my/regenerate-invite')
    return res.data
  },
  removeMember: async (userId: string) => {
    const res = await apiClient.delete(`/orgs/my/members/${userId}`)
    return res.data
  },
  leaveOrg: async () => {
    const res = await apiClient.post('/orgs/my/leave')
    return res.data
  },
}

export const eventsApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/events', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/events/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/events', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/events/${id}`, data)
    return res.data
  },
  getSources: async (id: string) => {
    const res = await apiClient.get(`/events/${id}/sources`)
    return res.data
  },
  getAgentActivities: async (id: string) => {
    const res = await apiClient.get(`/events/${id}/agent-activities`)
    return res.data
  },
  getWorkflowRuns: async (id: string) => {
    const res = await apiClient.get(`/events/${id}/workflow-runs`)
    return res.data
  },
  delete: async (id: string) => {
    const res = await apiClient.delete(`/events/${id}`)
    return res.data
  },
  restore: async (id: string) => {
    const res = await apiClient.post(`/events/${id}/restore`)
    return res.data
  },
  listArchived: async () => {
    const res = await apiClient.get('/events/archived/list')
    return res.data
  },
  triggerCollect: async (id: string, keywords?: string) => {
    const res = await apiClient.post(`/events/${id}/collect`, null, { params: keywords ? { keywords } : {} })
    return res.data
  },
  advanceGate: async (id: string) => {
    const res = await apiClient.post(`/events/${id}/advance-gate`)
    return res.data
  },
  advanceWorkflow: async (id: string) => {
    const res = await apiClient.post(`/events/${id}/workflow-advance`)
    return res.data
  },
}

export const storyPacketsApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/story-packets', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/story-packets/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/story-packets', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/story-packets/${id}`, data)
    return res.data
  },
  transition: async (id: string, targetState: string) => {
    const res = await apiClient.post(`/story-packets/${id}/transition`, { target_state: targetState })
    return res.data
  },
  listClaimCards: async (id: string, params?: { risk_level?: string; status?: string }) => {
    const res = await apiClient.get(`/story-packets/${id}/claim-cards`, { params })
    return res.data
  },
  getDraft: async (id: string) => {
    const res = await apiClient.get(`/story-packets/${id}/draft`)
    return res.data
  },
  getDraftVersions: async (id: string) => {
    const res = await apiClient.get(`/story-packets/${id}/draft/versions`)
    return res.data
  },
  getDraftVersion: async (id: string, version: number) => {
    const res = await apiClient.get(`/story-packets/${id}/draft/${version}`)
    return res.data
  },
  updateDraft: async (id: string, data: { title?: string; lead?: string; body?: string; body_html?: string; claim_anchor_map?: Record<string, any> }) => {
    const res = await apiClient.patch(`/story-packets/${id}/draft`, data)
    return res.data
  },
  submitReview: async (id: string, data: { submit_note: string; bundle_type?: string }, idempotencyKey?: string) => {
    const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined
    const res = await apiClient.post(`/story-packets/${id}/submit-review`, data, { headers })
    return res.data
  },
  delete: async (id: string) => {
    const res = await apiClient.delete(`/story-packets/${id}`)
    return res.data
  },
  restore: async (id: string) => {
    const res = await apiClient.post(`/story-packets/${id}/restore`)
    return res.data
  },
  listArchived: async () => {
    const res = await apiClient.get('/story-packets/archived/list')
    return res.data
  },
}

export const approvalsApi = {
  listTasks: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/approvals/tasks', { params })
    return res.data
  },
  getTask: async (taskId: string) => {
    const res = await apiClient.get(`/approvals/tasks/${taskId}`)
    return res.data
  },
  decide: async (taskId: string, data: Record<string, unknown>) => {
    const res = await apiClient.post(`/approvals/tasks/${taskId}/decide`, data)
    return res.data
  },
  listDecisionLogs: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/approvals/decision-logs', { params })
    return res.data
  },
}

export const sourcesApi = {
  upload: async (formData: FormData) => {
    const res = await apiClient.post('/sources/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },
  manual: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/sources/manual', data)
    return res.data
  },
  list: async (params?: { page?: number; page_size?: number; event_case_id?: string }) => {
    const res = await apiClient.get('/sources/items', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/sources/items/${id}`)
    return res.data
  }
}

export const dashboardApi = {
  getStats: async () => {
    const res = await apiClient.get('/dashboard/stats')
    return res.data
  },
  getHighPriorityEvents: async (limit = 10) => {
    const res = await apiClient.get('/dashboard/high-priority-events', { params: { limit } })
    return res.data
  },
  getSlaAlerts: async () => {
    const res = await apiClient.get('/dashboard/sla-alerts')
    return res.data
  },
  getAgentActivities: async (limit = 20) => {
    const res = await apiClient.get('/dashboard/agent-activities', { params: { limit } })
    return res.data
  },
  getSidebarCounts: async () => {
    const res = await apiClient.get('/dashboard/sidebar-counts')
    return res.data
  },
}

export const evidencePacksApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/evidence-packs', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/evidence-packs/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/evidence-packs', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/evidence-packs/${id}`, data)
    return res.data
  },
  snapshot: async (id: string) => {
    const res = await apiClient.post(`/evidence-packs/${id}/snapshot`)
    return res.data
  },
  delete: async (id: string) => {
    const res = await apiClient.delete(`/evidence-packs/${id}`)
    return res.data
  },
  restore: async (id: string) => {
    const res = await apiClient.post(`/evidence-packs/${id}/restore`)
    return res.data
  },
}

export const channelPackagesApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/channel-packages', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/channel-packages/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/channel-packages', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/channel-packages/${id}`, data)
    return res.data
  },
  transition: async (id: string, targetState: string) => {
    const res = await apiClient.post(`/channel-packages/${id}/transition`, { target_state: targetState })
    return res.data
  },
}

export const correctionTicketsApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/correction-tickets', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/correction-tickets/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/correction-tickets', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/correction-tickets/${id}`, data)
    return res.data
  },
  close: async (id: string) => {
    const res = await apiClient.post(`/correction-tickets/${id}/close`)
    return res.data
  },
}

export const reviewBundlesApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/review-bundles', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/review-bundles/${id}`)
    return res.data
  },
}

export const riskReportsApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/risk-reports', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/risk-reports/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/risk-reports', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/risk-reports/${id}`, data)
    return res.data
  },
}

export const claimCardsApi = {
  list: async (params?: Record<string, unknown>) => {
    const res = await apiClient.get('/claim-cards', { params })
    return res.data
  },
  get: async (id: string) => {
    const res = await apiClient.get(`/claim-cards/${id}`)
    return res.data
  },
  create: async (data: Record<string, unknown>) => {
    const res = await apiClient.post('/claim-cards', data)
    return res.data
  },
  update: async (id: string, data: Record<string, unknown>) => {
    const res = await apiClient.patch(`/claim-cards/${id}`, data)
    return res.data
  },
  delete: async (id: string) => {
    const res = await apiClient.delete(`/claim-cards/${id}`)
    return res.data
  },
  restore: async (id: string) => {
    const res = await apiClient.post(`/claim-cards/${id}/restore`)
    return res.data
  },
  listArchived: async (storyPacketId?: string) => {
    const res = await apiClient.get('/claim-cards/archived/list', { params: storyPacketId ? { story_packet_id: storyPacketId } : {} })
    return res.data
  },
}

export const workflowsApi = {
  getTemplate: async () => {
    const res = await apiClient.get('/workflows/template')
    return res.data
  },
  getStoryPacketProgress: async (packetId: string) => {
    const res = await apiClient.get(`/workflows/story-packets/${packetId}/progress`)
    return res.data
  },
  createRun: async (data: { event_case_id?: string; source_items?: any[] }) => {
    const res = await apiClient.post('/workflows/runs', data)
    return res.data
  },
  getRun: async (runId: string) => {
    const res = await apiClient.get(`/workflows/runs/${runId}`)
    return res.data
  },
  advanceRun: async (runId: string) => {
    const res = await apiClient.post(`/workflows/runs/${runId}/advance`)
    return res.data
  },
  submitDecision: async (runId: string, data: { decision_type: string; action: string; reason?: string }) => {
    const res = await apiClient.post(`/workflows/runs/${runId}/decisions`, data)
    return res.data
  },
  listRunEvents: async (runId: string, params?: { cursor?: string; limit?: number }) => {
    const res = await apiClient.get(`/workflows/runs/${runId}/events`, { params })
    return res.data
  },
  listAuditEvents: async (params?: { object_type?: string; object_id?: string; action?: string; actor_type?: string; cursor?: string; limit?: number }) => {
    const res = await apiClient.get('/workflows/audit/events', { params })
    return res.data
  }
}

export const seedApi = {
  generate: async () => {
    const res = await apiClient.post('/seed')
    return res.data
  },
  aiGenerate: async () => {
    const res = await apiClient.post('/seed/ai-generate')
    return res.data
  },
  upgrade: async () => {
    const res = await apiClient.post('/seed-upgrade')
    return res.data
  },
}

export default apiClient
