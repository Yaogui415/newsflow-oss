import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Tag, Button, Modal, Form, Input, Select, message, Spin, Popover, Checkbox } from 'antd'
import { PlusOutlined, FilterOutlined, DeleteOutlined, UndoOutlined, CopyOutlined, RobotOutlined } from '@ant-design/icons'
import { eventsApi } from '@/services/api'

const GOLD = '#D4A853'
const GOLD_BORDER = 'rgba(212,168,83,0.2)'
const BG_CARD = '#1A1A1A'
const BG_CARD_HOVER = '#222222'
const BORDER = 'rgba(212,168,83,0.1)'
const TEXT_PRIMARY = '#F5F5F5'
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)'
const TEXT_MUTED = 'rgba(245,245,245,0.50)'

interface EventCase {
  id: string
  title: string
  status: string
  risk_level: string
  desk: string
  tags: string[]
  packets: number
  published: number
  claims: number
  corrections: number
  lastActivity: string
}

const statusLabelsMap: Record<string, string> = {
  candidate: '候选',
  triaging: '分诊中',
  active: '进行中',
  monitoring: '监测中',
  archived: '已归档',
  merged: '已合并',
}

const riskColors: Record<string, { bg: string; text: string }> = {
  L0: { bg: '#22c55e', text: '#fff' },
  L1: { bg: '#eab308', text: '#000' },
  L2: { bg: '#f97316', text: '#fff' },
  L3: { bg: '#ef4444', text: '#fff' },
}

const statusColors: Record<string, { bg: string; text: string }> = {
  candidate: { bg: '#52525b', text: '#fff' },
  triaging: { bg: '#D4A853', text: '#0A0A0A' },
  active: { bg: '#22c55e', text: '#fff' },
  monitoring: { bg: '#3b82f6', text: '#fff' },
  archived: { bg: '#3f3f46', text: '#aaa' },
  merged: { bg: '#3f3f46', text: '#aaa' },
}

export default function EventListPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const deskFilter = searchParams.get('desk') || ''
  const [events, setEvents] = useState<EventCase[]>([])
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const [riskFilter, setRiskFilter] = useState<string[]>([])
  const [filterOpen, setFilterOpen] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [archivedEvents, setArchivedEvents] = useState<EventCase[]>([])
  const [archiveLoading, setArchiveLoading] = useState(false)

  const deskMap: Record<string, string> = {
    finance: '财经', politics: '时政', society: '社会', tech: '科技', other: '其他',
  }

  const loadEvents = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = {}
      if (deskFilter && deskMap[deskFilter]) params.desk = deskMap[deskFilter]
      const res = await eventsApi.list(params)
      const items = res.items || res
      const mapped = (Array.isArray(items) ? items : []).map((e: any) => ({
        id: e.id,
        title: e.title || '未命名事件',
        status: e.status || 'active',
        risk_level: e.risk_level || 'L0',
        desk: e.desk || '-',
        tags: Array.isArray(e.tags) ? e.tags : [],
        packets: e.story_packet_count ?? 0,
        published: e.published_count ?? 0,
        claims: e.active_claim_count ?? 0,
        corrections: e.correction_count ?? 0,
        lastActivity: e.updated_at ? new Date(e.updated_at).toLocaleString('zh-CN') : '-',
      }))
      setEvents(mapped)
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [deskFilter])

  useEffect(() => { loadEvents() }, [loadEvents])

  const loadArchived = async () => {
    setArchiveLoading(true)
    try {
      const res = await eventsApi.listArchived()
      const items = Array.isArray(res) ? res : []
      setArchivedEvents(items.map((e: any) => ({
        id: e.id, title: e.title || '未命名事件', status: e.status || 'archived',
        risk_level: e.risk_level || 'L0', desk: e.desk || '-', tags: Array.isArray(e.tags) ? e.tags : [],
        packets: 0, published: 0, claims: 0, corrections: 0,
        lastActivity: e.updated_at ? new Date(e.updated_at).toLocaleString('zh-CN') : '-',
      })))
    } catch { setArchivedEvents([]) }
    finally { setArchiveLoading(false) }
  }

  const handleDelete = async (e: React.MouseEvent, eventId: string, title: string) => {
    e.stopPropagation()
    e.preventDefault()
    Modal.confirm({
      title: '确认删除',
      content: `是否确认删除事件案卷「${title}」？删除后可在回收站恢复。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        // Optimistic removal for instant feedback
        setEvents(prev => prev.filter(ev => ev.id !== eventId))
        try {
          await eventsApi.delete(eventId)
          message.success('已删除')
          await loadEvents()
        } catch {
          message.error('删除失败，正在恢复...')
          await loadEvents()
        }
      },
    })
  }

  const handleRestore = async (eventId: string) => {
    try {
      await eventsApi.restore(eventId)
      message.success('已恢复')
      loadArchived()
      loadEvents()
    } catch { message.error('恢复失败') }
  }

  const handleCreateEvent = async () => {
    try {
      const values = await form.validateFields()
      setCreating(true)
      const res = await eventsApi.create(values)
      message.success('事件案卷创建成功')
      setCreateModalOpen(false)
      form.resetFields()
      if (res?.id) {
        navigate(`/events/${res.id}`)
      } else {
        loadEvents()
      }
    } catch (err: any) {
      if (err?.errorFields) return
      message.error('创建失败：' + (err?.response?.data?.message || '未知错误'))
    } finally {
      setCreating(false)
    }
  }

  // Apply local risk filter
  const displayedEvents = riskFilter.length > 0
    ? events.filter(e => riskFilter.includes(e.risk_level))
    : events

  return (
    <div style={{ padding: 28, color: TEXT_PRIMARY }}>
      {/* 页面标题 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, color: TEXT_PRIMARY }}>事件案卷</h1>
          <div style={{ color: TEXT_MUTED, marginTop: 4, fontSize: 12, letterSpacing: '0.5px' }}>
            Event Cases · 持续跟踪的新闻事件
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Popover
            open={filterOpen}
            onOpenChange={setFilterOpen}
            trigger="click"
            placement="bottomRight"
            content={
              <div style={{ minWidth: 160 }}>
                <div style={{ marginBottom: 8, fontWeight: 500 }}>风险等级</div>
                <Checkbox.Group
                  value={riskFilter}
                  onChange={(vals) => setRiskFilter(vals as string[])}
                  options={[
                    { value: 'L0', label: 'L0' },
                    { value: 'L1', label: 'L1' },
                    { value: 'L2', label: 'L2' },
                    { value: 'L3', label: 'L3' },
                  ]}
                  style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
                />
                {riskFilter.length > 0 && (
                  <Button size="small" type="link" onClick={() => setRiskFilter([])} style={{ padding: 0, marginTop: 8 }}>
                    清除筛选
                  </Button>
                )}
              </div>
            }
          >
            <Button 
              icon={<FilterOutlined />}
              style={{ background: riskFilter.length > 0 ? 'rgba(212,168,83,0.15)' : BG_CARD, borderColor: GOLD_BORDER, color: riskFilter.length > 0 ? GOLD : TEXT_SECONDARY }}
            >
              筛选{riskFilter.length > 0 ? ` (${riskFilter.length})` : ''}
            </Button>
          </Popover>
          <Button
            onClick={() => { const next = !showArchived; setShowArchived(next); if (next) loadArchived(); else loadEvents(); }}
            icon={<UndoOutlined />}
            style={{ background: showArchived ? 'rgba(212,168,83,0.15)' : BG_CARD, borderColor: GOLD_BORDER, color: showArchived ? GOLD : TEXT_SECONDARY }}
          >
            {showArchived ? '返回列表' : '回收站'}
          </Button>
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
            onClick={() => setCreateModalOpen(true)}
          >
            新建案卷
          </Button>
        </div>
      </div>

      {/* 回收站 */}
      {showArchived && (
        <Spin spinning={archiveLoading}>
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ color: TEXT_PRIMARY, marginBottom: 12 }}>回收站（已删除事件）</h3>
            {archivedEvents.length === 0 ? (
              <div style={{ color: TEXT_MUTED, padding: 20, textAlign: 'center' }}>回收站为空</div>
            ) : archivedEvents.map(ev => (
              <div key={ev.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: BG_CARD, borderRadius: 8, border: `1px solid ${BORDER}`, marginBottom: 8 }}>
                <div>
                  <span style={{ color: TEXT_PRIMARY, fontWeight: 500 }}>{ev.title}</span>
                  <Tag style={{ marginLeft: 8, fontSize: 10, background: 'rgba(212,168,83,0.08)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontFamily: 'monospace' }}>{ev.id.slice(0, 8)}</Tag>
                </div>
                <Button size="small" icon={<UndoOutlined />} onClick={() => handleRestore(ev.id)} style={{ color: GOLD, borderColor: GOLD_BORDER }}>恢复</Button>
              </div>
            ))}
          </div>
        </Spin>
      )}

      {/* 事件列表 */}
      {!showArchived && <Spin spinning={loading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {displayedEvents.map((event, index) => (
          <div
            key={event.id}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 20,
              padding: '18px 20px',
              background: BG_CARD,
              borderRadius: 10,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              border: `1px solid ${BORDER}`,
            }}
            onClick={() => navigate(`/events/${event.id}`)}
            onMouseEnter={(e) => { e.currentTarget.style.background = BG_CARD_HOVER; e.currentTarget.style.borderColor = GOLD_BORDER; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = BG_CARD; e.currentTarget.style.borderColor = BORDER; }}
          >
            {/* 序号 */}
            <div style={{ 
              fontSize: 28, 
              fontWeight: 700, 
              color: 'rgba(212,168,83,0.2)',
              width: 40,
              flexShrink: 0,
              fontFamily: 'Georgia, serif',
            }}>
              {String(index + 1).padStart(2, '0')}
            </div>

            {/* 内容 */}
            <div style={{ flex: 1 }}>
              {/* 标题行 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Tag
                  style={{ background: 'rgba(212,168,83,0.15)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11, fontFamily: 'monospace', margin: 0, cursor: 'pointer', padding: '2px 8px' }}
                  onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(event.id); message.success(`事件 ID 已复制: ${event.id}`); }}
                >ID：<CopyOutlined style={{ marginRight: 3 }} />{event.id.slice(0, 8)}…</Tag>
                <span style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY }}>{event.title}</span>
              </div>

              {/* 标签行 */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
                <Tag 
                  style={{ 
                    background: riskColors[event.risk_level]?.bg,
                    color: riskColors[event.risk_level]?.text,
                    border: 'none',
                    margin: 0,
                    fontSize: 11,
                  }}
                >
                  {event.risk_level}
                  {event.risk_level === 'L3' && ' 高风险'}
                </Tag>
                <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, margin: 0, fontSize: 11 }}>
                  {event.desk}
                </Tag>
                {event.tags.map(tag => (
                  <Tag key={tag} style={{ background: 'rgba(255,255,255,0.05)', border: `1px solid ${BORDER}`, color: TEXT_SECONDARY, margin: 0, fontSize: 11 }}>
                    {tag}
                  </Tag>
                ))}
                <Tag 
                  style={{ 
                    background: statusColors[event.status]?.bg || '#3f3f46',
                    color: statusColors[event.status]?.text || '#fff',
                    border: 'none',
                    margin: 0,
                    fontSize: 11,
                  }}
                >
                  {statusLabelsMap[event.status] || event.status}
                </Tag>
              </div>

              {/* 统计行 */}
              <div style={{ display: 'flex', gap: 20, color: TEXT_MUTED, fontSize: 12 }}>
                <span>任务包 <span style={{ color: TEXT_SECONDARY }}>{event.packets}</span></span>
                {event.published > 0 && (
                  <span>已发布 <span style={{ color: '#22c55e' }}>{event.published}</span></span>
                )}
                {event.claims > 0 && (
                  <span>活跃 Claim <span style={{ color: GOLD }}>{event.claims}</span></span>
                )}
                {event.corrections > 0 && (
                  <span>勘误 <span style={{ color: '#C0392B' }}>{event.corrections} 待处理</span></span>
                )}
                <span>最近活动 <span style={{ color: TEXT_SECONDARY }}>{event.lastActivity}</span></span>
              </div>
            </div>
            <div style={{ flexShrink: 0 }} onClick={e => e.stopPropagation()}>
              <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => handleDelete(e, event.id, event.title)} style={{ fontSize: 12 }}>删除</Button>
            </div>
          </div>
        ))}
      </div>
      </Spin>}

      {/* 创建事件弹窗 */}
      <Modal
        title="新建事件案卷"
        open={createModalOpen}
        onOk={handleCreateEvent}
        onCancel={() => { setCreateModalOpen(false); form.resetFields() }}
        okText="创建"
        cancelText="取消"
        confirmLoading={creating}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item 
            name="title" 
            label="事件标题" 
            rules={[{ required: true, message: '请输入事件标题' }]}
          >
            <Input placeholder="输入事件标题" />
          </Form.Item>
          <Form.Item 
            name="desk" 
            label="所属栏目" 
            rules={[{ required: true, message: '请选择栏目' }]}
          >
            <Select 
              placeholder="选择栏目"
              options={[
                { value: '财经', label: '财经' },
                { value: '时政', label: '时政' },
                { value: '社会', label: '社会' },
                { value: '科技', label: '科技' },
                { value: '其他', label: '其他' },
              ]}
            />
          </Form.Item>
          <Form.Item 
            name="risk_level" 
            label="初始风险等级"
            rules={[{ required: true, message: '请选择风险等级' }]}
          >
            <Select 
              placeholder="选择风险等级"
              options={[
                { value: 'L0', label: 'L0 - 低风险' },
                { value: 'L1', label: 'L1 - 中等风险' },
                { value: 'L2', label: 'L2 - 高风险' },
                { value: 'L3', label: 'L3 - 极高风险' },
              ]}
            />
          </Form.Item>
          <Form.Item name="description" label="事件描述">
            <Input.TextArea rows={3} placeholder="简要描述事件背景（可选）" />
          </Form.Item>
          <Form.Item 
            name="topic_keywords" 
            label={
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <RobotOutlined style={{ color: GOLD }} />
                AI 检索关键词（可选）
              </span>
            }
            extra="填写后，AI Agent 会自动检索网络相关信息并形成线索。多个关键词用逗号分隔"
          >
            <Input placeholder="如：某企业, 财务造假, 股价异常" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
