export interface EventCase {
  id: string
  title: string
  summary: string | null
  status: string
  risk_level: string
  desk: string | null
  region: string | null
  start_time: string | null
  end_time: string | null
  tags: string[]
  owner_id: string | null
  created_at: string
  updated_at: string
}

export interface StoryPacket {
  id: string
  event_case_id: string
  title: string
  angle_statement: string | null
  target_audience: string | null
  content_type: string
  status: string
  risk_level: string
  owner_id: string | null
  desk: string | null
  deadline: string | null
  blockers: Blocker[]
  created_at: string
  updated_at: string
}

export interface Blocker {
  blocker_id: string
  type: string
  severity: string
  description: string
  resolved: boolean
  resolved_by?: string
  resolved_at?: string
}

export interface ApprovalTask {
  id: string
  review_bundle_id: string
  approval_stage: string
  status: string
  signer_slots: SignerSlot[]
  execution_mode: string
  sla_deadline: string | null
  created_at: string
  updated_at: string
}

export interface SignerSlot {
  role: string
  user_id: string | null
  status: string
  signed_at: string | null
}

export interface DecisionLog {
  id: string
  approval_task_id: string
  review_bundle_id: string
  signer_id: string
  signer_role: string
  action: string
  decision_reason: string | null
  override_ai_flag: boolean
  override_reason: string | null
  return_category: string | null
  created_at: string
}

export interface User {
  id: string
  username: string
  display_name: string
  email: string
  roles: string[]
  desk: string | null
  is_active: boolean
}

export type RiskLevel = 'L0' | 'L1' | 'L2' | 'L3'
export type ContentType = 'breaking' | 'in_depth' | 'explainer' | 'video_script' | 'podcast'
