import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Tag, Button, Radio, Input, Progress, message, Spin } from 'antd';
import { 
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  SafetyOutlined,
  EyeOutlined,
  SendOutlined,
  UnorderedListOutlined,
  DiffOutlined,
  AuditOutlined
} from '@ant-design/icons';
import { approvalsApi, reviewBundlesApi, storyPacketsApi, riskReportsApi, channelPackagesApi } from '@/services/api';

const { TextArea } = Input;

const GOLD = '#D4A853';
const GOLD_BORDER = 'rgba(212,168,83,0.2)';
const BG_CARD = '#141414';
const BORDER = 'rgba(212,168,83,0.1)';
const TEXT_PRIMARY = '#F5F5F5';
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)';
const TEXT_MUTED = 'rgba(245,245,245,0.35)';

const riskColors: Record<string, string> = {
  L0: '#22c55e',
  L1: '#eab308', 
  L2: '#f97316',
  L3: '#ef4444',
};

const getRiskTextColor = (riskLevel?: string) => (riskLevel === 'L1' ? '#0A0A0A' : '#fff');

const stageLabels: Record<string, string> = {
  editorial_review: '编辑审核',
  risk_review: '风险审核',
  channel_review: '渠道审核',
};

export default function DetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [decision, setDecision] = useState<string>('');
  const [reason, setReason] = useState<string>('');
  const [aiDisposition, setAiDisposition] = useState<'follow' | 'override'>('follow');
  const [overrideReason, setOverrideReason] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [submitting, setSubmitting] = useState(false);

  // API-driven state
  const [task, setTask] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [decisionLogs, setDecisionLogs] = useState<any[]>([]);
  const [bundle, setBundle] = useState<any>(null);
  const [draftData, setDraftData] = useState<any>(null);
  const [claimCards, setClaimCards] = useState<any[]>([]);
  const [riskReports, setRiskReports] = useState<any[]>([]);
  const [channelPkgs, setChannelPkgs] = useState<any[]>([]);

  const loadTask = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await approvalsApi.getTask(id);
      setTask(res);
    } catch {
      setTask(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadDecisionLogs = useCallback(async () => {
    if (!id) return;
    try {
      const res = await approvalsApi.listDecisionLogs({ approval_task_id: id });
      setDecisionLogs(Array.isArray(res) ? res : (res.items || []));
    } catch {
      setDecisionLogs([]);
    }
  }, [id]);

  // Load review bundle
  const loadBundle = useCallback(async () => {
    if (!task?.review_bundle_id) return;
    try {
      const res = await reviewBundlesApi.get(task.review_bundle_id);
      setBundle(res);
    } catch { setBundle(null); }
  }, [task?.review_bundle_id]);

  // Load draft from story packet
  const loadDraft = useCallback(async () => {
    if (!task?.story_packet_id && !bundle?.story_packet_id) return;
    const spId = task?.story_packet_id || bundle?.story_packet_id;
    try {
      const res = await storyPacketsApi.getDraft(spId);
      setDraftData(res);
    } catch { setDraftData(null); }
  }, [task?.story_packet_id, bundle?.story_packet_id]);

  // Load claim cards from story packet
  const loadClaims = useCallback(async () => {
    if (!task?.story_packet_id && !bundle?.story_packet_id) return;
    const spId = task?.story_packet_id || bundle?.story_packet_id;
    try {
      const res = await storyPacketsApi.listClaimCards(spId);
      const items = Array.isArray(res) ? res : (res.items || []);
      setClaimCards(items);
    } catch { setClaimCards([]); }
  }, [task?.story_packet_id, bundle?.story_packet_id]);

  // Load risk reports
  const loadRiskReports = useCallback(async () => {
    if (!task?.story_packet_id && !bundle?.story_packet_id) return;
    const spId = task?.story_packet_id || bundle?.story_packet_id;
    try {
      const res = await riskReportsApi.list({ story_packet_id: spId });
      setRiskReports(Array.isArray(res.items) ? res.items : []);
    } catch { setRiskReports([]); }
  }, [task?.story_packet_id, bundle?.story_packet_id]);

  // Load channel packages
  const loadChannelPkgs = useCallback(async () => {
    if (!task?.story_packet_id && !bundle?.story_packet_id) return;
    const spId = task?.story_packet_id || bundle?.story_packet_id;
    try {
      const res = await channelPackagesApi.list({ story_packet_id: spId });
      setChannelPkgs(Array.isArray(res.items) ? res.items : []);
    } catch { setChannelPkgs([]); }
  }, [task?.story_packet_id, bundle?.story_packet_id]);

  useEffect(() => { loadTask(); loadDecisionLogs(); }, [loadTask, loadDecisionLogs]);
  useEffect(() => { loadBundle(); }, [loadBundle]);
  useEffect(() => {
    if (activeTab === 'content' || activeTab === 'diff') loadDraft();
    if (activeTab === 'claims') loadClaims();
    if (activeTab === 'risk') loadRiskReports();
    if (activeTab === 'preview') loadChannelPkgs();
  }, [activeTab, loadDraft, loadClaims, loadRiskReports, loadChannelPkgs]);

  const riskLevel = task?.risk_level || task?.policy_rule?.risk_level || 'L0';
  const isHighRisk = riskLevel === 'L2' || riskLevel === 'L3';
  const signerSlots = (() => {
    try {
      const slots = task?.signer_slots;
      if (Array.isArray(slots)) return slots;
      if (typeof slots === 'string') return JSON.parse(slots);
      return [];
    } catch { return []; }
  })();
  const isOverridingAi = aiDisposition === 'override';

  const handleSubmit = async () => {
    if (isHighRisk && !reason) {
      message.error(`${riskLevel} 风险等级内容签发必须填写决策理由`);
      return;
    }
    if (!decision) {
      message.error('请选择审批决策');
      return;
    }
    if (decision === 'return' && !reason) {
      message.error('退回时必须填写理由');
      return;
    }
    if (isOverridingAi && !overrideReason.trim()) {
      message.error('不同意 AI 建议时必须填写人工判断理由');
      return;
    }
    setSubmitting(true);
    try {
      await approvalsApi.decide(id!, {
        action: decision,
        decision_reason: reason || undefined,
        override_ai_flag: isOverridingAi,
        override_reason: isOverridingAi ? overrideReason.trim() : undefined,
      });
      message.success(`决策已提交: ${decision === 'approve' ? '通过' : decision === 'return' ? '退回' : decision}`);
      setTimeout(() => navigate('/sign-off'), 1000);
    } catch (err: any) {
      message.error(err?.response?.data?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  const tabs = [
    { key: 'overview', label: '概览', icon: <UnorderedListOutlined /> },
    { key: 'content', label: '正文内容', icon: <FileTextOutlined /> },
    { key: 'diff', label: '版本Diff', icon: <DiffOutlined /> },
    { key: 'claims', label: 'Claims', icon: <AuditOutlined /> },
    { key: 'risk', label: '风险脱敏', icon: <SafetyOutlined /> },
    { key: 'preview', label: '渠道预览', icon: <EyeOutlined /> },
    { key: 'history', label: '签发历史', icon: <ClockCircleOutlined /> },
  ];

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: '#0A0A0A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!task) {
    return (
      <div style={{ minHeight: '100vh', background: '#0A0A0A', color: TEXT_PRIMARY, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <ExclamationCircleOutlined style={{ fontSize: 48, color: TEXT_MUTED, marginBottom: 16 }} />
        <div style={{ color: TEXT_MUTED }}>未找到签发任务</div>
        <Button type="link" onClick={() => navigate('/sign-off')} style={{ color: GOLD }}>返回队列</Button>
      </div>
    );
  }

  const slaDeadline = task.sla_deadline ? new Date(task.sla_deadline) : null;
  const slaRemaining = slaDeadline ? Math.max(0, Math.round((slaDeadline.getTime() - Date.now()) / 60000)) : null;
  const slaPercent = slaRemaining !== null && slaDeadline ? Math.min(100, Math.max(0, (slaRemaining / (24 * 60)) * 100)) : 0;

  return (
    <div style={{ 
      minHeight: '100vh', 
      background: '#0A0A0A',
      color: TEXT_PRIMARY
    }}>
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
            onClick={() => navigate('/sign-off')}
            style={{ color: TEXT_MUTED }}
          >
            返回队列
          </Button>
          <div style={{ width: 1, height: 24, background: BORDER }} />
          <span style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY }}>
            签发任务 {task.id?.slice(0, 8)}
          </span>
          <Tag style={{ background: riskColors[riskLevel], border: 'none', color: getRiskTextColor(riskLevel), fontSize: 11, marginLeft: 8 }}>
            {riskLevel} 风险
          </Tag>
          <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11 }}>{stageLabels[task.approval_stage] || task.approval_stage}</Tag>
          <Tag style={{ background: 'rgba(245,245,245,0.08)', border: `1px solid ${BORDER}`, color: TEXT_SECONDARY, fontSize: 11 }}>{task.status}</Tag>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {slaRemaining !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ClockCircleOutlined style={{ color: GOLD }} />
              <span style={{ color: GOLD, fontSize: 13 }}>SLA 剩余: {Math.floor(slaRemaining / 60)}h {slaRemaining % 60}m</span>
              <Progress 
                percent={slaPercent} 
                size="small" 
                style={{ width: 100, marginLeft: 8 }}
                strokeColor={slaPercent > 50 ? '#22c55e' : slaPercent > 25 ? GOLD : '#ef4444'}
                showInfo={false}
              />
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 56px)' }}>
        {/* 左侧边栏 - 任务摘要 */}
        <div style={{ 
          width: 280, 
          background: '#0A0A0A', 
          borderRight: `1px solid ${BORDER}`,
          padding: 16,
          overflow: 'auto'
        }}>
          {/* 任务元信息 */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>任务信息</div>
            <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: TEXT_MUTED, fontSize: 12 }}>Bundle</span>
                <span style={{ fontSize: 12, color: TEXT_SECONDARY }}>{task.review_bundle_id?.slice(0, 8) || '-'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: TEXT_MUTED, fontSize: 12 }}>审批阶段</span>
                <span style={{ color: GOLD, fontSize: 12 }}>{stageLabels[task.approval_stage] || task.approval_stage || '-'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: TEXT_MUTED, fontSize: 12 }}>执行模式</span>
                <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{task.execution_mode || '-'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: TEXT_MUTED, fontSize: 12 }}>创建时间</span>
                <span style={{ fontSize: 11, color: TEXT_MUTED }}>{task.created_at ? new Date(task.created_at).toLocaleString('zh-CN') : '-'}</span>
              </div>
            </div>
          </div>

          {/* 多签位状态 */}
          {signerSlots.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>签发进度</div>
              <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
                {signerSlots.map((slot: any, i: number) => (
                  <div key={i} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 12,
                    marginBottom: i < signerSlots.length - 1 ? 12 : 0
                  }}>
                    <div style={{
                      width: 24,
                      height: 24,
                      borderRadius: '50%',
                      background: slot.status === 'completed' ? '#22c55e' : 
                                 slot.status === 'pending' ? GOLD : 'rgba(245,245,245,0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      color: slot.status === 'completed' || slot.status === 'pending' ? '#0A0A0A' : TEXT_MUTED
                    }}>
                      {slot.status === 'completed' ? <CheckCircleOutlined /> : i + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color: TEXT_PRIMARY }}>{slot.role || `签位 ${i + 1}`}</div>
                      <div style={{ fontSize: 11, color: TEXT_MUTED }}>{slot.name || '-'}</div>
                    </div>
                    <Tag style={{
                      marginLeft: 'auto',
                      background: slot.status === 'completed' ? 'rgba(34,197,94,0.15)' : slot.status === 'pending' ? 'rgba(212,168,83,0.15)' : 'rgba(245,245,245,0.05)',
                      border: `1px solid ${slot.status === 'completed' ? 'rgba(34,197,94,0.3)' : slot.status === 'pending' ? GOLD_BORDER : BORDER}`,
                      color: slot.status === 'completed' ? '#22c55e' : slot.status === 'pending' ? GOLD : TEXT_MUTED,
                      fontSize: 10
                    }}>
                      {slot.status === 'completed' ? '已签' : 
                       slot.status === 'pending' ? '待签' : '等待'}
                    </Tag>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 最近 Decision Log */}
          {decisionLogs.length > 0 && (
            <div>
              <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>最近决策</div>
              <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
                {decisionLogs.slice(0, 3).map((log: any, i: number) => (
                  <div key={log.id || i} style={{ marginBottom: i < 2 ? 8 : 0, fontSize: 12 }}>
                    <Tag style={{
                      background: log.action === 'approve' ? 'rgba(34,197,94,0.15)' : log.action === 'return' ? 'rgba(234,179,8,0.15)' : 'rgba(245,245,245,0.05)',
                      border: `1px solid ${log.action === 'approve' ? 'rgba(34,197,94,0.3)' : log.action === 'return' ? 'rgba(234,179,8,0.3)' : BORDER}`,
                      color: log.action === 'approve' ? '#22c55e' : log.action === 'return' ? '#eab308' : TEXT_MUTED,
                      fontSize: 10
                    }}>
                      {log.action === 'approve' ? '通过' : log.action === 'return' ? '退回' : log.action}
                    </Tag>
                    <span style={{ color: TEXT_MUTED }}>{log.signer_role || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 中央内容区 */}
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
              </div>
            ))}
          </div>

          {/* 内容区 */}
          <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
            {activeTab === 'overview' && (
              <div>
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                  <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>任务概览</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, fontSize: 13 }}>
                    <div><span style={{ color: TEXT_MUTED }}>任务 ID：</span><span style={{ color: TEXT_SECONDARY }}>{task.id?.slice(0, 8)}</span></div>
                    <div><span style={{ color: TEXT_MUTED }}>审批阶段：</span><span style={{ color: GOLD }}>{stageLabels[task.approval_stage] || task.approval_stage}</span></div>
                    <div><span style={{ color: TEXT_MUTED }}>当前状态：</span><Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11 }}>{task.status}</Tag></div>
                    <div><span style={{ color: TEXT_MUTED }}>风险等级：</span><Tag style={{ background: riskColors[riskLevel], border: 'none', color: getRiskTextColor(riskLevel), fontSize: 11 }}>{riskLevel}</Tag></div>
                    <div><span style={{ color: TEXT_MUTED }}>Bundle ID：</span><span style={{ color: TEXT_SECONDARY }}>{task.review_bundle_id?.slice(0, 8) || '-'}</span></div>
                    <div><span style={{ color: TEXT_MUTED }}>执行模式：</span><span style={{ color: TEXT_SECONDARY }}>{task.execution_mode || '-'}</span></div>
                  </div>
                </div>
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}` }}>
                  <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>签位状态</h3>
                  {signerSlots.length > 0 ? signerSlots.map((slot: any, i: number) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, padding: 12, background: 'rgba(212,168,83,0.04)', borderRadius: 8, border: `1px solid ${BORDER}` }}>
                      <CheckCircleOutlined style={{ color: slot.status === 'completed' ? '#22c55e' : TEXT_MUTED }} />
                      <span style={{ color: TEXT_PRIMARY }}>{slot.role || `签位 ${i + 1}`}</span>
                      <span style={{ color: TEXT_MUTED }}>{slot.name || ''}</span>
                      <Tag style={{
                        marginLeft: 'auto',
                        background: slot.status === 'completed' ? 'rgba(34,197,94,0.15)' : slot.status === 'pending' ? 'rgba(212,168,83,0.15)' : 'rgba(245,245,245,0.05)',
                        border: `1px solid ${slot.status === 'completed' ? 'rgba(34,197,94,0.3)' : slot.status === 'pending' ? GOLD_BORDER : BORDER}`,
                        color: slot.status === 'completed' ? '#22c55e' : slot.status === 'pending' ? GOLD : TEXT_MUTED,
                        fontSize: 11
                      }}>
                        {slot.status === 'completed' ? '已签' : slot.status === 'pending' ? '待签' : '等待'}
                      </Tag>
                    </div>
                  )) : (
                    <div style={{ color: TEXT_MUTED }}>暂无签位信息</div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'content' && (
              <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}` }}>
                <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>正文内容 {draftData?.version ? `· v${draftData.version}` : ''}</h3>
                {draftData ? (
                  <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 20, lineHeight: 1.8, border: `1px solid ${BORDER}` }}>
                    {draftData.title && <h4 style={{ color: TEXT_PRIMARY, marginBottom: 12, fontSize: 16 }}>{draftData.title}</h4>}
                    {draftData.lead && <p style={{ color: GOLD, fontStyle: 'italic', marginBottom: 16, fontSize: 13 }}>{draftData.lead}</p>}
                    {draftData.body ? draftData.body.split('\n').map((p: string, i: number) => (
                      <p key={i} style={{ color: TEXT_SECONDARY, marginTop: i > 0 ? 12 : 0, fontSize: 14 }}>{p}</p>
                    )) : <p style={{ color: TEXT_MUTED }}>暂无正文内容</p>}
                  </div>
                ) : (
                  <div style={{ color: TEXT_MUTED, background: '#0A0A0A', borderRadius: 8, padding: 20, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <FileTextOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.3, marginBottom: 8 }} />
                    <div>暂无草稿数据</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'diff' && (
              <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, border: `1px solid ${BORDER}` }}>
                <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>版本 Diff · v{draftData?.version || '?'}</h3>
                {draftData ? (
                  <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 20, border: `1px solid ${BORDER}` }}>
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontSize: 12, color: GOLD, marginBottom: 8, fontWeight: 500 }}>当前版本 v{draftData.version}</div>
                      <div style={{ fontSize: 11, color: TEXT_MUTED, marginBottom: 4 }}>版本时间: {draftData.created_at ? new Date(draftData.created_at).toLocaleString('zh-CN') : '-'}</div>
                    </div>
                    {bundle?.claim_snapshot && (() => {
                      const snapshot = typeof bundle.claim_snapshot === 'string' ? JSON.parse(bundle.claim_snapshot) : bundle.claim_snapshot;
                      return snapshot?.frozen_at ? (
                        <div style={{ background: 'rgba(212,168,83,0.05)', borderRadius: 8, padding: 12, border: `1px solid ${GOLD_BORDER}`, marginBottom: 12 }}>
                          <div style={{ fontSize: 12, color: GOLD, fontWeight: 500 }}>Bundle 冻结快照</div>
                          <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 4 }}>冻结于: {snapshot.frozen_at}</div>
                          {snapshot.total_claims && <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginTop: 2 }}>Claims: {snapshot.total_claims} 条</div>}
                        </div>
                      ) : null;
                    })()}
                    <div style={{ color: TEXT_MUTED, fontSize: 12, padding: 12, background: 'rgba(245,245,245,0.03)', borderRadius: 6, border: `1px dashed ${BORDER}` }}>
                      <DiffOutlined style={{ marginRight: 8, color: GOLD }} />
                      当前仅有 1 个版本，待后续版本提交后可进行版本差异对比
                    </div>
                  </div>
                ) : (
                  <div style={{ color: TEXT_MUTED, background: '#0A0A0A', borderRadius: 8, padding: 20, textAlign: 'center', border: `1px dashed ${GOLD_BORDER}` }}>
                    <DiffOutlined style={{ fontSize: 48, color: GOLD, opacity: 0.3, marginBottom: 16 }} />
                    <div>暂无版本数据</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'claims' && (
              <div>
                <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>Claim Cards ({claimCards.length})</h3>
                {claimCards.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <AuditOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.3, marginBottom: 8 }} />
                    <div style={{ color: TEXT_MUTED }}>暂无 Claim Cards</div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {claimCards.map((c: any) => {
                      const statusColor = c.status === 'supported' ? '#22c55e' : c.status === 'disputed' ? '#f97316' : '#ef4444';
                      return (
                        <div key={c.id} style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${BORDER}`, borderLeft: `3px solid ${statusColor}` }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Tag style={{ background: `${statusColor}22`, border: 'none', color: statusColor, fontSize: 11 }}>{c.status}</Tag>
                              <Tag style={{ background: riskColors[c.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(c.risk_level), fontSize: 11 }}>{c.risk_level || 'L0'}</Tag>
                              {c.confidence_score != null && (
                                <Progress percent={Math.round(c.confidence_score * 100)} size="small" style={{ width: 60 }} strokeColor={c.confidence_score > 0.7 ? '#22c55e' : '#faad14'} />
                              )}
                            </div>
                          </div>
                          <div style={{ fontSize: 13, color: TEXT_PRIMARY, lineHeight: 1.7, marginBottom: 8 }}>{c.claim_text || c.claim}</div>
                          <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                            <span style={{ color: '#22c55e' }}>支持: {(c.supporting_evidence || []).length}</span>
                            <span style={{ color: c.contradicting_evidence?.length > 0 ? '#ef4444' : TEXT_MUTED }}>矛盾: {(c.contradicting_evidence || []).length}</span>
                            <span style={{ color: TEXT_MUTED }}>缺失: {(c.missing_evidence || []).length}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {activeTab === 'risk' && (
              <div>
                <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>风险脱敏报告 ({riskReports.length})</h3>
                {riskReports.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <SafetyOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.3, marginBottom: 8 }} />
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
                        </div>
                        <span style={{ fontSize: 11, color: TEXT_MUTED }}>{rr.created_at ? new Date(rr.created_at).toLocaleString('zh-CN') : ''}</span>
                      </div>
                      {Object.keys(severity).length > 0 && (
                        <div style={{ background: 'rgba(239,68,68,0.05)', borderRadius: 8, padding: 12, marginBottom: 12, border: '1px solid rgba(239,68,68,0.15)' }}>
                          <div style={{ fontSize: 12, color: '#ef4444', fontWeight: 500, marginBottom: 6 }}>严重程度摘要</div>
                          <div style={{ display: 'flex', gap: 16, fontSize: 12, flexWrap: 'wrap' }}>
                            {Object.entries(severity).map(([k, v]) => (
                              <div key={k}><span style={{ color: TEXT_MUTED }}>{k}: </span><span style={{ color: TEXT_PRIMARY, fontWeight: 500 }}>{String(v)}</span></div>
                            ))}
                          </div>
                        </div>
                      )}
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
                      {recs.length > 0 && (
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
              </div>
            )}

            {activeTab === 'preview' && (
              <div>
                <h3 style={{ marginBottom: 16, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>渠道预览 ({channelPkgs.length})</h3>
                {channelPkgs.length === 0 ? (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                    <EyeOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.3, marginBottom: 8 }} />
                    <div style={{ color: TEXT_MUTED }}>暂无渠道稿件</div>
                  </div>
                ) : channelPkgs.map((cp: any) => {
                  const content = typeof cp.content === 'string' ? JSON.parse(cp.content || '{}') : (cp.content || {});
                  const displayTitle = content.title || cp.title || '';
                  const displayLead = content.lead || content.summary || content.push_summary || '';
                  const displayBody = content.body || content.text || content.summary || content.push_summary || '';
                  const chLabels: Record<string, { label: string; color: string }> = {
                    wechat: { label: '微信公众号', color: '#22c55e' },
                    wechat_mp: { label: '微信公众号', color: '#22c55e' },
                    weibo: { label: '微博', color: '#ef4444' },
                    app_push: { label: 'APP推送', color: '#3b82f6' },
                    website: { label: '网站', color: '#8b5cf6' },
                    web: { label: '网站', color: '#8b5cf6' },
                    print: { label: '印刷版', color: '#f97316' },
                    video_script: { label: '视频脚本', color: '#ec4899' },
                    push_title: { label: '推送标题', color: '#3b82f6' },
                  };
                  const ch = chLabels[cp.channel_type] || { label: cp.channel_type, color: '#71717a' };
                  return (
                    <div key={cp.id} style={{ background: BG_CARD, borderRadius: 10, padding: 20, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Tag style={{ background: `${ch.color}22`, border: 'none', color: ch.color, fontSize: 12, fontWeight: 500 }}>{ch.label}</Tag>
                          <Tag style={{ background: 'rgba(245,245,245,0.08)', border: 'none', color: TEXT_SECONDARY, fontSize: 11 }}>{cp.status}</Tag>
                          {cp.drift_score != null && (
                            <Tag style={{ background: cp.drift_score <= (cp.drift_threshold || 0.1) ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', border: 'none', color: cp.drift_score <= (cp.drift_threshold || 0.1) ? '#22c55e' : '#ef4444', fontSize: 11 }}>
                              内容偏离度 {Math.round(cp.drift_score * 100)}%{cp.drift_score <= (cp.drift_threshold || 0.1) ? '（合格）' : '（超标）'}
                            </Tag>
                          )}
                        </div>
                        <span style={{ fontSize: 11, color: TEXT_MUTED }}>{cp.created_at ? new Date(cp.created_at).toLocaleString('zh-CN') : ''}</span>
                      </div>
                      <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 16, border: `1px solid ${BORDER}`, lineHeight: 1.8 }}>
                        {displayTitle && <h4 style={{ color: TEXT_PRIMARY, marginBottom: 8, fontSize: 14 }}>{displayTitle}</h4>}
                        {displayLead && <p style={{ color: GOLD, fontSize: 13, fontStyle: 'italic', marginBottom: 12 }}>{displayLead}</p>}
                        {displayBody ? String(displayBody).split('\n').map((p: string, i: number) => (
                          <p key={i} style={{ color: TEXT_SECONDARY, fontSize: 13, marginTop: i > 0 ? 8 : 0 }}>{p}</p>
                        )) : <div style={{ color: TEXT_MUTED, fontSize: 12 }}>（无正文内容）</div>}
                        {content.hashtags && (
                          <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {content.hashtags.map((h: string, i: number) => (
                              <Tag key={i} style={{ background: 'rgba(212,168,83,0.1)', border: 'none', color: GOLD, fontSize: 11 }}>#{h}</Tag>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {activeTab === 'history' && (
              <div>
                <div style={{ color: TEXT_MUTED, marginBottom: 16, fontSize: 13 }}>签发决策历史记录</div>
                {decisionLogs.length > 0 ? decisionLogs.map((log: any) => (
                  <div key={log.id} style={{ 
                    background: BG_CARD, 
                    borderRadius: 10, 
                    padding: 16,
                    marginBottom: 12,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 16,
                    border: `1px solid ${BORDER}`
                  }}>
                    <div style={{
                      width: 36,
                      height: 36,
                      borderRadius: '50%',
                      background: log.action === 'approve' ? 'rgba(34,197,94,0.2)' : log.action === 'return' ? 'rgba(234,179,8,0.2)' : 'rgba(239,68,68,0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: log.action === 'approve' ? '#22c55e' : log.action === 'return' ? '#eab308' : '#ef4444'
                    }}>
                      {log.action === 'approve' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontWeight: 500, color: TEXT_PRIMARY, fontSize: 13 }}>{log.signer_id?.slice(0, 8) || '-'}</span>
                        <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 10 }}>{log.signer_role || '-'}</Tag>
                        <Tag style={{
                          background: log.action === 'approve' ? 'rgba(34,197,94,0.15)' : log.action === 'return' ? 'rgba(234,179,8,0.15)' : 'rgba(239,68,68,0.15)',
                          border: 'none',
                          color: log.action === 'approve' ? '#22c55e' : log.action === 'return' ? '#eab308' : '#ef4444',
                          fontSize: 10
                        }}>
                          {log.action === 'approve' ? '通过' : log.action === 'return' ? '退回' : log.action}
                        </Tag>
                      </div>
                      {log.decision_reason && <div style={{ color: TEXT_SECONDARY, marginBottom: 4, fontSize: 13 }}>{log.decision_reason}</div>}
                      {log.override_ai_flag && (
                        <Tag style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 10, marginBottom: 4 }}>不同意 AI 建议</Tag>
                      )}
                      {log.override_ai_flag && log.override_reason && (
                        <div style={{ color: '#fca5a5', marginBottom: 4, fontSize: 12 }}>人工判断：{log.override_reason}</div>
                      )}
                      <div style={{ color: TEXT_MUTED, fontSize: 11 }}>{log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : '-'}</div>
                    </div>
                  </div>
                )) : (
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', color: TEXT_MUTED, border: `1px solid ${BORDER}` }}>
                    暂无签发记录
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 右侧决策栏 */}
        <div style={{ 
          width: 320, 
          background: '#0A0A0A', 
          borderLeft: `1px solid ${BORDER}`,
          padding: 20,
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ color: TEXT_PRIMARY, marginBottom: 8, fontSize: 15, fontWeight: 600 }}>审批决策</h3>
            <div style={{ color: TEXT_MUTED, fontSize: 12 }}>你当前拥有的权限：签发/退回/升级</div>
          </div>

          <div style={{ marginBottom: 24 }}>
            <div style={{ color: TEXT_MUTED, marginBottom: 12, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px' }}>可执行动作</div>
            <Radio.Group 
              value={decision} 
              onChange={(e) => setDecision(e.target.value)}
              style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
            >
              <Radio value="approve" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircleOutlined style={{ color: '#22c55e' }} />
                  通过并推进
                </span>
              </Radio>
              <Radio value="return" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ArrowLeftOutlined style={{ color: GOLD }} />
                  退回修改
                </span>
              </Radio>
              <Radio value="escalate" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <SendOutlined style={{ color: '#3b82f6' }} />
                  升级法务/主编
                </span>
              </Radio>
              <Radio value="hold" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ClockCircleOutlined style={{ color: TEXT_MUTED }} />
                  暂缓
                </span>
              </Radio>
              <Radio value="reject" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CloseCircleOutlined style={{ color: '#ef4444' }} />
                  终止
                </span>
              </Radio>
            </Radio.Group>
          </div>

          <div style={{ marginBottom: 24 }}>
            <div style={{ color: TEXT_MUTED, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
              决策理由
              {isHighRisk && <span style={{ color: '#ef4444' }}>（必填）</span>}
            </div>
            <TextArea 
              rows={3} 
              placeholder="请输入决策理由..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ 
                background: '#0E0E0E', 
                borderColor: GOLD_BORDER,
                color: TEXT_PRIMARY
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <div style={{ color: TEXT_MUTED, marginBottom: 8, fontSize: 12 }}>对 AI 建议的处理</div>
            <Radio.Group
              value={aiDisposition}
              onChange={(e) => setAiDisposition(e.target.value)}
              style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
            >
              <Radio value="follow" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>采纳 AI 建议继续决策</span>
                  <span style={{ color: TEXT_MUTED, fontSize: 11 }}>保留人工决策理由，但不额外标记为 AI 分歧。</span>
                </span>
              </Radio>
              <Radio value="override" style={{ color: TEXT_PRIMARY }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>不同意或修正 AI 建议</span>
                  <span style={{ color: TEXT_MUTED, fontSize: 11 }}>系统会把你的分歧判断单独写入 Decision Log。</span>
                </span>
              </Radio>
            </Radio.Group>
            {isOverridingAi && (
              <div style={{ marginTop: 12 }}>
                <TextArea
                  rows={3}
                  placeholder="请说明你不同意 AI 的哪一部分，以及你的人工判断依据..."
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  style={{
                    background: '#0E0E0E',
                    borderColor: 'rgba(239,68,68,0.3)',
                    color: TEXT_PRIMARY
                  }}
                />
              </div>
            )}
          </div>

          <div style={{ marginTop: 'auto', display: 'flex', gap: 12 }}>
            <Button 
              style={{ flex: 1, background: BG_CARD, borderColor: BORDER, color: TEXT_SECONDARY }}
              onClick={() => navigate('/sign-off')}
            >
              取消
            </Button>
            <Button 
              type="primary"
              style={{ flex: 1, background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
              disabled={!decision || (isHighRisk && !reason) || (isOverridingAi && !overrideReason.trim())}
              loading={submitting}
              onClick={handleSubmit}
            >
              确认提交
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
