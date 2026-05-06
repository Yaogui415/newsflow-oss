import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Tag, Button, Table, Progress, Select, Input, Modal, message, Upload, Spin } from 'antd'
import { 
  RightOutlined, 
  ArrowLeftOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  ClockCircleOutlined,
  PlusOutlined,
  EditOutlined,
  FilterOutlined,
  UploadOutlined,
  SaveOutlined,
  EyeOutlined,
  DeleteOutlined,
  UndoOutlined
} from '@ant-design/icons'
import { storyPacketsApi, sourcesApi, workflowsApi, riskReportsApi, channelPackagesApi, evidencePacksApi, claimCardsApi } from '@/services/api'

const GOLD = '#D4A853'
const GOLD_BORDER = 'rgba(212,168,83,0.2)'
const BG_CARD = '#141414'
const BORDER = 'rgba(212,168,83,0.1)'
const TEXT_PRIMARY = '#F5F5F5'
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)'
const TEXT_MUTED = 'rgba(245,245,245,0.35)'

const claimStatusMeta: Record<string, { label: string; background: string; color: string }> = {
  supported: { label: '已支持', background: '#22c55e', color: '#fff' },
  disputed: { label: '有争议', background: '#f97316', color: '#fff' },
  insufficient: { label: '证据不足', background: '#ef4444', color: '#fff' },
  manually_accepted: { label: '人工采纳', background: GOLD, color: '#0A0A0A' },
  unverified: { label: '待核验', background: '#71717a', color: '#fff' },
}

const riskColors: Record<string, string> = {
  L0: '#22c55e',
  L1: '#eab308',
  L2: '#f97316',
  L3: '#ef4444',
}

const getRiskTextColor = (riskLevel?: string) => (riskLevel === 'L1' ? '#0A0A0A' : '#fff')

export default function StoryPacketDetailPage() {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const [activeTab, setActiveTab] = useState('claims')

  // Claim filter state
  const [claimRiskFilter, setClaimRiskFilter] = useState<string | undefined>(undefined)
  const [claimStatusFilter, setClaimStatusFilter] = useState<string | undefined>(undefined)
  const [filteredClaims, setFilteredClaims] = useState<any[]>([])
  const [claimsLoading, setClaimsLoading] = useState(false)

  // Draft editing state
  const [draftData, setDraftData] = useState<{ title: string; lead: string; body: string; version: number } | null>(null)
  const [isEditingDraft, setIsEditingDraft] = useState(false)
  const [draftEditTitle, setDraftEditTitle] = useState('')
  const [draftEditLead, setDraftEditLead] = useState('')
  const [draftEditBody, setDraftEditBody] = useState('')
  const [draftLoading, setDraftLoading] = useState(false)
  const [draftSaving, setDraftSaving] = useState(false)
  const [draftVersions, setDraftVersions] = useState<any[]>([])
  const [showVersionHistory, setShowVersionHistory] = useState(false)
  const [viewingVersion, setViewingVersion] = useState<any>(null)

  // Workflow stages from API
  const [apiWorkflowStages, setApiWorkflowStages] = useState<any[]>([])
  const [, setWorkflowLoading] = useState(false)
  const [apiBlockers, setApiBlockers] = useState<any[]>([])

  // Evidence / Sources state
  const [sourceItems, setSourceItems] = useState<any[]>([])
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [sourceDetailModal, setSourceDetailModal] = useState<any>(null)

  // Story Packet detail from API
  const [packetData, setPacketData] = useState<any>(null)
  const [, setPacketLoading] = useState(false)

  // Risk reports state
  const [riskReports, setRiskReports] = useState<any[]>([])
  const [riskLoading, setRiskLoading] = useState(false)

  // Channel packages state
  const [channelPkgs, setChannelPkgs] = useState<any[]>([])
  const [channelLoading, setChannelLoading] = useState(false)

  // Evidence packs state
  const [evidencePacks, setEvidencePacks] = useState<any[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [expandedEpIds, setExpandedEpIds] = useState<Set<string>>(new Set())

  // Upload loading state
  const [uploading, setUploading] = useState(false)

  // Submit review state
  const [submitLoading, setSubmitLoading] = useState(false)

  // Add claim modal state
  const [addClaimOpen, setAddClaimOpen] = useState(false)
  const [newClaimText, setNewClaimText] = useState('')
  const [addClaimLoading, setAddClaimLoading] = useState(false)
  const [manualAcceptOpen, setManualAcceptOpen] = useState(false)
  const [manualAcceptTarget, setManualAcceptTarget] = useState<any>(null)
  const [manualAcceptReason, setManualAcceptReason] = useState('')
  const [manualAcceptLoading, setManualAcceptLoading] = useState(false)

  // Archived claims (recycle bin)
  const [archivedClaimsOpen, setArchivedClaimsOpen] = useState(false)
  const [archivedClaims, setArchivedClaims] = useState<any[]>([])
  const [archivedLoading, setArchivedLoading] = useState(false)
  const loadArchivedClaims = useCallback(async () => {
    if (!id) return
    setArchivedLoading(true)
    try {
      const items = await claimCardsApi.listArchived(id)
      setArchivedClaims(Array.isArray(items) ? items : [])
    } catch { setArchivedClaims([]) }
    finally { setArchivedLoading(false) }
  }, [id])

  // Load packet detail
  const loadPacket = useCallback(async () => {
    if (!id) return
    setPacketLoading(true)
    try {
      const res = await storyPacketsApi.get(id)
      setPacketData(res)
      return res
    } catch {
      setPacketData(null)
      return null
    } finally {
      setPacketLoading(false)
    }
  }, [id])

  useEffect(() => { loadPacket() }, [loadPacket])

  // Load claim cards with filter
  const loadClaimCards = useCallback(async () => {
    if (!id) return
    setClaimsLoading(true)
    try {
      const params: { risk_level?: string; status?: string } = {}
      if (claimRiskFilter) params.risk_level = claimRiskFilter
      if (claimStatusFilter) params.status = claimStatusFilter
      const res = await storyPacketsApi.listClaimCards(id, params)
      const items = Array.isArray(res) ? res : (res.items || [])
      setFilteredClaims(items.map((c: any, i: number) => ({
        key: c.id || String(i + 1),
        id: c.id || String(i + 1),
        claim: c.claim_text || c.claim || '',
        support: (c.supporting_evidence || []).length,
        contradiction: (c.contradicting_evidence || []).length,
        status: c.status || 'supported',
        confidence: c.confidence_score ?? 0,
        riskLevel: c.risk_level || 'L0',
        sources: c.supporting_evidence?.map((e: any) => e.title || e) || [],
        manualAcceptReason: c.manual_accept_reason || '',
      })))
    } catch {
      setFilteredClaims([])
    } finally {
      setClaimsLoading(false)
    }
  }, [id, claimRiskFilter, claimStatusFilter])

  useEffect(() => { loadClaimCards() }, [loadClaimCards])

  // Load draft
  const loadDraft = useCallback(async () => {
    if (!id) return
    setDraftLoading(true)
    try {
      const res = await storyPacketsApi.getDraft(id)
      setDraftData({ title: res.title || '', lead: res.lead || '', body: res.body || '', version: res.version || 1 })
    } catch {
      setDraftData(null)
    } finally {
      setDraftLoading(false)
    }
  }, [id])

  useEffect(() => { if (activeTab === 'draft') loadDraft() }, [activeTab, loadDraft])

  const loadDraftVersions = useCallback(async () => {
    if (!id) return
    try {
      const res = await storyPacketsApi.getDraftVersions(id)
      setDraftVersions(res)
    } catch { setDraftVersions([]) }
  }, [id])

  const handleViewVersion = async (version: number) => {
    if (!id) return
    try {
      const res = await storyPacketsApi.getDraftVersion(id, version)
      setViewingVersion(res)
    } catch { message.error('加载版本失败') }
  }

  const handleRestoreVersion = (v: any) => {
    setDraftEditTitle(v.title || '')
    setDraftEditLead(v.lead || '')
    setDraftEditBody(v.body || '')
    setIsEditingDraft(true)
    setViewingVersion(null)
    setShowVersionHistory(false)
    message.info(`已加载 v${v.version} 到编辑器，保存后将生成新版本`)
  }

  // Save draft
  const handleSaveDraft = async () => {
    if (!id) return
    setDraftSaving(true)
    try {
      const res = await storyPacketsApi.updateDraft(id, {
        title: draftEditTitle,
        lead: draftEditLead,
        body: draftEditBody,
      })
      setDraftData({ title: res.title, lead: res.lead, body: res.body, version: res.version })
      setIsEditingDraft(false)
      message.success(`草稿已保存，版本 v${res.version}`)
    } catch {
      message.error('保存失败，请重试')
    } finally {
      setDraftSaving(false)
    }
  }

  // Start editing draft
  const startEditDraft = () => {
    if (draftData) {
      setDraftEditTitle(draftData.title)
      setDraftEditLead(draftData.lead)
      setDraftEditBody(draftData.body)
    }
    setIsEditingDraft(true)
  }

  // Load workflow progress
  const loadWorkflowProgress = useCallback(async () => {
    if (!id) return
    setWorkflowLoading(true)
    try {
      const res = await workflowsApi.getStoryPacketProgress(id)
      if (res.stages && Array.isArray(res.stages)) {
        setApiWorkflowStages(res.stages.map((s: any) => ({
          key: s.key,
          label: s.name,
          status: s.state === 'completed' ? 'done' : s.state === 'current' ? 'current' : s.state === 'blocked' ? 'blocked' : 'pending',
        })))
      }
      if (res.blockers_count > 0) {
        setApiBlockers([{ id: 1, type: 'system', message: `${res.blockers_count} 个未解决的阻塞项` }])
      } else {
        setApiBlockers([])
      }
    } catch {
      // API unavailable, keep empty
    } finally {
      setWorkflowLoading(false)
    }
  }, [id])

  useEffect(() => { loadWorkflowProgress() }, [loadWorkflowProgress])

  // Load source items
  const loadSources = useCallback(async (eventCaseIdOverride?: string | null) => {
    if (!id) return
    const ecId = eventCaseIdOverride || packetData?.event_case_id
    if (!ecId) {
      setSourceItems([])
      return
    }
    setSourcesLoading(true)
    try {
      const res = await sourcesApi.list({ event_case_id: ecId })
      const items = res.items || res
      const mapped = (Array.isArray(items) ? items : []).map((s: any) => ({
        id: s.id,
        title: s.title || s.file_ref || '未命名素材',
        type: s.source_type || 'document',
        source_type: s.source_type || 'document',
        url: s.url || null,
        source: s.url || s.file_ref || '未知来源',
        credibilityTier: s.credibility_tier || null,
        credibilityScore: typeof s.credibility_score === 'number' ? s.credibility_score : null,
        verified: !s.risk_tags || s.risk_tags.length === 0,
        linkedClaims: 0,
        agentSummary: s.agent_summary || null,
        rawContent: s.raw_content || null,
      }))
      setSourceItems(mapped)
    } catch {
      setSourceItems([])
    } finally {
      setSourcesLoading(false)
    }
  }, [id, packetData?.event_case_id])

  useEffect(() => { loadSources() }, [loadSources])

  // Load risk reports
  const loadRiskReports = useCallback(async () => {
    if (!id) return
    setRiskLoading(true)
    try {
      const res = await riskReportsApi.list({ story_packet_id: id })
      setRiskReports(Array.isArray(res.items) ? res.items : [])
    } catch {
      setRiskReports([])
    } finally {
      setRiskLoading(false)
    }
  }, [id])

  useEffect(() => { loadRiskReports() }, [loadRiskReports])

  // Load channel packages
  const loadChannelPkgs = useCallback(async () => {
    if (!id) return
    setChannelLoading(true)
    try {
      const res = await channelPackagesApi.list({ story_packet_id: id })
      setChannelPkgs(Array.isArray(res.items) ? res.items : [])
    } catch {
      setChannelPkgs([])
    } finally {
      setChannelLoading(false)
    }
  }, [id])

  useEffect(() => { if (activeTab === 'channels') loadChannelPkgs() }, [activeTab, loadChannelPkgs])

  // Load evidence packs
  const loadEvidencePacks = useCallback(async () => {
    if (!id) return
    setEvidenceLoading(true)
    try {
      const res = await evidencePacksApi.list({ story_packet_id: id })
      setEvidencePacks(Array.isArray(res.items) ? res.items : [])
    } catch {
      setEvidencePacks([])
    } finally {
      setEvidenceLoading(false)
    }
  }, [id])

  useEffect(() => { loadEvidencePacks() }, [loadEvidencePacks])

  // Upload source
  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    if (id) formData.append('story_packet_id', id)
    const ecId = packetData?.event_case_id
    if (ecId) formData.append('event_case_id', ecId)
    setUploading(true)
    try {
      const uploaded = await sourcesApi.upload(formData)
      message.success('素材上传成功')
      const refreshedPacket = await loadPacket()
      loadSources(refreshedPacket?.event_case_id || null)
      // Also create evidence pack record so 证据包 tab is not empty
      if (id) {
        try {
          await evidencePacksApi.create({
            story_packet_id: id,
            sources: [{ title: file.name, source_type: 'upload', file_ref: uploaded?.id || file.name, credibility: '人工上传' }],
          })
          loadEvidencePacks()
        } catch {
          message.warning('素材已上传，但证据包记录创建失败，请重试')
        }
      }
      setUploadModalOpen(false)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.message
      message.error('上传失败：' + (detail || '请稍后重试'))
    } finally {
      setUploading(false)
    }
    return false
  }

  // View source detail
  const handleViewSource = async (sourceId: string) => {
    try {
      const detail = await sourcesApi.get(sourceId)
      setSourceDetailModal(detail)
    } catch {
      message.error('无法加载素材详情')
    }
  }

  // Add claim handler
  const handleAddClaim = async () => {
    if (!id || !newClaimText.trim()) {
      message.warning('请输入 Claim 内容')
      return
    }
    setAddClaimLoading(true)
    try {
      await claimCardsApi.create({ story_packet_id: id, claim_text: newClaimText.trim(), status: 'unverified', risk_level: 'L0' })
      message.success('Claim 已添加')
      setAddClaimOpen(false)
      setNewClaimText('')
      loadClaimCards()
    } catch {
      message.error('添加 Claim 失败')
    } finally {
      setAddClaimLoading(false)
    }
  }

  const handleManualAcceptClaim = async () => {
    if (!manualAcceptTarget?.id && !manualAcceptTarget?.key) {
      message.error('缺少 Claim 标识')
      return
    }
    if (!manualAcceptReason.trim()) {
      message.warning('请填写人工采纳理由')
      return
    }
    setManualAcceptLoading(true)
    try {
      await claimCardsApi.update(manualAcceptTarget.id || manualAcceptTarget.key, {
        status: 'manually_accepted',
        manual_accept_reason: manualAcceptReason.trim(),
      })
      message.success('已记录人工采纳理由')
      setManualAcceptOpen(false)
      setManualAcceptTarget(null)
      setManualAcceptReason('')
      loadClaimCards()
    } catch {
      message.error('人工采纳失败，请重试')
    } finally {
      setManualAcceptLoading(false)
    }
  }

  // Submit review with idempotency key
  const handleSubmitReview = async () => {
    if (!id) {
      message.error('缺少 Story Packet ID')
      return
    }
    setSubmitLoading(true)
    const idempotencyKey = `${id}-${crypto.randomUUID()}`
    try {
      const res = await storyPacketsApi.submitReview(id, { submit_note: '提交签发' }, idempotencyKey)
      if (res?.precheck && !res.precheck.passed) {
        const blockers = (res.precheck.blocking_items || []).map((b: any) => b.description || b.message || JSON.stringify(b)).join('；')
        message.error('送审预检不通过：' + (blockers || '请补全必要数据'))
      } else {
        message.success('已提交签发')
        navigate(`/sign-off/${id}`)
      }
    } catch (err: any) {
      const code = err?.response?.data?.code
      const detail = err?.response?.data?.detail || err?.response?.data?.message
      if (code === 'IDEMPOTENCY_CONFLICT') {
        message.error('重复提交冲突，请勿重复操作')
      } else if (code === 'REQUEST_IN_PROGRESS') {
        message.warning('请求处理中，请稍后')
      } else {
        message.error('提交失败：' + (detail || '未知错误'))
      }
    } finally {
      setSubmitLoading(false)
    }
  }

  const spTitle = packetData?.title || '未命名任务包'
  const spRiskLevel = packetData?.risk_level || 'L0'
  const spDeadline = packetData?.deadline ? new Date(packetData.deadline).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--:--'

  // Fallback workflow stages when API doesn't return stages
  // Uses both status progression AND data existence checks to avoid
  // marking stages as "done" when their corresponding data is empty.
  const fallbackStages = (() => {
    const STATUS_INDEX: Record<string, number> = {
      created: 4, researching: 5, verification_pending: 6, supplement: 7, redaction_gate2: 7, drafting: 8,
      editorial_review: 11, risk_review: 11, channel_packaging: 12,
      channel_review: 13, ready_to_publish: 14, published: 15, monitoring: 16,
    }
    // Data-existence gates: stages that should NOT be 'done' if the data they produce is empty
    const DATA_GATES: Record<string, boolean> = {
      source_ingestion: sourceItems.length > 0,
      ai_workpack: filteredClaims.length > 0 || evidencePacks.length > 0,
      draft_version: !!draftData,
      risk_redaction_gate3: riskReports.length > 0,
    }
    const ALL_STAGES = [
      { key: 'source_ingestion', label: '线索采集' },
      { key: 'preprocess_gate1', label: '预处理 + 脱敏门1' },
      { key: 'event_case_merge', label: '归并事件簇' },
      { key: 'human_triage', label: '人工分诊/立项' },
      { key: 'story_packet_created', label: '创建 Story Packet' },
      { key: 'ai_workpack', label: 'AI 生成工作包' },
      { key: 'human_supplement', label: '人工补充与修正' },
      { key: 'redaction_gate2', label: '脱敏门2：AI内容审查' },
      { key: 'draft_version', label: '生成基准稿' },
      { key: 'risk_redaction_gate3', label: '风控/脱敏门3' },
      { key: 'review_bundle', label: '冻结送审' },
      { key: 'approval_task', label: '人工签发' },
      { key: 'channel_package', label: '渠道适配' },
      { key: 'channel_review', label: '渠道审核' },
      { key: 'human_publish_gate', label: '确认发布' },
      { key: 'published', label: '已发布' },
      { key: 'post_monitoring', label: '发布后监测' },
    ]
    const currentIdx = STATUS_INDEX[packetData?.status] ?? 0
    return ALL_STAGES.map((s, i) => {
      let status: string
      if (i < currentIdx) {
        // Only mark as 'done' if there is no data gate or the gate passes
        const hasGate = s.key in DATA_GATES
        status = (!hasGate || DATA_GATES[s.key]) ? 'done' : 'skipped'
      } else if (i === currentIdx) {
        status = 'current'
      } else {
        status = 'pending'
      }
      return { key: s.key, label: s.label, status }
    })
  })()

  const workflowStages = apiWorkflowStages.length > 0 ? apiWorkflowStages : fallbackStages

  // Derive claim stats from filteredClaims
  const claimStats = {
    total: filteredClaims.length,
    supported: filteredClaims.filter(c => c.status === 'supported' || c.status === 'manually_accepted').length,
    disputed: filteredClaims.filter(c => c.status === 'disputed').length,
    insufficient: filteredClaims.filter(c => c.status === 'insufficient').length,
    pending: filteredClaims.filter(c => !['supported', 'disputed', 'insufficient', 'manually_accepted'].includes(c.status)).length,
  }

  // Determine which workflow stages are completed to control tab visibility
  const completedStageKeys = new Set(
    workflowStages.filter((s: any) => s.status === 'done').map((s: any) => s.key)
  )
  const stageReached = (targetKey: string) => {
    const targetIdx = workflowStages.findIndex((s: any) => s.key === targetKey)
    const currentIdx = workflowStages.findIndex((s: any) => s.status === 'current')
    if (targetIdx < 0) return true
    return targetIdx <= currentIdx || completedStageKeys.has(targetKey)
  }
  // Draft tab only after 'draft_version' or 'ai_workpack' stage is reached
  const showDraftTab = stageReached('draft_version') || stageReached('ai_workpack') || stageReached('redaction_gate2') || (packetData?.status && ['drafting', 'editorial_review', 'risk_review', 'channel_packaging', 'channel_review', 'ready_to_publish', 'published', 'monitoring'].includes(packetData.status))
  // Risk tab only after 'risk_redaction_gate3' stage or risk_review status
  const showRiskTab = stageReached('risk_redaction_gate3') || (packetData?.status && ['risk_review', 'channel_packaging', 'channel_review', 'ready_to_publish', 'published', 'monitoring'].includes(packetData.status))
  // Channels tab only after 'channel_package' stage
  const showChannelsTab = stageReached('channel_package') || (packetData?.status && ['channel_packaging', 'channel_review', 'ready_to_publish', 'published', 'monitoring'].includes(packetData.status))

  const tabs = [
    { key: 'claims', label: 'Claim Cards', icon: <FileTextOutlined />, count: claimStats.total },
    { key: 'evidence-pack', label: '证据包', icon: <FolderOpenOutlined />, count: evidencePacks.length },
    { key: 'evidence', label: '来源素材', icon: <FolderOpenOutlined />, count: sourceItems.length },
    ...(showDraftTab ? [{ key: 'draft', label: '正文草稿', icon: <EditOutlined /> }] : []),
    ...(showRiskTab ? [{ key: 'risk', label: '风险报告', icon: <ExclamationCircleOutlined /> }] : []),
    ...(showChannelsTab ? [{ key: 'channels', label: '渠道稿件', icon: <LinkOutlined /> }] : []),
  ]

  const claimColumns = [
    {
      title: 'CLAIM',
      dataIndex: 'claim',
      key: 'claim',
      render: (text: string, record: any) => (
        <div>
          <div style={{ marginBottom: 4 }}>{text}</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {(record.sources || []).map((s: string, i: number) => (
              <Tag key={i} style={{ fontSize: 10, background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD }}>{s}</Tag>
            ))}
          </div>
          {record.manualAcceptReason && (
            <div style={{ marginTop: 8, fontSize: 12, color: GOLD }}>人工采纳理由：{record.manualAcceptReason}</div>
          )}
        </div>
      ),
    },
    {
      title: '风险',
      dataIndex: 'riskLevel',
      key: 'riskLevel',
      width: 80,
      render: (level: string) => (
        <Tag style={{ background: riskColors[level], border: 'none', color: getRiskTextColor(level) }}>{level}</Tag>
      ),
    },
    {
      title: '支持/矛盾',
      key: 'supportContradiction',
      width: 100,
      render: (_: unknown, record: any) => (
        <span>
          <span style={{ color: '#22c55e' }}>{record.support}</span>
          {' / '}
          <span style={{ color: record.contradiction > 0 ? '#ef4444' : '#71717a' }}>{record.contradiction}</span>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const meta = claimStatusMeta[status] || { label: status, background: '#71717a', color: '#fff' }
        return <Tag style={{ background: meta.background, border: 'none', color: meta.color }}>{meta.label}</Tag>
      },
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 80,
      render: (val: number) => (
        <Progress 
          percent={Math.round(val * 100)} 
          size="small" 
          strokeColor={val > 0.7 ? '#22c55e' : val > 0.4 ? '#faad14' : '#ef4444'}
          style={{ width: 60 }}
        />
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 170,
      render: (_: unknown, record: any) => (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
          <Button
            type="text"
            size="small"
            icon={<CheckCircleOutlined />}
            style={{ color: GOLD }}
            onClick={() => {
              setManualAcceptTarget(record)
              setManualAcceptReason(record.manualAcceptReason || '')
              setManualAcceptOpen(true)
            }}
          >
            {record.status === 'manually_accepted' ? '编辑理由' : '人工采纳'}
          </Button>
          <Button
            type="text"
            size="small"
            icon={<DeleteOutlined />}
            style={{ color: '#ef4444' }}
            onClick={() => {
              Modal.confirm({
                title: '删除 Claim',
                content: `确定要删除 "${record.claim.slice(0, 40)}…" 吗？删除后可在回收站恢复。`,
                okText: '删除',
                okButtonProps: { danger: true },
                cancelText: '取消',
                onOk: async () => {
                  try {
                    await claimCardsApi.delete(record.key)
                    message.success('已删除')
                    loadClaimCards()
                  } catch {
                    message.error('删除失败')
                  }
                },
              })
            }}
          />
        </div>
      ),
    },
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#0A0A0A', color: TEXT_PRIMARY }}>
      {/* 顶部导航栏 */}
      <div style={{
        height: 56,
        background: BG_CARD,
        borderBottom: `1px solid ${BORDER}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/story-packets')}
            style={{ color: TEXT_MUTED }}
          >
            返回列表
          </Button>
          <div style={{ width: 1, height: 24, background: BORDER }} />
          <span style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY }}>
            《{spTitle}》
          </span>
          <Button type="text" size="small" icon={<EditOutlined />} style={{ color: TEXT_MUTED }} onClick={() => { const newName = window.prompt('重命名任务包', spTitle); if (newName && newName.trim() && newName !== spTitle && id) { storyPacketsApi.update(id, { title: newName.trim() }).then(() => { message.success('已重命名'); loadPacket(); }).catch(() => message.error('重命名失败')); } }} />
          <Tag style={{ background: riskColors[spRiskLevel], border: 'none', color: getRiskTextColor(spRiskLevel), fontSize: 11 }}>
            {spRiskLevel} 风险
          </Tag>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ClockCircleOutlined style={{ color: GOLD }} />
            <span style={{ color: GOLD, fontSize: 13 }}>截止 {spDeadline}</span>
          </div>
          {(() => {
            const canSubmit = !!draftData && !!id
            return canSubmit ? (
              <Button type="primary" style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }} loading={submitLoading} onClick={handleSubmitReview}>
                提交签发 <RightOutlined />
              </Button>
            ) : (
              <Button disabled style={{ opacity: 0.5, color: 'rgba(245,245,245,0.6)', borderColor: 'rgba(245,245,245,0.2)' }} title="请先完成稿件起草后再提交签发">
                提交签发 <RightOutlined />
              </Button>
            )
          })()}
        </div>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 56px)' }}>
        {/* 左侧信息栏 */}
        <div style={{
          width: 280,
          background: '#0A0A0A',
          borderRight: `1px solid ${BORDER}`,
          padding: 20,
          overflow: 'auto'
        }}>
          {/* 工作流进度 */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>工作流阶段</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {workflowStages.map((stage, i) => (
                <div key={stage.key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    background: stage.status === 'done' ? '#22c55e' : stage.status === 'current' ? GOLD : 'rgba(245,245,245,0.08)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: stage.status === 'done' || stage.status === 'current' ? '#0A0A0A' : TEXT_MUTED
                  }}>
                    {stage.status === 'done' ? <CheckCircleOutlined /> : i + 1}
                  </div>
                  <span style={{ color: stage.status === 'pending' ? TEXT_MUTED : stage.status === 'current' ? GOLD : TEXT_PRIMARY, fontSize: 13 }}>
                    {stage.label}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* 阻塞项 */}
          {apiBlockers.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>阻塞项</div>
              <div style={{
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 8,
                padding: 12
              }}>
                <div style={{ color: '#ef4444', fontWeight: 500, marginBottom: 8, fontSize: 13 }}>
                  <ExclamationCircleOutlined style={{ marginRight: 8 }} />
                  {apiBlockers.length} 个阻塞项
                </div>
                {apiBlockers.map((b: any) => (
                  <div key={b.id} style={{ color: '#fca5a5', fontSize: 12, marginTop: 4 }}>
                    • {b.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Claim统计 */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Claim 核实状态</div>
            <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 13 }}>
                <span style={{ color: TEXT_SECONDARY }}>总数</span>
                <span style={{ color: TEXT_PRIMARY, fontFamily: 'Georgia, serif' }}>{claimStats.total}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 13 }}>
                <span style={{ color: TEXT_SECONDARY }}>已支持</span>
                <span style={{ color: '#22c55e', fontFamily: 'Georgia, serif' }}>{claimStats.supported}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 13 }}>
                <span style={{ color: TEXT_SECONDARY }}>有争议</span>
                <span style={{ color: '#f97316', fontFamily: 'Georgia, serif' }}>{claimStats.disputed}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: TEXT_SECONDARY }}>证据不足</span>
                <span style={{ color: '#ef4444', fontFamily: 'Georgia, serif' }}>{claimStats.insufficient}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginTop: 8 }}>
                <span style={{ color: TEXT_SECONDARY }}>待核验/其他</span>
                <span style={{ color: GOLD, fontFamily: 'Georgia, serif' }}>{claimStats.pending}</span>
              </div>
              <Progress
                percent={claimStats.total > 0 ? Math.round((claimStats.supported / claimStats.total) * 100) : 0}
                size="small"
                style={{ marginTop: 12 }}
                strokeColor="#22c55e"
                trailColor="rgba(245,245,245,0.1)"
              />
            </div>
          </div>

          {/* 关系图谱摘要 */}
          <div>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>关系图谱</div>
            <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, color: TEXT_MUTED, fontSize: 12, border: `1px solid ${BORDER}` }}>
              暂无关系图谱数据
            </div>
          </div>
        </div>

        {/* 主内容区 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Tab 导航 */}
          <div style={{
            display: 'flex',
            borderBottom: `1px solid ${BORDER}`,
            background: BG_CARD,
            padding: '0 24px'
          }}>
            {tabs.map(tab => (
              <div
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: '12px 18px',
                  cursor: 'pointer',
                  borderBottom: activeTab === tab.key ? `2px solid ${GOLD}` : '2px solid transparent',
                  color: activeTab === tab.key ? GOLD : TEXT_MUTED,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13,
                  transition: 'all 0.2s'
                }}
              >
                {tab.icon}
                {tab.label}
                {tab.count !== undefined && (
                  <span style={{
                    background: activeTab === tab.key ? 'rgba(212,168,83,0.2)' : 'rgba(245,245,245,0.08)',
                    color: activeTab === tab.key ? GOLD : TEXT_MUTED,
                    padding: '2px 6px',
                    borderRadius: 10,
                    fontSize: 11
                  }}>
                    {tab.count}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* 内容区 */}
          <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
            {activeTab === 'claims' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>Claim Cards ({filteredClaims.length})</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Button icon={<DeleteOutlined />} onClick={() => { setArchivedClaimsOpen(true); loadArchivedClaims() }} style={{ background: BG_CARD, borderColor: BORDER, color: TEXT_SECONDARY }}>回收站</Button>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddClaimOpen(true)} style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>添加 Claim</Button>
                  </div>
                </div>
                {/* 筛选区 */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
                  <FilterOutlined style={{ color: TEXT_MUTED }} />
                  <Select
                    placeholder="风险等级"
                    allowClear
                    style={{ width: 140 }}
                    value={claimRiskFilter}
                    onChange={(val) => setClaimRiskFilter(val)}
                    options={[
                      { value: 'L0', label: 'L0' },
                      { value: 'L1', label: 'L1' },
                      { value: 'L2', label: 'L2' },
                      { value: 'L3', label: 'L3' },
                    ]}
                  />
                  <Select
                    placeholder="状态"
                    allowClear
                    style={{ width: 160 }}
                    value={claimStatusFilter}
                    onChange={(val) => setClaimStatusFilter(val)}
                    options={[
                      { value: 'supported', label: 'Supported' },
                      { value: 'disputed', label: 'Disputed' },
                      { value: 'insufficient', label: 'Insufficient' },
                      { value: 'manually_accepted', label: '人工采纳' },
                    ]}
                  />
                </div>
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${BORDER}` }}>
                  <Spin spinning={claimsLoading}>
                    <Table
                      columns={claimColumns}
                      dataSource={filteredClaims}
                      pagination={false}
                      size="small"
                      rowClassName={() => 'dark-table-row'}
                    />
                  </Spin>
                </div>
              </div>
            )}

            {activeTab === 'evidence' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>来源素材 ({sourceItems.length})</h3>
                  <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadModalOpen(true)} style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>上传素材</Button>
                </div>
                <Spin spinning={sourcesLoading}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                    {sourceItems.map(ev => (
                      <div key={ev.id} style={{
                        background: BG_CARD,
                        borderRadius: 10,
                        padding: 16,
                        border: `1px solid ${BORDER}`,
                        cursor: 'pointer',
                        transition: 'border-color 0.2s',
                      }}
                        onClick={() => handleViewSource(ev.id)}
                        onMouseEnter={(e) => e.currentTarget.style.borderColor = GOLD_BORDER}
                        onMouseLeave={(e) => e.currentTarget.style.borderColor = BORDER}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <FolderOpenOutlined style={{ color: GOLD, fontSize: 18 }} />
                            <span style={{ fontWeight: 500, color: TEXT_PRIMARY }}>{ev.title}</span>
                          </div>
                          {ev.verified ? (
                            <Tag style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', color: '#22c55e', fontSize: 11 }} icon={<CheckCircleOutlined />}>已核实</Tag>
                          ) : (
                            <Tag style={{ background: 'rgba(234,179,8,0.15)', border: '1px solid rgba(234,179,8,0.3)', color: '#eab308', fontSize: 11 }} icon={<ExclamationCircleOutlined />}>待核实</Tag>
                          )}
                        </div>
                        <div style={{ color: TEXT_MUTED, fontSize: 12, marginBottom: 4 }}>
                          来源: {ev.source}
                          {(ev.credibilityTier || ev.type) && (() => {
                            const credMap: Record<string, { label: string; color: string }> = {
                              '官方/监管': { label: '官方/监管', color: '#22c55e' },
                              '主流媒体': { label: '主流媒体', color: '#3b82f6' },
                              '公开网络来源': { label: '公开网络来源', color: '#eab308' },
                              '社交媒体': { label: '社交媒体', color: '#f97316' },
                              '记者线索': { label: '记者线索', color: '#a855f7' },
                              '人工上传': { label: '人工上传', color: '#8b5cf6' },
                              '网络来源': { label: '网络来源', color: '#71717a' },
                            };
                            const c = credMap[ev.credibilityTier] || null;
                            if (!c) return null;
                            return <span style={{ marginLeft: 8, color: c.color, fontSize: 11 }}>· {c.label}{typeof ev.credibilityScore === 'number' ? ` (${Math.round(ev.credibilityScore * 100)}分)` : ''}</span>;
                          })()}
                        </div>
                        {ev.url && <div style={{ fontSize: 11, marginBottom: 4 }}><a href={ev.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3b82f6' }} onClick={e => e.stopPropagation()}>🔗 {ev.url.length > 50 ? ev.url.slice(0, 50) + '...' : ev.url}</a></div>}
                        {ev.uploaded_by && <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 4 }}>上传者: <span style={{ color: TEXT_SECONDARY }}>{ev.uploaded_by}</span></div>}
                        <div style={{ color: TEXT_MUTED, fontSize: 12 }}>关联 Claim: {ev.linkedClaims} 条</div>
                      </div>
                    ))}
                  </div>
                </Spin>
              </div>
            )}

            {activeTab === 'evidence-pack' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>证据包 ({evidencePacks.length})</h3>
                  <Button type="primary" icon={<UploadOutlined />}
                    style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
                    onClick={() => {
                      const input = document.createElement('input');
                      input.type = 'file';
                      input.accept = '.pdf,.doc,.docx,.txt,.csv,.json,.png,.jpg,.jpeg,.gif,.bmp,.webp';
                      input.onchange = async (ev: any) => {
                        const file = ev.target?.files?.[0];
                        if (!file || !id) return;
                        const formData = new FormData();
                        formData.append('file', file);
                        formData.append('story_packet_id', id);
                        if (packetData?.event_case_id) formData.append('event_case_id', packetData.event_case_id);
                        setUploading(true);
                        try {
                          const { sourcesApi } = await import('@/services/api');
                          const uploaded = await sourcesApi.upload(formData);
                          message.success(`「${file.name}」上传成功`);
                          const refreshedPacket = await loadPacket();
                          try {
                            await evidencePacksApi.create({
                              story_packet_id: id,
                              sources: [{ title: file.name, source_type: 'upload', file_ref: uploaded?.id || file.name, credibility: '人工上传' }],
                            });
                          } catch {
                            message.warning('素材已上传，但证据包记录创建失败，请重试');
                          }
                          loadEvidencePacks();
                          loadSources(refreshedPacket?.event_case_id || null);
                        } catch (err: any) {
                          const detail = err?.response?.data?.detail || err?.response?.data?.message;
                          message.error('上传失败：' + (detail || '请稍后重试'));
                        } finally { setUploading(false); }
                      };
                      input.click();
                    }}
                  >上传证据</Button>
                </div>
                <Spin spinning={evidenceLoading}>
                {evidencePacks.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <FolderOpenOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                    <div style={{ color: TEXT_MUTED }}>暂无证据包数据</div>
                  </div>
                ) : evidencePacks.map((ep: any) => {
                  const sources = typeof ep.sources === 'string' ? JSON.parse(ep.sources || '[]') : (ep.sources || []);
                  const anchors = typeof ep.citation_anchors === 'string' ? JSON.parse(ep.citation_anchors || '[]') : (ep.citation_anchors || []);
                  // Credibility level helper (Issue 8)
                  const getCredibilityLevel = (src: any) => {
                    if (src.credibility) return src.credibility;
                    if (src.source_type === 'government' || src.source_type === 'official') return '官方/监管';
                    if (src.source_type === 'mainstream_media' || src.source_type === 'rss') return '主流媒体';
                    if (src.source_type === 'social_media') return '社交媒体';
                    if (src.source_type === 'upload') return '人工上传';
                    if (src.source_type === 'website') return '公开网络来源';
                    return null;
                  };
                  const credibilityConfig: Record<string, { bg: string; color: string }> = {
                    '官方/监管': { bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
                    '主流媒体': { bg: 'rgba(59,130,246,0.15)', color: '#3b82f6' },
                    '公开网络来源': { bg: 'rgba(234,179,8,0.15)', color: '#eab308' },
                    '社交媒体': { bg: 'rgba(249,115,22,0.15)', color: '#f97316' },
                    '记者线索': { bg: 'rgba(168,85,247,0.15)', color: '#a855f7' },
                    '人工上传': { bg: 'rgba(139,92,246,0.15)', color: '#8b5cf6' },
                    '网络来源': { bg: 'rgba(234,179,8,0.15)', color: '#eab308' },
                    '高': { bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
                    '中': { bg: 'rgba(234,179,8,0.15)', color: '#eab308' },
                    '低': { bg: 'rgba(239,68,68,0.15)', color: '#ef4444' },
                  };
                  return (
                    <div key={ep.id} style={{ background: BG_CARD, borderRadius: 10, padding: 20, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: TEXT_PRIMARY }}>证据包 v{ep.version}</span>
                          {ep.is_snapshot && <Tag style={{ background: 'rgba(59,130,246,0.15)', border: 'none', color: '#3b82f6', fontSize: 10 }}>快照</Tag>}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {ep.completeness_score != null && (
                            <Tag style={{ background: ep.completeness_score >= 0.8 ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)', border: 'none', color: ep.completeness_score >= 0.8 ? '#22c55e' : '#eab308', fontSize: 11 }}>
                              完整度 {Math.round(ep.completeness_score * 100)}%
                            </Tag>
                          )}
                          <Button size="small" icon={<EyeOutlined />} onClick={() => {
                            setExpandedEpIds(prev => {
                              const next = new Set(prev)
                              if (next.has(ep.id)) next.delete(ep.id); else next.add(ep.id)
                              return next
                            })
                          }} style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD, fontSize: 11 }}>{expandedEpIds.has(ep.id) ? '收起' : '查看'}</Button>
                          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => { Modal.confirm({ title: '确认删除', content: `是否确认删除证据包 v${ep.version}？删除后可在回收站恢复。`, okText: '删除', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { await evidencePacksApi.delete(ep.id); message.success('证据包已删除'); loadEvidencePacks(); } catch { message.error('删除失败'); } } }); }} style={{ fontSize: 11 }}>删除</Button>
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>{ep.created_at ? new Date(ep.created_at).toLocaleString('zh-CN') : ''}</span>
                        </div>
                      </div>
                      {!expandedEpIds.has(ep.id) && <div style={{ fontSize: 12, color: TEXT_MUTED }}>来源 {sources.length} 条 · 锚点 {anchors.length} 条</div>}
                      {expandedEpIds.has(ep.id) && <>
                      <div style={{ fontSize: 12, color: GOLD, marginBottom: 8, fontWeight: 500 }}>关联来源 ({sources.length})</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
                        {sources.map((src: any, i: number) => {
                          const cred = getCredibilityLevel(src);
                          const credStyle = cred ? credibilityConfig[cred] || { bg: 'rgba(245,245,245,0.08)', color: TEXT_MUTED } : null;
                          return (
                            <div key={i} style={{ background: '#0A0A0A', borderRadius: 6, padding: '8px 12px', border: `1px solid ${BORDER}`, fontSize: 12 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                                <div style={{ fontWeight: 500, color: TEXT_PRIMARY }}>{src.title || src.url || `来源 #${i+1}`}</div>
                                {credStyle && <Tag style={{ fontSize: 10, background: credStyle.bg, border: 'none', color: credStyle.color }}>可信度: {cred}</Tag>}
                              </div>
                              {src.snippet && <div style={{ color: TEXT_SECONDARY, fontSize: 11 }}>{src.snippet}</div>}
                              {src.url && <div style={{ marginTop: 2 }}><a href={src.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3b82f6', fontSize: 11, wordBreak: 'break-all' }}>🔗 {src.url}</a></div>}
                              {src.uploader && <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 2 }}>上传者: <span style={{ color: TEXT_SECONDARY }}>{src.uploader}</span></div>}
                              {src.file_ref && (
                                <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 2, cursor: 'pointer' }} onClick={() => message.info(`源文件: ${src.file_ref}`)}>
                                  📄 源文件: <span style={{ color: '#3b82f6', textDecoration: 'underline' }}>{src.file_ref}</span>
                                </div>
                              )}
                              {src.original_text && (
                                <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 4, padding: '4px 8px', background: 'rgba(245,245,245,0.03)', borderRadius: 4, borderLeft: `2px solid ${GOLD_BORDER}` }}>
                                  原话: <span style={{ color: TEXT_SECONDARY, fontStyle: 'italic' }}>"{src.original_text.length > 100 ? src.original_text.slice(0, 100) + '...' : src.original_text}"</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                      {anchors.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: GOLD, marginBottom: 8, fontWeight: 500 }}>引用锚点 ({anchors.length})</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {anchors.map((a: any, i: number) => {
                              const label = typeof a === 'string' ? a : (a.label || a.claim_id || `锚点 #${i+1}`);
                              const href = typeof a === 'object' && a.url ? a.url : null;
                              const claimRef = typeof a === 'object' && a.claim_id ? a.claim_id : null;
                              return (
                                <Tag
                                  key={i}
                                  style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11, cursor: 'pointer' }}
                                  onClick={() => {
                                    if (href) {
                                      window.open(href, '_blank');
                                    } else if (claimRef) {
                                      setActiveTab('claims');
                                      message.info(`跳转至 Claim: ${claimRef.slice(0, 8)}`);
                                    } else {
                                      message.info(`锚点: ${label}`);
                                    }
                                  }}
                                >
                                  {href ? '🔗 ' : claimRef ? '📌 ' : ''}{label}
                                </Tag>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      </>}
                    </div>
                  );
                })}
                </Spin>
              </div>
            )}

            {activeTab === 'risk' && (
              <div>
                <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600, marginBottom: 16 }}>风险报告 (Redaction & Risk Agent)</h3>
                <Spin spinning={riskLoading}>
                {riskReports.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <ExclamationCircleOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                    <div style={{ color: TEXT_MUTED }}>暂无风险报告</div>
                  </div>
                ) : riskReports.map((rr: any) => {
                  const findings = typeof rr.findings === 'string' ? JSON.parse(rr.findings || '[]') : (rr.findings || []);
                  const severity = typeof rr.severity_summary === 'string' ? JSON.parse(rr.severity_summary || '{}') : (rr.severity_summary || {});
                  const recs = typeof rr.recommendations === 'string' ? JSON.parse(rr.recommendations || '[]') : (rr.recommendations || []);
                  return (
                    <div key={rr.id} style={{ background: BG_CARD, borderRadius: 10, padding: 20, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Tag style={{ background: rr.report_type === 'risk' ? 'rgba(239,68,68,0.15)' : 'rgba(234,179,8,0.15)', border: 'none', color: rr.report_type === 'risk' ? '#ef4444' : '#eab308', fontSize: 11 }}>
                            {rr.report_type === 'risk' ? '风险扫描' : '脱敏审查'}
                          </Tag>
                          <span style={{ fontSize: 14, fontWeight: 600, color: TEXT_PRIMARY }}>v{rr.version}</span>
                          <Tag style={{ background: 'rgba(212,168,83,0.1)', border: 'none', color: GOLD, fontSize: 10 }}>
                            {rr.generated_by === 'system' ? 'Agent 生成' : '人工审核'}
                          </Tag>
                        </div>
                        <span style={{ fontSize: 11, color: TEXT_MUTED }}>{rr.created_at ? new Date(rr.created_at).toLocaleString('zh-CN') : ''}</span>
                      </div>
                      {/* severity summary */}
                      {Object.keys(severity).length > 0 && (
                        <div style={{ background: 'rgba(239,68,68,0.05)', borderRadius: 8, padding: 12, marginBottom: 12, border: '1px solid rgba(239,68,68,0.15)' }}>
                          <div style={{ fontSize: 12, color: '#ef4444', fontWeight: 500, marginBottom: 6 }}>严重程度摘要</div>
                          <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                            {Object.entries(severity).map(([k, v]) => (
                              <div key={k}><span style={{ color: TEXT_MUTED }}>{k}: </span><span style={{ color: TEXT_PRIMARY, fontWeight: 500 }}>{String(v)}</span></div>
                            ))}
                          </div>
                        </div>
                      )}
                      {/* findings */}
                      <div style={{ fontSize: 12, color: GOLD, fontWeight: 500, marginBottom: 8 }}>发现项 ({findings.length})</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
                        {findings.map((f: any, i: number) => (
                          <div key={i} style={{ background: '#0A0A0A', borderRadius: 6, padding: '8px 12px', border: `1px solid ${BORDER}`, fontSize: 12, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                            <ExclamationCircleOutlined style={{ color: (f.severity === 'L3' || f.severity === 'L2' || f.raw_severity === 'critical' || f.raw_severity === 'high' || f.severity === 'high' || f.severity === '高') ? '#ef4444' : '#eab308', marginTop: 2, flexShrink: 0 }} />
                            <div>
                              <div style={{ fontWeight: 500, color: TEXT_PRIMARY }}>{f.issue || f.title || (typeof f === 'string' ? f : JSON.stringify(f))}</div>
                              {f.location && <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 2 }}>位置: {f.location}</div>}
                              {f.suggestion && <div style={{ color: TEXT_SECONDARY, fontSize: 11, marginTop: 2 }}>建议: {f.suggestion}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                      {/* recommendations */}
                      {recs && recs.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: '#22c55e', fontWeight: 500, marginBottom: 8 }}>处置建议</div>
                          {recs.map((r: any, i: number) => (
                            <div key={i} style={{ fontSize: 12, color: TEXT_SECONDARY, marginBottom: 4, paddingLeft: 12, borderLeft: '2px solid rgba(34,197,94,0.3)' }}>
                              {typeof r === 'string' ? r : r.text || JSON.stringify(r)}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                </Spin>
              </div>
            )}

            {activeTab === 'channels' && (
              <div>
                <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600, marginBottom: 16 }}>渠道稿件 (Channel Adapt Agent)</h3>
                <Spin spinning={channelLoading}>
                {channelPkgs.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <LinkOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                    <div style={{ color: TEXT_MUTED }}>暂无渠道稿件</div>
                  </div>
                ) : channelPkgs.map((cp: any) => {
                  const content = typeof cp.content === 'string' ? JSON.parse(cp.content || '{}') : (cp.content || {});
                  const displayTitle = content.title || cp.title || '';
                  const displayLead = content.lead || content.summary || content.push_summary || '';
                  const displayBody = content.body || content.text || content.summary || content.push_summary || '';
                  const channelLabels: Record<string, { label: string; color: string }> = {
                    wechat: { label: '微信公众号', color: '#22c55e' },
                    wechat_mp: { label: '微信公众号', color: '#22c55e' },
                    weibo: { label: '微博', color: '#ef4444' },
                    app_push: { label: 'APP推送', color: '#3b82f6' },
                    website: { label: '网站', color: '#8b5cf6' },
                    web: { label: '网站', color: '#8b5cf6' },
                    print: { label: '印刷版', color: '#f97316' },
                    video: { label: '视频', color: '#ec4899' },
                    video_script: { label: '视频脚本', color: '#ec4899' },
                    push_title: { label: '推送标题', color: '#3b82f6' },
                  };
                  const ch = channelLabels[cp.channel_type] || { label: cp.channel_type, color: '#71717a' };
                  const statusLabels: Record<string, string> = { draft: '草稿', reviewing: '审核中', approved: '已通过', published: '已发布', rejected: '已驳回' };
                  return (
                    <div key={cp.id} style={{ background: BG_CARD, borderRadius: 10, padding: 20, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Tag style={{ background: `${ch.color}22`, border: 'none', color: ch.color, fontSize: 12, fontWeight: 500 }}>{ch.label}</Tag>
                          <Tag style={{ background: 'rgba(245,245,245,0.08)', border: 'none', color: TEXT_SECONDARY, fontSize: 11 }}>{statusLabels[cp.status] || cp.status}</Tag>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {cp.drift_score != null && (
                            <Tag style={{ background: cp.drift_score <= cp.drift_threshold ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', border: 'none', color: cp.drift_score <= cp.drift_threshold ? '#22c55e' : '#ef4444', fontSize: 11 }}>
                              内容偏离度 {Math.round(cp.drift_score * 100)}%{cp.drift_score <= cp.drift_threshold ? '（合格）' : '（超标）'}
                            </Tag>
                          )}
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>{cp.created_at ? new Date(cp.created_at).toLocaleString('zh-CN') : ''}</span>
                        </div>
                      </div>
                      {/* content */}
                      <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 16, border: `1px solid ${BORDER}`, lineHeight: 1.8 }}>
                        {displayTitle && <h4 style={{ color: TEXT_PRIMARY, marginBottom: 8, fontSize: 14 }}>{displayTitle}</h4>}
                        {displayLead && <p style={{ color: GOLD, fontSize: 13, fontStyle: 'italic', marginBottom: 12 }}>{displayLead}</p>}
                        {displayBody ? (
                          <div style={{ color: TEXT_SECONDARY, fontSize: 13 }}>
                            {String(displayBody).split('\n').map((p: string, i: number) => <p key={i} style={{ marginTop: i > 0 ? 8 : 0 }}>{p}</p>)}
                          </div>
                        ) : (
                          <div style={{ color: TEXT_MUTED, fontSize: 12 }}>（无正文内容）</div>
                        )}
                        {content.hashtags && (
                          <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {content.hashtags.map((h: string, i: number) => (
                              <Tag key={i} style={{ background: 'rgba(212,168,83,0.1)', border: 'none', color: GOLD, fontSize: 11 }}>#{h}</Tag>
                            ))}
                          </div>
                        )}
                        {content.char_count && <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 8 }}>字数: {content.char_count}</div>}
                      </div>
                      {/* published info */}
                      {cp.published_url && (
                        <div style={{ marginTop: 8, fontSize: 12 }}>
                          <span style={{ color: TEXT_MUTED }}>发布链接: </span>
                          <a href={cp.published_url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>{cp.published_url}</a>
                        </div>
                      )}
                      {cp.published_at && <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 4 }}>发布时间: {new Date(cp.published_at).toLocaleString('zh-CN')}</div>}
                    </div>
                  );
                })}
                </Spin>
              </div>
            )}

            {activeTab === 'draft' && (
              <Spin spinning={draftLoading}>
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>正文草稿 · v{draftData?.version || 1}</h3>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Button size="small" onClick={() => { setShowVersionHistory(!showVersionHistory); if (!showVersionHistory) loadDraftVersions() }}
                        style={{ background: 'rgba(212,168,83,0.05)', borderColor: GOLD_BORDER, color: showVersionHistory ? GOLD : TEXT_MUTED, fontSize: 12 }}>
                        {showVersionHistory ? '收起历史' : '版本历史'}
                      </Button>
                      {isEditingDraft ? (
                        <>
                          <Button onClick={() => setIsEditingDraft(false)} style={{ background: BG_CARD, borderColor: BORDER, color: TEXT_SECONDARY }}>取消</Button>
                          <Button type="primary" icon={<SaveOutlined />} loading={draftSaving} onClick={handleSaveDraft} style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>保存</Button>
                        </>
                      ) : (
                        <Button icon={<EditOutlined />} onClick={startEditDraft} style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD }}>编辑</Button>
                      )}
                    </div>
                  </div>

                  {showVersionHistory && (
                    <div style={{ marginBottom: 16, background: '#0A0A0A', borderRadius: 8, padding: 16, border: `1px solid ${BORDER}` }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: TEXT_PRIMARY, marginBottom: 10 }}>📋 版本历史 ({draftVersions.length} 个版本)</div>
                      {draftVersions.length === 0 ? (
                        <div style={{ color: TEXT_MUTED, fontSize: 12 }}>暂无版本记录</div>
                      ) : (
                        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                          {draftVersions.map((v: any) => (
                            <div key={v.id} style={{
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              padding: '8px 10px', borderRadius: 6, marginBottom: 4,
                              background: viewingVersion?.id === v.id ? 'rgba(212,168,83,0.1)' : 'transparent',
                              border: `1px solid ${viewingVersion?.id === v.id ? GOLD_BORDER : 'transparent'}`,
                              cursor: 'pointer',
                            }} onClick={() => handleViewVersion(v.version)}>
                              <div>
                                <span style={{ color: GOLD, fontWeight: 600, fontSize: 12 }}>v{v.version}</span>
                                <span style={{ color: TEXT_MUTED, marginLeft: 8, fontSize: 11 }}>
                                  {v.title || '(无标题)'} · {v.word_count || 0} 字
                                </span>
                                <span style={{ color: TEXT_MUTED, marginLeft: 8, fontSize: 11 }}>
                                  {v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : ''}
                                </span>
                              </div>
                              <div style={{ display: 'flex', gap: 4 }}>
                                {v.version !== draftData?.version && (
                                  <Button size="small" type="link" style={{ color: GOLD, fontSize: 11, padding: '0 4px' }}
                                    onClick={(e) => { e.stopPropagation(); handleRestoreVersion(v) }}>
                                    恢复此版本
                                  </Button>
                                )}
                                {v.version === draftData?.version && (
                                  <Tag color="gold" style={{ fontSize: 10, margin: 0 }}>当前</Tag>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      {viewingVersion && viewingVersion.version !== draftData?.version && (
                        <div style={{ marginTop: 12, padding: 12, background: '#111', borderRadius: 6, border: `1px solid ${GOLD_BORDER}` }}>
                          <div style={{ fontSize: 12, color: GOLD, marginBottom: 8, fontWeight: 600 }}>预览 v{viewingVersion.version}</div>
                          {viewingVersion.title && <div style={{ color: TEXT_PRIMARY, fontWeight: 500, marginBottom: 4 }}>{viewingVersion.title}</div>}
                          {viewingVersion.lead && <div style={{ color: TEXT_MUTED, fontStyle: 'italic', marginBottom: 8, fontSize: 13 }}>{viewingVersion.lead}</div>}
                          <div style={{ color: TEXT_SECONDARY, fontSize: 13, lineHeight: 1.6, maxHeight: 150, overflowY: 'auto' }}>
                            {viewingVersion.body ? viewingVersion.body.substring(0, 500) + (viewingVersion.body.length > 500 ? '...' : '') : '(无正文)'}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {isEditingDraft ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <div>
                        <div style={{ color: TEXT_MUTED, marginBottom: 4, fontSize: 12 }}>标题</div>
                        <Input value={draftEditTitle} onChange={e => setDraftEditTitle(e.target.value)} style={{ background: '#0E0E0E', borderColor: GOLD_BORDER, color: TEXT_PRIMARY }} />
                      </div>
                      <div>
                        <div style={{ color: TEXT_MUTED, marginBottom: 4, fontSize: 12 }}>导语</div>
                        <Input.TextArea rows={2} value={draftEditLead} onChange={e => setDraftEditLead(e.target.value)} style={{ background: '#0E0E0E', borderColor: GOLD_BORDER, color: TEXT_PRIMARY }} />
                      </div>
                      <div>
                        <div style={{ color: TEXT_MUTED, marginBottom: 4, fontSize: 12 }}>正文</div>
                        <Input.TextArea rows={10} value={draftEditBody} onChange={e => setDraftEditBody(e.target.value)} style={{ background: '#0E0E0E', borderColor: GOLD_BORDER, color: TEXT_PRIMARY }} />
                      </div>
                    </div>
                  ) : (
                    <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 20, lineHeight: 1.8, color: TEXT_SECONDARY, border: `1px solid ${BORDER}` }}>
                      {draftData ? (
                        <>
                          {draftData.title && <h4 style={{ color: TEXT_PRIMARY, marginBottom: 8 }}>{draftData.title}</h4>}
                          {draftData.lead && <p style={{ fontStyle: 'italic', marginBottom: 16 }}>{draftData.lead}</p>}
                          {draftData.body ? draftData.body.split('\n').map((p, i) => (
                            <p key={i} style={{ marginTop: i > 0 ? 16 : 0 }}>{p}</p>
                          )) : <p style={{ color: TEXT_MUTED }}>暂无正文内容</p>}
                        </>
                      ) : (
                        <p style={{ color: TEXT_MUTED }}>暂无正文内容，请点击"编辑"开始撰写</p>
                      )}
                    </div>
                  )}
                </div>
              </Spin>
            )}
          </div>
        </div>
      </div>

      {/* 上传素材 Modal */}
      <Modal
        title="上传素材"
        open={uploadModalOpen}
        onCancel={() => setUploadModalOpen(false)}
        footer={null}
      >
        <Spin spinning={uploading} tip="素材上传中…">
          <Upload.Dragger
            beforeUpload={(file) => { handleUpload(file); return false; }}
            showUploadList={false}
            disabled={uploading}
          >
            <p style={{ fontSize: 48, color: GOLD, opacity: 0.4 }}><UploadOutlined /></p>
            <p>点击或拖拽文件到此区域上传</p>
          </Upload.Dragger>
        </Spin>
      </Modal>

      {/* 素材详情 Modal */}
      <Modal
        title={sourceDetailModal?.title || '素材详情'}
        open={!!sourceDetailModal}
        onCancel={() => setSourceDetailModal(null)}
        footer={<Button onClick={() => setSourceDetailModal(null)}>关闭</Button>}
        width={640}
      >
        {sourceDetailModal && (
          <div>
            <div style={{ marginBottom: 12 }}>
              <strong>来源类型：</strong>{sourceDetailModal.source_type || '-'}
            </div>
            {(sourceDetailModal.credibilityTier || typeof sourceDetailModal.credibilityScore === 'number') && (
              <div style={{ marginBottom: 12 }}>
                <strong>可信度分级：</strong>{sourceDetailModal.credibilityTier || '-'}{typeof sourceDetailModal.credibilityScore === 'number' ? `（${Math.round(sourceDetailModal.credibilityScore * 100)}分）` : ''}
              </div>
            )}
            {sourceDetailModal.url && (
              <div style={{ marginBottom: 12 }}>
                <strong>URL：</strong><a href={sourceDetailModal.url} target="_blank" rel="noreferrer">{sourceDetailModal.url}</a>
              </div>
            )}
            {sourceDetailModal.agent_summary && (
              <div style={{ marginBottom: 12 }}>
                <strong>Agent 摘要：</strong>
                <div style={{ background: 'rgba(212,168,83,0.05)', padding: 12, borderRadius: 6, marginTop: 4, border: `1px solid ${BORDER}` }}>{sourceDetailModal.agent_summary}</div>
              </div>
            )}
            {sourceDetailModal.raw_content && (
              <div style={{ marginBottom: 12 }}>
                <strong>原始内容：</strong>
                <div style={{ background: 'rgba(245,245,245,0.03)', padding: 12, borderRadius: 6, marginTop: 4, maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap', border: `1px solid ${BORDER}` }}>{sourceDetailModal.raw_content}</div>
              </div>
            )}
            {sourceDetailModal.risk_tags && sourceDetailModal.risk_tags.length > 0 && (
              <div>
                <strong>风险标签：</strong>
                <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                  {sourceDetailModal.risk_tags.map((t: string, i: number) => <Tag key={i} style={{ background: 'rgba(234,179,8,0.15)', border: '1px solid rgba(234,179,8,0.3)', color: '#eab308', fontSize: 11 }}>{t}</Tag>)}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 添加 Claim 弹窗 */}
      <Modal
        title="添加 Claim"
        open={addClaimOpen}
        onCancel={() => { setAddClaimOpen(false); setNewClaimText('') }}
        onOk={handleAddClaim}
        confirmLoading={addClaimLoading}
        okText="添加"
        cancelText="取消"
      >
        <Input.TextArea
          rows={4}
          placeholder="请输入 Claim 内容（核心事实主张）"
          value={newClaimText}
          onChange={e => setNewClaimText(e.target.value)}
        />
      </Modal>

      <Modal
        title="人工采纳 Claim"
        open={manualAcceptOpen}
        onCancel={() => {
          setManualAcceptOpen(false)
          setManualAcceptTarget(null)
          setManualAcceptReason('')
        }}
        onOk={handleManualAcceptClaim}
        confirmLoading={manualAcceptLoading}
        okText="确认写入"
        cancelText="取消"
      >
        <div style={{ color: TEXT_SECONDARY, fontSize: 12, marginBottom: 12 }}>
          当你认为现有证据还不足以让 AI 自动支持，但编辑判断可以先保留这条 Claim 时，请写下人工依据，后续签发和复盘都能看到。
        </div>
        {manualAcceptTarget?.claim && (
          <div style={{ marginBottom: 12, padding: 12, borderRadius: 8, background: 'rgba(212,168,83,0.06)', border: `1px solid ${BORDER}`, color: TEXT_PRIMARY }}>
            {manualAcceptTarget.claim}
          </div>
        )}
        <Input.TextArea
          rows={4}
          placeholder="请输入人工采纳理由，例如：线下采访已核实、公开材料待补录、编辑判断可暂时保留但需后续复核。"
          value={manualAcceptReason}
          onChange={e => setManualAcceptReason(e.target.value)}
        />
      </Modal>

      {/* 回收站弹窗 */}
      <Modal
        title="已删除的 Claim Cards"
        open={archivedClaimsOpen}
        onCancel={() => setArchivedClaimsOpen(false)}
        footer={null}
        width={640}
      >
        <Spin spinning={archivedLoading}>
          {archivedClaims.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24, color: TEXT_MUTED }}>回收站为空</div>
          ) : (
            archivedClaims.map((c: any) => (
              <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: `1px solid ${BORDER}` }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13 }}>{c.claim_text}</div>
                  <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 2 }}>{c.risk_level} · {c.updated_at ? new Date(c.updated_at).toLocaleString('zh-CN') : ''}</div>
                </div>
                <Button
                  size="small"
                  icon={<UndoOutlined />}
                  onClick={async () => {
                    try {
                      await claimCardsApi.restore(c.id)
                      message.success('已恢复')
                      loadArchivedClaims()
                      loadClaimCards()
                    } catch { message.error('恢复失败') }
                  }}
                  style={{ color: GOLD, borderColor: GOLD_BORDER }}
                >恢复</Button>
              </div>
            ))
          )}
        </Spin>
      </Modal>
    </div>
  )
}
