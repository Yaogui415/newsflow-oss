import { useState, useEffect, useCallback } from 'react'
import { Button, Input, message, Spin, Empty, Tag, Modal } from 'antd'
import { TeamOutlined, CopyOutlined, UserDeleteOutlined, LogoutOutlined, ReloadOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons'
import { orgsApi, authApi } from '@/services/api'

const GOLD = '#D4A853'
const GOLD_BORDER = 'rgba(212,168,83,0.25)'
const BORDER = 'rgba(212,168,83,0.1)'
const TEXT_PRIMARY = '#F5F5F5'
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)'
const TEXT_MUTED = 'rgba(245,245,245,0.35)'
const TEXT_LABEL = 'rgba(245,245,245,0.55)'
const BG_CARD = '#141414'
const BG_INPUT = '#0E0E0E'

export default function TeamPage() {
  const [loading, setLoading] = useState(true)
  const [org, setOrg] = useState<any>(null)
  const [members, setMembers] = useState<any[]>([])
  const [currentUser, setCurrentUser] = useState<any>(null)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [createMode, setCreateMode] = useState(false)
  const [joinMode, setJoinMode] = useState(false)
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgDesc, setNewOrgDesc] = useState('')
  const [joinCode, setJoinCode] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [orgData, me] = await Promise.all([
        orgsApi.getMyOrg().catch(() => null),
        authApi.getMe().catch(() => null),
      ])
      setOrg(orgData)
      setCurrentUser(me)
      if (orgData) {
        const m = await orgsApi.getMembers().catch(() => [])
        setMembers(m)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleCreateOrg = async () => {
    if (!newOrgName.trim()) { message.error('请输入团队名称'); return }
    setActionLoading(true)
    try {
      await orgsApi.createOrg({ name: newOrgName.trim(), display_name: newOrgName.trim(), description: newOrgDesc.trim() || undefined })
      message.success('团队创建成功！')
      setCreateMode(false)
      setNewOrgName('')
      setNewOrgDesc('')
      loadData()
    } catch (err: any) {
      message.error(err?.response?.data?.message || '创建失败')
    } finally {
      setActionLoading(false)
    }
  }

  const handleJoinOrg = async () => {
    if (!joinCode.trim()) { message.error('请输入邀请码'); return }
    setActionLoading(true)
    try {
      const res = await orgsApi.joinOrg(joinCode.trim())
      message.success(res.message || '加入成功')
      setJoinMode(false)
      setJoinCode('')
      loadData()
    } catch (err: any) {
      message.error(err?.response?.data?.message || '加入失败')
    } finally {
      setActionLoading(false)
    }
  }

  const handleSaveEdit = async () => {
    setActionLoading(true)
    try {
      await orgsApi.updateOrg({ display_name: editName, description: editDesc })
      message.success('已更新')
      setEditing(false)
      loadData()
    } catch (err: any) {
      message.error(err?.response?.data?.message || '更新失败')
    } finally {
      setActionLoading(false)
    }
  }

  const handleRegenInvite = async () => {
    try {
      const res = await orgsApi.regenerateInvite()
      message.success(`新邀请码：${res.invite_code}`)
      loadData()
    } catch (err: any) {
      message.error(err?.response?.data?.message || '操作失败')
    }
  }

  const handleRemoveMember = async (userId: string, name: string) => {
    Modal.confirm({
      title: '确认移除',
      content: `确定要将「${name}」移出团队吗？`,
      okText: '移除',
      okType: 'danger',
      onOk: async () => {
        try {
          await orgsApi.removeMember(userId)
          message.success('已移除')
          loadData()
        } catch (err: any) {
          message.error(err?.response?.data?.message || '操作失败')
        }
      },
    })
  }

  const handleLeave = async () => {
    Modal.confirm({
      title: '确认退出',
      content: '确定要退出当前团队吗？',
      okText: '退出',
      okType: 'danger',
      onOk: async () => {
        try {
          await orgsApi.leaveOrg()
          message.success('已退出团队')
          loadData()
        } catch (err: any) {
          message.error(err?.response?.data?.message || '操作失败')
        }
      },
    })
  }

  const copyInviteCode = () => {
    if (org?.invite_code) {
      navigator.clipboard.writeText(org.invite_code)
      message.success('邀请码已复制')
    }
  }

  const isOwner = org && currentUser && org.owner_id === currentUser.id

  return (
    <div style={{ padding: 28, color: TEXT_PRIMARY, maxWidth: 700 }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, marginBottom: 6 }}>团队管理</h1>
      <div style={{ color: TEXT_MUTED, marginBottom: 28, fontSize: 12, letterSpacing: '0.5px' }}>
        管理你的新闻工作团队，邀请成员协作
      </div>

      <Spin spinning={loading}>
        {!org ? (
          <div style={{ background: BG_CARD, borderRadius: 10, padding: 28, border: `1px solid ${BORDER}` }}>
            {!createMode && !joinMode ? (
              <div style={{ textAlign: 'center' }}>
                <Empty description={<span style={{ color: TEXT_MUTED }}>你还没有加入任何团队</span>} />
                <div style={{ marginTop: 20, display: 'flex', gap: 12, justifyContent: 'center' }}>
                  <Button icon={<TeamOutlined />} onClick={() => setCreateMode(true)}
                    style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>
                    创建新团队
                  </Button>
                  <Button onClick={() => setJoinMode(true)}
                    style={{ borderColor: GOLD_BORDER, color: GOLD, background: 'transparent' }}>
                    通过邀请码加入
                  </Button>
                </div>
              </div>
            ) : createMode ? (
              <div>
                <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16 }}>创建新闻工作团队</h3>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ color: TEXT_LABEL, fontSize: 12, marginBottom: 4 }}>团队名称 *</div>
                  <Input value={newOrgName} onChange={e => setNewOrgName(e.target.value)} placeholder="如：财新新闻编辑部"
                    style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY }} />
                </div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ color: TEXT_LABEL, fontSize: 12, marginBottom: 4 }}>团队简介</div>
                  <Input.TextArea value={newOrgDesc} onChange={e => setNewOrgDesc(e.target.value)} placeholder="团队的简要描述..."
                    rows={3} style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY }} />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button onClick={() => setCreateMode(false)} style={{ borderColor: GOLD_BORDER, color: TEXT_MUTED }}>取消</Button>
                  <Button loading={actionLoading} onClick={handleCreateOrg}
                    style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>
                    创建团队
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16 }}>通过邀请码加入团队</h3>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ color: TEXT_LABEL, fontSize: 12, marginBottom: 4 }}>邀请码</div>
                  <Input value={joinCode} onChange={e => setJoinCode(e.target.value.toUpperCase())} placeholder="输入8位邀请码"
                    maxLength={8} style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY, letterSpacing: 2 }} />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button onClick={() => setJoinMode(false)} style={{ borderColor: GOLD_BORDER, color: TEXT_MUTED }}>取消</Button>
                  <Button loading={actionLoading} onClick={handleJoinOrg}
                    style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>
                    加入团队
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* 团队信息卡片 */}
            <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}`, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  {editing ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <Input value={editName} onChange={e => setEditName(e.target.value)} style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY, fontWeight: 600, fontSize: 18 }} />
                      <Input.TextArea value={editDesc} onChange={e => setEditDesc(e.target.value)} rows={2} style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY, fontSize: 13 }} />
                    </div>
                  ) : (
                    <>
                      <h2 style={{ margin: 0, fontSize: 20, color: TEXT_PRIMARY }}>{org.display_name}</h2>
                      {org.description && <div style={{ color: TEXT_MUTED, fontSize: 13, marginTop: 4 }}>{org.description}</div>}
                    </>
                  )}
                </div>
                {isOwner && (
                  editing ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Button size="small" onClick={() => setEditing(false)} style={{ borderColor: GOLD_BORDER, color: TEXT_MUTED }}>取消</Button>
                      <Button size="small" icon={<SaveOutlined />} loading={actionLoading} onClick={handleSaveEdit}
                        style={{ background: GOLD, border: 'none', color: '#0A0A0A' }}>保存</Button>
                    </div>
                  ) : (
                    <Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(true); setEditName(org.display_name); setEditDesc(org.description || '') }}
                      style={{ borderColor: GOLD_BORDER, color: GOLD, background: 'transparent' }}>编辑</Button>
                  )
                )}
              </div>

              <div style={{ display: 'flex', gap: 24, fontSize: 13 }}>
                <div><span style={{ color: TEXT_MUTED }}>成员数：</span><span style={{ color: GOLD }}>{org.member_count}</span></div>
                <div><span style={{ color: TEXT_MUTED }}>上限：</span><span style={{ color: TEXT_PRIMARY }}>{org.max_members}</span></div>
                <div>
                  <span style={{ color: TEXT_MUTED }}>邀请码：</span>
                  <Tag style={{ cursor: 'pointer', letterSpacing: 1, marginLeft: 4, background: 'rgba(212,168,83,0.12)', borderColor: GOLD_BORDER, color: GOLD }} onClick={copyInviteCode}>
                    {org.invite_code} <CopyOutlined />
                  </Tag>
                  {isOwner && <Button type="link" size="small" icon={<ReloadOutlined />} onClick={handleRegenInvite} style={{ color: TEXT_MUTED, fontSize: 11 }}>重新生成</Button>}
                </div>
              </div>
            </div>

            {/* 成员列表 */}
            <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}` }}>
              <h3 style={{ margin: 0, marginBottom: 16, fontSize: 16, color: TEXT_PRIMARY }}>
                <TeamOutlined style={{ color: GOLD, marginRight: 8 }} />团队成员 ({members.length})
              </h3>
              {members.map((m: any) => (
                <div key={m.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 12px', borderRadius: 6, marginBottom: 6,
                  background: 'rgba(212,168,83,0.03)', border: `1px solid ${BORDER}`,
                }}>
                  <div>
                    <span style={{ fontWeight: 500, color: TEXT_PRIMARY }}>{m.display_name}</span>
                    <span style={{ color: TEXT_MUTED, marginLeft: 8, fontSize: 12 }}>@{m.username}</span>
                    {m.id === org.owner_id && <Tag style={{ marginLeft: 8, fontSize: 10, background: 'rgba(212,168,83,0.12)', borderColor: GOLD_BORDER, color: GOLD }}>创建者</Tag>}
                    {m.desk && <Tag style={{ marginLeft: 4, fontSize: 10, background: 'rgba(245,245,245,0.04)', borderColor: GOLD_BORDER, color: TEXT_SECONDARY }}>{m.desk}</Tag>}
                  </div>
                  <div style={{ fontSize: 12, color: TEXT_SECONDARY }}>
                    {m.email}
                    {isOwner && m.id !== currentUser?.id && (
                      <Button type="link" danger size="small" icon={<UserDeleteOutlined />}
                        onClick={() => handleRemoveMember(m.id, m.display_name)}
                        style={{ marginLeft: 8 }}>移除</Button>
                    )}
                  </div>
                </div>
              ))}

              {!isOwner && (
                <Button danger icon={<LogoutOutlined />} onClick={handleLeave}
                  style={{ marginTop: 12, borderColor: 'rgba(239,68,68,0.3)', color: '#ef4444', background: 'transparent' }}>
                  退出团队
                </Button>
              )}
            </div>
          </>
        )}
      </Spin>
    </div>
  )
}
