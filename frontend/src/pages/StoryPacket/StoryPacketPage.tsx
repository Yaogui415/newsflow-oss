import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Tag, Button, Modal, Form, Input, Select, message, Spin, Empty } from 'antd'
import { PlusOutlined, FileTextOutlined, DeleteOutlined, UndoOutlined, EditOutlined } from '@ant-design/icons'
import { storyPacketsApi } from '@/services/api'

const GOLD = '#D4A853'
const GOLD_BORDER = 'rgba(212,168,83,0.2)'
const BG_CARD = '#1A1A1A'
const BG_CARD_HOVER = '#222222'
const BORDER = 'rgba(212,168,83,0.1)'
const TEXT_PRIMARY = '#F5F5F5'
const TEXT_MUTED = 'rgba(245,245,245,0.50)'

const riskColors: Record<string, string> = {
  L0: '#22c55e',
  L1: '#eab308',
  L2: '#f97316',
  L3: '#ef4444',
}

const getRiskTextColor = (riskLevel?: string) => (riskLevel === 'L1' ? '#0A0A0A' : '#fff')

const statusColors: Record<string, string> = {
  created: '#52525b',
  researching: '#3b82f6',
  verification_pending: '#1890ff',
  drafting: '#722ed1',
  editorial_review: '#D4A853',
  risk_review: '#f97316',
  channel_adapting: '#13c2c2',
  channel_packaging: '#13c2c2',
  channel_review: '#eb2f96',
  ready_to_publish: '#52c41a',
  publishing: '#22c55e',
  published: '#22c55e',
  monitoring: '#2f54eb',
  reopened: '#C0392B',
  killed: '#434343',
  archived: '#8c8c8c',
}

const statusLabels: Record<string, string> = {
  created: '已创建',
  researching: '调研中',
  verification_pending: '待核验',
  drafting: '起草中',
  editorial_review: '编辑审核',
  risk_review: '风险审核',
  channel_adapting: '渠道打包',
  channel_packaging: '渠道打包',
  channel_review: '渠道审核',
  ready_to_publish: '待发布',
  publishing: '发布中',
  published: '已发布',
  monitoring: '监测中',
  reopened: '已重开',
  killed: '已终止',
  archived: '已归档',
}

const getStatusTextColor = (status?: string) => (
  ['editorial_review', 'ready_to_publish', 'channel_adapting', 'channel_packaging'].includes(status || '') ? '#0A0A0A' : '#fff'
)

export default function StoryPacketPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [packets, setPackets] = useState<any[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const [showArchived, setShowArchived] = useState(false)
  const [archivedPackets, setArchivedPackets] = useState<any[]>([])
  const [archiveLoading, setArchiveLoading] = useState(false)

  const activeStatus = searchParams.get('status') || undefined
  const activeScope = searchParams.get('scope') || undefined

  const loadPackets = useCallback(async () => {
    setLoading(true)
    try {
      const res = await storyPacketsApi.list({ page: 1, page_size: 100, ...(activeStatus ? { status: activeStatus } : {}), ...(activeScope ? { scope: activeScope } : {}) })
      const items = res.items || res
      setTotalCount(typeof res.total === 'number' ? res.total : Array.isArray(items) ? items.length : 0)
      setPackets((Array.isArray(items) ? items : []).filter((p: any) => p.status !== 'archived').map((p: any) => ({
        id: p.id,
        title: p.title || '未命名任务包',
        status: p.status || 'draft',
        statusText: statusLabels[p.status] || p.status,
        risk_level: p.risk_level || 'L0',
        content_type: p.content_type || 'in_depth',
        owner: p.owner_display_name || p.owner_id?.slice(0, 8) || '-',
        event_case_id: p.event_case_title || (p.event_case_id ? p.event_case_id.slice(0, 8) : '-'),
        updated_at: p.updated_at ? new Date(p.updated_at).toLocaleString('zh-CN') : '-',
      })))
    } catch {
      setTotalCount(0)
      setPackets([])
    } finally {
      setLoading(false)
    }
  }, [activeScope, activeStatus])

  useEffect(() => {
    if (!showArchived) loadPackets()
  }, [loadPackets, showArchived])

  const loadArchived = async () => {
    setArchiveLoading(true)
    try {
      const res = await storyPacketsApi.listArchived()
      const items = Array.isArray(res) ? res : []
      setArchivedPackets(items.map((p: any) => ({
        id: p.id, title: p.title || '未命名', status: 'archived',
        statusText: '已归档', risk_level: p.risk_level || 'L0',
        updated_at: p.updated_at ? new Date(p.updated_at).toLocaleString('zh-CN') : '-',
      })))
    } catch { setArchivedPackets([]) }
    finally { setArchiveLoading(false) }
  }

  const handleDelete = (e: React.MouseEvent, packetId: string, title: string) => {
    e.stopPropagation()
    e.preventDefault()
    Modal.confirm({
      title: '确认删除',
      content: `是否确认删除报道任务包「${title}」？删除后可在回收站恢复。`,
      okText: '删除', cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        // Optimistic removal for instant UI feedback
        setPackets(prev => prev.filter(p => p.id !== packetId))
        try {
          await storyPacketsApi.delete(packetId)
          message.success('已删除')
          await loadPackets()
        } catch {
          message.error('删除失败，正在恢复...')
          await loadPackets()
        }
      },
    })
  }

  const handleRestore = async (packetId: string) => {
    try { await storyPacketsApi.restore(packetId); message.success('已恢复'); loadArchived(); loadPackets() }
    catch { message.error('恢复失败') }
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setCreating(true)
      const res = await storyPacketsApi.create(values)
      message.success('Story Packet 创建成功')
      setCreateModalOpen(false)
      form.resetFields()
      if (res?.id) {
        navigate(`/story-packets/${res.id}`)
      } else {
        loadPackets()
      }
    } catch (err: any) {
      if (err?.errorFields) return // form validation
      message.error('创建失败：' + (err?.response?.data?.message || '未知错误'))
    } finally {
      setCreating(false)
    }
  }

  const listLabel = activeScope === 'in_progress'
    ? '仅显示进行中任务包'
    : activeStatus
      ? `按状态筛选：${statusLabels[activeStatus] || activeStatus}`
      : '显示全部可见任务包'

  return (
    <div style={{ padding: 28, color: TEXT_PRIMARY }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, color: TEXT_PRIMARY }}>Story Packets</h1>
          <div style={{ color: TEXT_MUTED, marginTop: 4, fontSize: 12, letterSpacing: '0.5px' }}>
            {showArchived ? '报道任务包 · 回收站视图' : `报道任务包 · ${listLabel} · 共 ${totalCount} 个`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button onClick={() => { const next = !showArchived; setShowArchived(next); if (next) loadArchived(); else loadPackets(); }} icon={<UndoOutlined />} style={{ background: showArchived ? 'rgba(212,168,83,0.15)' : BG_CARD, borderColor: GOLD_BORDER, color: showArchived ? GOLD : TEXT_MUTED }}>
            {showArchived ? '返回列表' : '回收站'}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }} onClick={() => setCreateModalOpen(true)}>
            新建 Story Packet
          </Button>
        </div>
      </div>

      {showArchived && (
        <Spin spinning={archiveLoading}>
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ color: TEXT_PRIMARY, marginBottom: 12 }}>回收站（已删除任务包）</h3>
            {archivedPackets.length === 0 ? (
              <div style={{ color: TEXT_MUTED, padding: 20, textAlign: 'center' }}>回收站为空</div>
            ) : archivedPackets.map((sp: any) => (
              <div key={sp.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: BG_CARD, borderRadius: 8, border: `1px solid ${BORDER}`, marginBottom: 8 }}>
                <span style={{ color: TEXT_PRIMARY, fontWeight: 500 }}>{sp.title}</span>
                <Button size="small" icon={<UndoOutlined />} onClick={() => handleRestore(sp.id)} style={{ color: GOLD, borderColor: GOLD_BORDER }}>恢复</Button>
              </div>
            ))}
          </div>
        </Spin>
      )}

      {!showArchived && <Spin spinning={loading}>
        {packets.length === 0 ? (
          <Empty description={<span style={{ color: TEXT_MUTED }}>暂无任务包</span>} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {packets.map(sp => (
              <div
                key={sp.id}
                onClick={() => navigate(`/story-packets/${sp.id}`)}
                style={{
                  background: BG_CARD,
                  borderRadius: 10,
                  padding: '16px 20px',
                  cursor: 'pointer',
                  border: `1px solid ${BORDER}`,
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = GOLD_BORDER; e.currentTarget.style.background = BG_CARD_HOVER; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = BORDER; e.currentTarget.style.background = BG_CARD; }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <FileTextOutlined style={{ color: GOLD }} />
                      <span style={{ fontSize: 15, fontWeight: 500, color: TEXT_PRIMARY }}>{sp.title}</span>
                      <Tag style={{ background: riskColors[sp.risk_level], border: 'none', color: getRiskTextColor(sp.risk_level), fontSize: 11 }}>
                        {sp.risk_level}
                      </Tag>
                      <Tag style={{ background: statusColors[sp.status] || '#52525b', border: 'none', color: getStatusTextColor(sp.status), fontSize: 11 }}>
                        {sp.statusText}
                      </Tag>
                    </div>
                    <div style={{ color: TEXT_MUTED, fontSize: 12 }}>
                      事件: {sp.event_case_id} · 更新于 {sp.updated_at}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); const newName = window.prompt('重命名任务包', sp.title); if (newName && newName.trim() && newName !== sp.title) { storyPacketsApi.update(sp.id, { title: newName.trim() }).then(() => { message.success('已重命名'); loadPackets(); }).catch(() => message.error('重命名失败')); } }} style={{ color: TEXT_MUTED, fontSize: 12 }}>重命名</Button>
                    <Button size="small" style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD, fontSize: 12 }}>查看详情</Button>
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => handleDelete(e, sp.id, sp.title)} style={{ fontSize: 12 }}>删除</Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Spin>}

      {/* 新建 Story Packet Modal */}
      <Modal
        title="新建 Story Packet"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateModalOpen(false); form.resetFields() }}
        okText="创建"
        cancelText="取消"
        confirmLoading={creating}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="任务包标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="输入报道任务包标题" />
          </Form.Item>
          <Form.Item name="event_case_id" label="关联事件 ID（可选）" extra="可从事件案卷列表点击『事件ID』按钮复制，留空则创建独立任务包">
            <Input placeholder="粘贴事件 ID（非必填）" />
          </Form.Item>
          <Form.Item name="content_type" label="内容形态" rules={[{ required: true, message: '请选择内容形态' }]}>
            <Select
              placeholder="选择内容形态"
              options={[
                { value: 'breaking', label: '快讯' },
                { value: 'in_depth', label: '深度稿' },
                { value: 'explainer', label: '解释性报道' },
                { value: 'video_script', label: '视频脚本' },
                { value: 'podcast', label: '播客' },
              ]}
            />
          </Form.Item>
          <Form.Item name="angle_statement" label="报道角度（可选）">
            <Input.TextArea rows={2} placeholder="描述报道角度" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
