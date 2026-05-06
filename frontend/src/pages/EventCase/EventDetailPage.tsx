import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Tag, Button, Spin, Empty, message, Modal } from 'antd';
import {
  ArrowLeftOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  ClockCircleOutlined,
  UserOutlined,
  PlusOutlined,
  ExclamationCircleOutlined,
  AuditOutlined,
  BranchesOutlined,
  HistoryOutlined,
  ToolOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  SafetyCertificateOutlined,
  UploadOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  SyncOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { eventsApi, storyPacketsApi, correctionTicketsApi, approvalsApi } from '@/services/api';

const GOLD = '#D4A853';
const GOLD_BORDER = 'rgba(212,168,83,0.2)';
const BG_CARD = '#141414';
const BORDER = 'rgba(212,168,83,0.1)';
const TEXT_PRIMARY = '#F5F5F5';
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)';
const TEXT_MUTED = 'rgba(245,245,245,0.35)';

const eventStatusLabels: Record<string, string> = {
  candidate: '候选',
  triaging: '分诊中',
  active: '进行中',
  monitoring: '监测中',
  archived: '已归档',
  merged: '已合并',
};

const spStatusLabels: Record<string, string> = {
  created: '已创建',
  researching: '调研中',
  verification_pending: '核验中',
  drafting: '起草中',
  editorial_review: '编辑审',
  risk_review: '风险审',
  channel_packaging: '渠道包',
  channel_review: '渠道审',
  ready_to_publish: '待发布',
  published: '已发布',
  killed: '已杀稿',
  archived: '已归档',
  draft: '草稿',
  in_review: '审核中',
  in_progress: '进行中',
  approved: '已通过',
};

// 风险颜色
const riskColors: Record<string, string> = {
  L0: '#22c55e',
  L1: '#eab308',
  L2: '#f97316',
  L3: '#ef4444',
};

const getRiskTextColor = (riskLevel?: string) => (riskLevel === 'L1' ? '#0A0A0A' : '#fff');

const statusColors: Record<string, string> = {
  draft: '#52525b',
  in_progress: '#3b82f6',
  in_review: '#D4A853',
  approved: '#22c55e',
  published: '#22c55e',
};

export default function EventDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [activeSection, setActiveSection] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [event, setEvent] = useState<any>(null);
  const [eventPackets, setEventPackets] = useState<any[]>([]);
  const [packetsLoading, setPacketsLoading] = useState(false);
  const [sourceItems, setSourceItems] = useState<any[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [agentActivities, setAgentActivities] = useState<any[]>([]);
  const [agentLoading, setAgentLoading] = useState(false);
  const [decisionLogs, setDecisionLogs] = useState<any[]>([]);
  const [decisionsLoading, setDecisionsLoading] = useState(false);
  const [corrections, setCorrections] = useState<any[]>([]);
  const [correctionsLoading, setCorrectionsLoading] = useState(false);
  const [workflowRuns, setWorkflowRuns] = useState<any[]>([]);
  const [workflowRunsLoading, setWorkflowRunsLoading] = useState(false);
  const [mergeSplitOpen, setMergeSplitOpen] = useState(false);

  // Load event data from API
  const loadEvent = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await eventsApi.get(id);
      setEvent(res);
    } catch {
      setEvent(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  // Load story packets for this event
  const loadPackets = useCallback(async () => {
    if (!id) return;
    setPacketsLoading(true);
    try {
      const res = await storyPacketsApi.list({ event_case_id: id });
      const items = res.items || res;
      setEventPackets(Array.isArray(items) ? items : []);
    } catch {
      setEventPackets([]);
    } finally {
      setPacketsLoading(false);
    }
  }, [id]);

  const loadSources = useCallback(async () => {
    if (!id) return;
    setSourcesLoading(true);
    try {
      const res = await eventsApi.getSources(id);
      setSourceItems(Array.isArray(res) ? res : []);
    } catch {
      setSourceItems([]);
    } finally {
      setSourcesLoading(false);
    }
  }, [id]);

  const loadDecisionLogs = useCallback(async () => {
    if (!id) return;
    setDecisionsLoading(true);
    try {
      const res = await approvalsApi.listDecisionLogs({ event_case_id: id });
      const items = res.items || res;
      setDecisionLogs(Array.isArray(items) ? items : []);
    } catch {
      setDecisionLogs([]);
    } finally {
      setDecisionsLoading(false);
    }
  }, [id]);

  const loadCorrections = useCallback(async () => {
    if (!id) return;
    setCorrectionsLoading(true);
    try {
      const res = await correctionTicketsApi.list({ event_case_id: id });
      const items = res.items || res;
      setCorrections(Array.isArray(items) ? items : []);
    } catch {
      setCorrections([]);
    } finally {
      setCorrectionsLoading(false);
    }
  }, [id]);

  const loadAgentActivities = useCallback(async () => {
    if (!id) return;
    setAgentLoading(true);
    try {
      const res = await eventsApi.getAgentActivities(id);
      setAgentActivities(Array.isArray(res) ? res : []);
    } catch {
      setAgentActivities([]);
    } finally {
      setAgentLoading(false);
    }
  }, [id]);

  const loadWorkflowRuns = useCallback(async () => {
    if (!id) return;
    setWorkflowRunsLoading(true);
    try {
      const res = await eventsApi.getWorkflowRuns(id);
      setWorkflowRuns(Array.isArray(res) ? res : []);
    } catch {
      setWorkflowRuns([]);
    } finally {
      setWorkflowRunsLoading(false);
    }
  }, [id]);

  useEffect(() => { loadEvent(); loadPackets(); loadSources(); loadDecisionLogs(); loadCorrections(); loadAgentActivities(); loadWorkflowRuns(); }, [loadEvent, loadPackets, loadSources, loadDecisionLogs, loadCorrections, loadAgentActivities, loadWorkflowRuns]);

  // 解析 entity_graph_ref
  const entityGraph = (() => {
    if (!event?.entity_graph_ref) return null;
    try {
      const parsed = typeof event.entity_graph_ref === 'string' ? JSON.parse(event.entity_graph_ref) : event.entity_graph_ref;
      return parsed;
    } catch { return null; }
  })();

  const sourceTypeLabels: Record<string, { label: string; color: string }> = {
    rss: { label: 'RSS', color: '#3b82f6' },
    website: { label: '网站', color: '#8b5cf6' },
    reporter_tip: { label: '记者线报', color: '#ef4444' },
    social_media: { label: '社交媒体', color: '#f97316' },
    upload: { label: '上传文件', color: '#22c55e' },
  };

  const nodeTypeColors: Record<string, string> = {
    company: '#3b82f6', person: '#f97316', offshore: '#ef4444',
    regulator: '#22c55e', gov: '#8b5cf6', group: '#eab308',
  };

  if (loading || !event) {
    return (
      <div style={{ minHeight: '100vh', background: '#0A0A0A', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        {loading ? (
          <Spin size="large" />
        ) : (
          <div style={{ textAlign: 'center', color: '#71717a' }}>
            <Empty description="未找到该事件案卷" />
            <Button onClick={() => navigate('/events')} style={{ marginTop: 16 }}>返回列表</Button>
          </div>
        )}
      </div>
    );
  }

  // 左侧导航配置
  const leftNavItems = [
    { key: 'overview', label: '概览', icon: <EyeOutlined /> },
    { key: 'agent-flow', label: 'Agent 工作流', icon: <RobotOutlined />, count: agentActivities.length },
    { key: 'timeline', label: '时间线', icon: <ClockCircleOutlined /> },
    { key: 'relations', label: '实体与关系', icon: <BranchesOutlined /> },
    { key: 'story-packets', label: '报道任务包', icon: <FileTextOutlined />, count: eventPackets.length },
    { key: 'evidence', label: '证据素材', icon: <FolderOpenOutlined />, count: sourceItems.length },
    { key: 'decisions', label: '签发记录', icon: <AuditOutlined />, count: decisionLogs.length },
    { key: 'corrections', label: '勘误记录', icon: <ToolOutlined />, count: corrections.length },
  ];

  return (
    <Spin spinning={loading}>
    <div style={{ minHeight: '100vh', background: '#0A0A0A', color: TEXT_PRIMARY }}>
      {/* 顶部状态栏 */}
      <div style={{
        background: BG_CARD,
        borderBottom: `1px solid ${BORDER}`,
        padding: '12px 24px',
      }}>
        {/* 第一行：返回 + 标题 + 标签 + 操作 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/events')} style={{ color: TEXT_MUTED }}>返回列表</Button>
            <div style={{ width: 1, height: 24, background: BORDER }} />
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => { navigator.clipboard.writeText(event.id); message.success(`事件 ID 已复制: ${event.id}`); }}
              title={`完整事件 ID: ${event.id}`}
              style={{ background: 'rgba(212,168,83,0.15)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 12, fontFamily: 'monospace', fontWeight: 600, padding: '2px 10px' }}
            >ID：{event.id.slice(0, 8)}…</Button>
            <span style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY }}>{event.title}</span>
            <Tag style={{ background: riskColors[event.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(event.risk_level), fontSize: 11 }}>
              {event.risk_level} {event.risk_level === 'L3' ? '红线风险' : event.risk_level === 'L2' ? '高风险' : ''}
            </Tag>
            <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11 }}>
              {eventStatusLabels[event?.status] || event?.status}
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Button icon={<PlusOutlined />} onClick={() => setActiveSection('story-packets')} style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD }}>新建任务包</Button>
            <Button onClick={() => setMergeSplitOpen(true)} style={{ background: BG_CARD, borderColor: BORDER, color: TEXT_SECONDARY }}>合并/拆分</Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setActiveSection('evidence')} style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}>上传素材</Button>
          </div>
        </div>
        {/* 第二行：元信息 */}
        <div style={{ display: 'flex', gap: 20, fontSize: 12, color: TEXT_MUTED, paddingLeft: 8, flexWrap: 'wrap' }}>
          {event?.owner_id && <span><UserOutlined style={{ marginRight: 4 }} />Owner: <span style={{ color: TEXT_SECONDARY }}>{event.owner_display_name || event.owner_id?.slice(0, 8)}</span></span>}
          {event?.desk && <span>Desk: <span style={{ color: GOLD }}>{event.desk}</span></span>}
          {event?.created_at && <span>创建: {new Date(event.created_at).toLocaleDateString('zh-CN')}</span>}
          {event?.region && <span>地域: {event.region}</span>}
          {event?.updated_at && <span>最近更新: <span style={{ color: TEXT_SECONDARY }}>{new Date(event.updated_at).toLocaleString('zh-CN')}</span></span>}
          <span>任务包: <span style={{ color: TEXT_SECONDARY }}>{eventPackets.length}</span></span>
        </div>
      </div>

      <div style={{ display: 'flex', height: 'calc(100vh - 100px)' }}>
        {/* 左侧导航栏 - 按 outline 4.1 结构 */}
        <div style={{
          width: 180,
          background: '#0A0A0A',
          borderRight: `1px solid ${BORDER}`,
          padding: '12px 8px',
          overflow: 'auto'
        }}>
          {leftNavItems.map(item => {
            const isActive = activeSection === item.key;
            return (
              <div
                key={item.key}
                onClick={() => setActiveSection(item.key)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '9px 12px',
                  cursor: 'pointer',
                  borderRadius: 6,
                  marginBottom: 2,
                  backgroundColor: isActive ? 'rgba(212,168,83,0.12)' : 'transparent',
                  borderLeft: isActive ? `2px solid ${GOLD}` : '2px solid transparent',
                  color: isActive ? GOLD : TEXT_SECONDARY,
                  fontSize: 13,
                  transition: 'all 0.15s',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {item.icon}
                  {item.label}
                </span>
                {item.count !== undefined && (
                  <span style={{ fontSize: 10, color: GOLD, background: 'rgba(212,168,83,0.15)', padding: '1px 6px', borderRadius: 8 }}>
                    {item.count}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* 中央主内容区 */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>

          {/* 概览 */}
          {activeSection === 'overview' && (
            <div>
              <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16, fontSize: 15, fontWeight: 600 }}>事件摘要</h3>
              <div style={{ background: BG_CARD, borderRadius: 10, padding: 20, marginBottom: 16, lineHeight: 1.8, color: TEXT_SECONDARY, border: `1px solid ${BORDER}` }}>
                {event?.description || event?.summary || '暂无描述'}
              </div>
              {(event?.tags || []).length > 0 && (
                <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {event.tags.map((tag: string, i: number) => (
                    <Tag key={i} style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD }}>{tag}</Tag>
                  ))}
                </div>
              )}
              <h4 style={{ color: TEXT_PRIMARY, marginBottom: 12, marginTop: 20, fontSize: 14, fontWeight: 500 }}>图谱/地图预览入口</h4>
              {entityGraph ? (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 20, border: `1px dashed ${GOLD_BORDER}`, textAlign: 'center', cursor: 'pointer' }} onClick={() => setActiveSection('relations')}>
                  <BranchesOutlined style={{ fontSize: 32, color: GOLD, marginBottom: 8, opacity: 0.5 }} />
                  <div style={{ color: TEXT_MUTED }}>点击查看完整实体关系图谱</div>
                </div>
              ) : (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 20, border: `1px dashed ${BORDER}`, textAlign: 'center' }}>
                  <BranchesOutlined style={{ fontSize: 32, color: TEXT_MUTED, marginBottom: 8, opacity: 0.3 }} />
                  <div style={{ color: TEXT_MUTED }}>暂无关系图谱数据（关系调查 Agent 尚未运行）</div>
                </div>
              )}
            </div>
          )}

          {/* Agent 工作流 */}
          {activeSection === 'agent-flow' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <RobotOutlined style={{ color: GOLD }} />
                  AI Agent 信息采集流程
                </h3>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={async () => {
                      if (!id) return;
                      try {
                        await eventsApi.triggerCollect(id, event?.title);
                        message.success('AI采集已触发，请稍后刷新查看结果');
                      } catch { message.error('触发采集失败'); }
                    }}
                    style={{ background: 'rgba(212,168,83,0.15)', borderColor: GOLD_BORDER, color: GOLD, fontSize: 12 }}
                  >触发采集</Button>
                  <Button
                    size="small"
                    icon={<SyncOutlined spin={agentLoading || workflowRunsLoading} />}
                    onClick={() => { loadAgentActivities(); loadWorkflowRuns(); }}
                    style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD, fontSize: 12 }}
                  >刷新</Button>
                </div>
              </div>

              {/* AI Agent 说明卡片 (Issue 9) */}
              <div style={{ background: 'rgba(212,168,83,0.05)', borderRadius: 10, padding: 16, marginBottom: 16, border: `1px dashed ${GOLD_BORDER}` }}>
                <div style={{ fontSize: 13, color: GOLD, fontWeight: 600, marginBottom: 8 }}>🤖 AI Agent 信息采集机制</div>
                <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.8 }}>
                  <p style={{ margin: '0 0 6px' }}>1. <strong style={{ color: TEXT_PRIMARY }}>线索采集 (Source Monitor)</strong>：Agent 自动从已配置的 RSS 订阅源、网站、社交媒体 API 抓取相关信息</p>
                  <p style={{ margin: '0 0 6px' }}>2. <strong style={{ color: TEXT_PRIMARY }}>聚合去重 (Dedup & Cluster)</strong>：对多条线索进行去重并聚合为事件簇</p>
                  <p style={{ margin: '0 0 6px' }}>3. <strong style={{ color: TEXT_PRIMARY }}>智能分诊 (Triage Agent)</strong>：自动评估风险等级、分配版面、判定优先级</p>
                  <p style={{ margin: '0 0 6px' }}>4. <strong style={{ color: TEXT_PRIMARY }}>后续处理</strong>：证据结构化 → 事实核验 → 关系图谱 → 稿件生成 → 风险扫描</p>
                </div>
                <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 8, padding: '8px 12px', background: 'rgba(245,245,245,0.03)', borderRadius: 6 }}>
                  💡 确保已在「设置 → LLM 配置」中正确配置 API Key，Agent 才能正常采集和处理信息。如下方无活动记录，说明采集流程尚未启动或 API 连接异常。
                </div>
              </div>

              {/* Workflow Run 状态卡片 */}
              {workflowRuns.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  {workflowRuns.map((run: any) => {
                    const statusConfig: Record<string, { color: string; bg: string; label: string; icon: React.ReactNode }> = {
                      running: { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)', label: '运行中', icon: <LoadingOutlined spin /> },
                      completed: { color: '#22c55e', bg: 'rgba(34,197,94,0.1)', label: '已完成', icon: <CheckCircleOutlined /> },
                      failed: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', label: '失败', icon: <ExclamationCircleOutlined /> },
                      blocked: { color: '#f97316', bg: 'rgba(249,115,22,0.1)', label: '阻塞', icon: <ExclamationCircleOutlined /> },
                    };
                    const st = statusConfig[run.status] || statusConfig.running;
                    const stageLabels: Record<string, string> = {
                      source_ingestion: '线索采集', dedup_cluster: '聚合去重', triage: '智能分诊',
                      human_gate_project: '人工立项', create_story_packet: '创建任务包',
                      evidence_structuring: '证据结构化', verification: '事实核验',
                      relationship_map: '关系图谱', cognitive_parallel: '认知并行',
                      redaction_gate2: '脱敏门2', human_supplement: '人工补充',
                      drafting: '稿件生成', risk_scan: '风险扫描',
                      redaction_gate3: '脱敏门3', editorial_review: '编辑审',
                      risk_review: '风险审', channel_adaptation: '渠道适配',
                      channel_review: '渠道审', human_gate_publish: '发布闸口',
                      publish: '发布', post_publish_monitor: '发布后监测',
                      completed: '已完成', failed: '失败',
                    };
                    return (
                      <div key={run.run_id} style={{
                        background: BG_CARD, borderRadius: 10, padding: '14px 18px',
                        border: `1px solid ${st.color}33`, marginBottom: 10,
                        borderLeft: `3px solid ${st.color}`,
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <Tag style={{ background: st.bg, border: 'none', color: st.color, fontSize: 11, fontWeight: 600 }}>
                              {st.icon} <span style={{ marginLeft: 4 }}>{st.label}</span>
                            </Tag>
                            <span style={{ fontSize: 13, color: TEXT_PRIMARY, fontWeight: 500 }}>
                              <PlayCircleOutlined style={{ marginRight: 4, color: GOLD }} />
                              工作流实例
                            </span>
                            <span style={{ fontSize: 12, color: TEXT_SECONDARY }}>
                              当前阶段: <span style={{ color: GOLD }}>{stageLabels[run.current_stage] || run.current_stage}</span>
                            </span>
                          </div>
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>
                            {run.created_at ? new Date(run.created_at).toLocaleString('zh-CN') : ''}
                          </span>
                        </div>
                        {(run.status === 'running' || run.status === 'blocked') && (() => {
                          const advanceConfig: Record<string, { label: string; blockedLabel?: string; api: 'gate' | 'workflow' }> = {
                            human_gate_project: { label: '确认立项并继续', api: 'gate' },
                            human_supplement: { label: '确认补充完成，继续生成', api: 'workflow' },
                            editorial_review: { label: '编辑审核通过', blockedLabel: '⚠️ 确认风险并通过审核', api: 'workflow' },
                            risk_review: { label: '风险审核通过，进入渠道适配', blockedLabel: '⚠️ 确认风险并继续', api: 'workflow' },
                            channel_adaptation: { label: '渠道适配完成', api: 'workflow' },
                            channel_review: { label: '渠道审核通过', api: 'workflow' },
                            human_gate_publish: { label: '确认发布闸口通过', api: 'workflow' },
                            publish: { label: '确认发布完成', api: 'workflow' },
                            post_publish_monitor: { label: '监测完成，结束流程', api: 'workflow' },
                          };
                          const cfg = advanceConfig[run.current_stage];
                          if (!cfg) return null;
                          const isBlocked = run.status === 'blocked';
                          const btnLabel = isBlocked && cfg.blockedLabel ? cfg.blockedLabel : cfg.label;
                          return (
                            <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
                              <Button
                                type="primary"
                                size="small"
                                danger={isBlocked}
                                style={{ background: isBlocked ? '#ef4444' : GOLD, borderColor: isBlocked ? '#ef4444' : GOLD, color: isBlocked ? '#fff' : '#0A0A0A', fontWeight: 600 }}
                                onClick={async () => {
                                  try {
                                    if (cfg.api === 'gate') {
                                      await eventsApi.advanceGate(event!.id);
                                    } else {
                                      await eventsApi.advanceWorkflow(event!.id);
                                    }
                                    message.success(`${cfg.label} — 操作成功`);
                                    loadAgentActivities();
                                    loadWorkflowRuns();
                                  } catch {
                                    message.error('操作失败');
                                  }
                                }}
                              >
                                {btnLabel}
                              </Button>
                            </div>
                          );
                        })()}
                        {run.last_error && (
                          <div style={{ fontSize: 12, color: '#ef4444', marginTop: 8, padding: '6px 10px', background: 'rgba(239,68,68,0.08)', borderRadius: 6 }}>
                            <ExclamationCircleOutlined style={{ marginRight: 4 }} />
                            {run.last_error}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* 流程阶段概览 */}
              {(() => {
                const PIPELINE_STAGES = [
                  { key: 'source_ingestion', aliases: ['source_ingestion', 'source_ingest'], label: '线索采集', icon: '📰', agent: 'Source Monitor', desc: '从 RSS/网站/社交媒体自动采集相关线索' },
                  { key: 'dedup_cluster', aliases: ['dedup_cluster'], label: '聚合去重', icon: '🔗', agent: 'Dedup & Cluster', desc: '将多条相关线索聚合为事件簇' },
                  { key: 'triage', aliases: ['triage'], label: '智能分诊', icon: '🎯', agent: 'Triage Agent', desc: '风险评估、版面分配、优先级判定' },
                  { key: 'evidence_structuring', aliases: ['evidence_structuring', 'evidence_structure'], label: '证据结构化', icon: '📦', agent: '证据结构化', desc: '从来源中提取核心事实声明并生成证据包' },
                  { key: 'verification', aliases: ['verification'], label: '事实核验', icon: '✅', agent: '核验 Agent', desc: '对每条 Claim 进行交叉核实与可信度评估' },
                  { key: 'relationship_map', aliases: ['relationship_map'], label: '关系图谱', icon: '🕸️', agent: '关系调查', desc: '绘制实体关系图谱，发现隐藏关联' },
                  { key: 'drafting', aliases: ['drafting', 'draft_generate'], label: '稿件生成', icon: '✍️', agent: 'Drafting', desc: '基于证据包和 Claim Cards 生成基准稿' },
                  { key: 'risk_scan', aliases: ['risk_scan'], label: '风险扫描', icon: '🛡️', agent: 'Redaction & Risk', desc: '法律风险、信源保护、数据准确性检查' },
                  { key: 'channel_adapt', aliases: ['channel_adapt', 'channel_adaptation'], label: '渠道适配', icon: '📣', agent: 'Channel Adapt', desc: '为不同发布渠道生成适配版本' },
                  { key: 'post_monitor', aliases: ['post_monitor', 'post_publish_monitor'], label: '发布后监测', icon: '📈', agent: 'Post Monitor', desc: '跟踪传播效果、反馈与潜在争议' },
                ];
                const activityByAction: Record<string, any> = {};
                const completedStageKeys = new Set<string>();
                PIPELINE_STAGES.forEach((stage) => {
                  const matched = agentActivities.find((a: any) => stage.aliases.includes(a.action));
                  if (matched) {
                    activityByAction[stage.key] = matched;
                    completedStageKeys.add(stage.key);
                  }
                });

                const highestCompletedIdx = PIPELINE_STAGES.reduce((acc, stage, idx) => (
                  completedStageKeys.has(stage.key) ? idx : acc
                ), -1);
                const currentStageIdx = highestCompletedIdx >= 0 && highestCompletedIdx < PIPELINE_STAGES.length - 1
                  ? highestCompletedIdx + 1
                  : -1;
                const hasAnyActivity = agentActivities.length > 0;
                const completedCount = completedStageKeys.size;

                return (
                  <>
                    {/* 流水线进度条 */}
                    <div style={{ background: BG_CARD, borderRadius: 10, padding: '16px 20px', marginBottom: 20, border: `1px solid ${BORDER}` }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                        <span style={{ fontSize: 12, color: TEXT_MUTED }}>
                          已记录 {completedCount} / {PIPELINE_STAGES.length} 个关键步骤
                        </span>
                        {hasAnyActivity && (
                          <div style={{ width: 200, height: 4, background: '#1A1A1A', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{
                              width: `${(completedCount / PIPELINE_STAGES.length) * 100}%`,
                              height: '100%', background: `linear-gradient(90deg, ${GOLD}, #B8860B)`, borderRadius: 2, transition: 'width 0.5s ease',
                            }} />
                          </div>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 0, overflowX: 'auto', paddingBottom: 4 }}>
                        {PIPELINE_STAGES.map((stage, idx) => {
                          const done = completedStageKeys.has(stage.key);
                          const isCurrent = hasAnyActivity && idx === currentStageIdx;
                          const isLast = idx === PIPELINE_STAGES.length - 1;
                          const activity = activityByAction[stage.key];
                          return (
                            <div key={stage.key} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                              <div
                                style={{
                                  display: 'flex', flexDirection: 'column', alignItems: 'center', width: 82,
                                  cursor: activity ? 'pointer' : 'default',
                                  opacity: !done && !isCurrent ? 0.5 : 1,
                                  transition: 'opacity 0.3s',
                                }}
                                title={`${stage.agent}: ${stage.desc}${activity ? '\n' + activity.summary : ''}`}
                              >
                                <div style={{
                                  width: 38, height: 38, borderRadius: '50%',
                                  background: done
                                    ? `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`
                                    : isCurrent ? 'rgba(59,130,246,0.15)' : '#1A1A1A',
                                  border: done ? 'none' : isCurrent ? '2px solid #3b82f6' : `2px solid ${BORDER}`,
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  fontSize: 15, color: done ? '#0A0A0A' : isCurrent ? '#3b82f6' : TEXT_MUTED,
                                  transition: 'all 0.3s',
                                  boxShadow: isCurrent ? '0 0 8px rgba(59,130,246,0.3)' : done ? '0 0 6px rgba(212,168,83,0.2)' : 'none',
                                }}>
                                  {done ? <CheckCircleOutlined /> : isCurrent ? <LoadingOutlined spin /> : <span style={{ fontSize: 12 }}>{idx + 1}</span>}
                                </div>
                                <span style={{
                                  fontSize: 10, marginTop: 6, textAlign: 'center', lineHeight: 1.3, fontWeight: done ? 600 : 400,
                                  color: done ? GOLD : isCurrent ? '#3b82f6' : TEXT_MUTED,
                                }}>{stage.label}</span>
                                {activity && (
                                  <span style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 2, textAlign: 'center' }}>
                                    {new Date(activity.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                                  </span>
                                )}
                              </div>
                              {!isLast && (
                                <div style={{
                                  width: 20, height: 2, flexShrink: 0,
                                  background: done && completedStageKeys.has(PIPELINE_STAGES[idx + 1]?.key)
                                    ? GOLD
                                    : done ? `linear-gradient(90deg, ${GOLD}, ${BORDER})` : BORDER,
                                  marginBottom: activity ? 30 : 18,
                                }} />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* 详细活动日志 */}
                    <h4 style={{ color: TEXT_PRIMARY, marginBottom: 12, fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <ThunderboltOutlined style={{ color: GOLD }} />
                      Agent 活动时间线 ({agentActivities.length})
                    </h4>
                    <Spin spinning={agentLoading}>
                    {agentActivities.length === 0 ? (
                      <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                        <RobotOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                        <div style={{ color: TEXT_MUTED }}>暂无 Agent 活动记录</div>
                        <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 4 }}>Agent 采集流程尚未启动，或数据正在加载中</div>
                      </div>
                    ) : (
                      <div style={{ position: 'relative', paddingLeft: 28 }}>
                        <div style={{ position: 'absolute', left: 10, top: 0, bottom: 0, width: 2, background: `linear-gradient(180deg, ${GOLD} 0%, ${BORDER} 100%)` }} />
                        {agentActivities.map((act: any, i: number) => {
                          const stageInfo = PIPELINE_STAGES.find(s => s.key === act.action);
                          return (
                            <div key={act.id || i} style={{ position: 'relative', marginBottom: 16 }}>
                              <div style={{ position: 'absolute', left: -22, top: 6, width: 12, height: 12, borderRadius: '50%', background: GOLD, border: '2px solid #0A0A0A' }} />
                              <div style={{ background: BG_CARD, borderRadius: 8, padding: '14px 18px', border: `1px solid ${BORDER}` }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <Tag style={{ background: 'rgba(212,168,83,0.15)', border: 'none', color: GOLD, fontSize: 11, fontWeight: 600 }}>
                                      <ThunderboltOutlined style={{ marginRight: 3 }} />{act.agent_name}
                                    </Tag>
                                    {stageInfo && <span style={{ fontSize: 12, color: TEXT_SECONDARY }}>{stageInfo.label}</span>}
                                  </div>
                                  <span style={{ fontSize: 11, color: TEXT_MUTED, whiteSpace: 'nowrap' }}>
                                    {act.timestamp ? new Date(act.timestamp).toLocaleString('zh-CN') : ''}
                                  </span>
                                </div>
                                <div style={{ fontSize: 13, color: TEXT_PRIMARY, marginBottom: 6 }}>{act.summary}</div>
                                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                  {act.ai_model && <Tag style={{ fontSize: 10, background: 'rgba(59,130,246,0.1)', border: 'none', color: '#3b82f6' }}>模型: {act.ai_model}</Tag>}
                                  {act.tokens && <Tag style={{ fontSize: 10, background: 'rgba(34,197,94,0.1)', border: 'none', color: '#22c55e' }}>Token: {act.tokens.input || 0} → {act.tokens.output || 0}</Tag>}
                                  {act.details?.trigger === 'auto_on_create' && <Tag style={{ fontSize: 10, background: 'rgba(139,92,246,0.1)', border: 'none', color: '#8b5cf6' }}>自动触发</Tag>}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    </Spin>
                  </>
                );
              })()}
            </div>
          )}

          {/* 时间线 */}
          {activeSection === 'timeline' && (
            <div>
              <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16, fontSize: 15, fontWeight: 600 }}>事件时间线</h3>
              {(event?.timeline_data || []).length === 0 ? (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                  <HistoryOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                  <div style={{ color: TEXT_MUTED }}>暂无时间线数据</div>
                </div>
              ) : (
                <div style={{ position: 'relative', paddingLeft: 28 }}>
                  <div style={{ position: 'absolute', left: 10, top: 0, bottom: 0, width: 2, background: GOLD_BORDER }} />
                  {event.timeline_data.map((item: any, i: number) => {
                    const isAgent = (item.actor || '').includes('Agent');
                    return (
                      <div key={i} style={{ position: 'relative', marginBottom: 16 }}>
                        <div style={{ position: 'absolute', left: -22, top: 4, width: 12, height: 12, borderRadius: '50%', background: isAgent ? GOLD : '#3b82f6', border: '2px solid #0A0A0A' }} />
                        <div style={{ background: BG_CARD, borderRadius: 8, padding: '12px 16px', border: `1px solid ${BORDER}` }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <span style={{ fontSize: 13, fontWeight: 500, color: TEXT_PRIMARY }}>{item.event}</span>
                            <span style={{ fontSize: 11, color: TEXT_MUTED }}>{new Date(item.time).toLocaleString('zh-CN')}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Tag style={{ background: isAgent ? 'rgba(212,168,83,0.15)' : 'rgba(59,130,246,0.15)', border: 'none', color: isAgent ? GOLD : '#3b82f6', fontSize: 10 }}>
                              {isAgent ? 'AI Agent' : '人工'}
                            </Tag>
                            <span style={{ fontSize: 12, color: TEXT_SECONDARY }}>{item.actor}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 实体与关系 */}
          {activeSection === 'relations' && (
            <div>
              <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16, fontSize: 15, fontWeight: 600 }}>实体与关系图谱</h3>
              {!entityGraph ? (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                  <BranchesOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                  <div style={{ color: TEXT_MUTED }}>暂无关系图谱数据（关系调查 Agent 尚未运行）</div>
                </div>
              ) : (
                <div>
                  {/* 摘要 */}
                  <div style={{ background: BG_CARD, borderRadius: 10, padding: 16, marginBottom: 16, border: `1px solid ${BORDER}` }}>
                    <div style={{ fontSize: 13, color: GOLD, fontWeight: 500, marginBottom: 8 }}>关系调查 Agent 分析结论</div>
                    <div style={{ fontSize: 13, color: TEXT_SECONDARY, lineHeight: 1.8 }}>{entityGraph.summary}</div>
                  </div>
                  {/* SVG 力导图 */}
                  {(() => {
                    const nodes = entityGraph.nodes || [];
                    const edges = entityGraph.edges || [];
                    const W = 760, H = 480;
                    const cx = W / 2, cy = H / 2;
                    const R = Math.min(W, H) * 0.36;
                    const positions: Record<string, { x: number; y: number }> = {};
                    nodes.forEach((n: any, i: number) => {
                      const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
                      positions[n.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
                    });
                    return (
                      <div style={{ background: BG_CARD, borderRadius: 10, padding: 16, marginBottom: 16, border: `1px solid ${BORDER}`, overflow: 'hidden' }}>
                        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', background: '#0A0A0A' }}>
                          <rect x="0" y="0" width={W} height={H} rx={16} fill="#0A0A0A" />
                          <defs>
                            <marker id="arrow" viewBox="0 0 10 6" refX="28" refY="3" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
                              <path d="M0,0 L10,3 L0,6 Z" fill="rgba(212,168,83,0.5)" />
                            </marker>
                            <marker id="arrow-red" viewBox="0 0 10 6" refX="28" refY="3" markerWidth="8" markerHeight="6" orient="auto-start-reverse">
                              <path d="M0,0 L10,3 L0,6 Z" fill="rgba(239,68,68,0.6)" />
                            </marker>
                          </defs>
                          {/* Edges */}
                          {edges.map((e: any, i: number) => {
                            const s = positions[e.source], t = positions[e.target];
                            if (!s || !t) return null;
                            const isRisky = e.type === 'hidden_ownership' || e.type === 'fund_flow';
                            const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2;
                            const dx = t.x - s.x, dy = t.y - s.y;
                            const len = Math.sqrt(dx * dx + dy * dy) || 1;
                            const offsetX = -dy / len * 12, offsetY = dx / len * 12;
                            return (
                              <g key={`e-${i}`}>
                                <line x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                                  stroke={isRisky ? 'rgba(239,68,68,0.5)' : 'rgba(212,168,83,0.3)'}
                                  strokeWidth={isRisky ? 2 : 1.2}
                                  strokeDasharray={isRisky ? '6,3' : 'none'}
                                  markerEnd={isRisky ? 'url(#arrow-red)' : 'url(#arrow)'}
                                />
                                <rect x={mx + offsetX - 40} y={my + offsetY - 9} width={80} height={18} rx={4}
                                  fill={isRisky ? 'rgba(127,29,29,0.92)' : 'rgba(10,10,10,0.94)'}
                                  stroke={isRisky ? 'rgba(252,165,165,0.45)' : 'rgba(212,168,83,0.24)'}
                                  strokeWidth={0.5}
                                />
                                <text x={mx + offsetX} y={my + offsetY + 3} textAnchor="middle" fontSize={9}
                                  fill={isRisky ? '#FCA5A5' : TEXT_PRIMARY}
                                  fontWeight="600"
                                >{e.label}</text>
                              </g>
                            );
                          })}
                          {/* Nodes */}
                          {nodes.map((n: any) => {
                            const p = positions[n.id];
                            if (!p) return null;
                            const color = nodeTypeColors[n.type] || GOLD;
                            const riskColor = riskColors[n.risk] || '#52525b';
                            return (
                              <g key={n.id}>
                                <circle cx={p.x} cy={p.y} r={22} fill={`${color}22`} stroke={color} strokeWidth={2} />
                                <circle cx={p.x + 16} cy={p.y - 16} r={7} fill={riskColor} />
                                <text x={p.x + 16} y={p.y - 13} textAnchor="middle" fontSize={7} fill={getRiskTextColor(n.risk)} fontWeight="bold">{n.risk}</text>
                                <text x={p.x} y={p.y + 3} textAnchor="middle" fontSize={10} fill={TEXT_PRIMARY} fontWeight="500">
                                  {n.label.length > 6 ? n.label.slice(0, 6) + '..' : n.label}
                                </text>
                                <text x={p.x} y={p.y + 38} textAnchor="middle" fontSize={9} fill={TEXT_SECONDARY}>{n.role}</text>
                              </g>
                            );
                          })}
                        </svg>
                        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                          {Object.entries(nodeTypeColors).map(([type, color]) => (
                            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: TEXT_MUTED }}>
                              <div style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                              {type === 'company' ? '公司' : type === 'person' ? '个人' : type === 'offshore' ? '离岸' : type === 'regulator' ? '监管' : type === 'gov' ? '政府' : type === 'group' ? '群体' : type}
                            </div>
                          ))}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: TEXT_MUTED }}>
                            <div style={{ width: 16, height: 2, background: 'rgba(239,68,68,0.5)', borderTop: '1px dashed rgba(239,68,68,0.5)' }} />
                            高风险关系
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                  {/* 核心发现 */}
                  {entityGraph.key_findings && (
                    <div style={{ background: 'rgba(239,68,68,0.05)', borderRadius: 10, padding: 16, border: '1px solid rgba(239,68,68,0.2)' }}>
                      <div style={{ fontSize: 13, color: '#ef4444', fontWeight: 500, marginBottom: 8 }}><ExclamationCircleOutlined /> 核心发现</div>
                      {entityGraph.key_findings.map((f: string, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: TEXT_SECONDARY, marginBottom: 6, paddingLeft: 12, borderLeft: '2px solid rgba(239,68,68,0.3)' }}>{f}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 报道任务包 - 从API加载 */}
          {activeSection === 'story-packets' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>报道任务包 ({eventPackets.length})</h3>
                <Button type="primary" icon={<PlusOutlined />}
                  style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
                  onClick={async () => {
                    try {
                      const res = await storyPacketsApi.create({ event_case_id: id, title: `${event?.title || '新建'} - 新稿件`, content_type: 'in_depth', desk: event?.desk || '其他' });
                      if (res?.id) navigate(`/story-packets/${res.id}`);
                    } catch (err: any) {
                      const detail = err?.response?.data?.message || err?.response?.data?.detail || '请稍后重试';
                      message.error(`新建 Story Packet 失败：${detail}`);
                    }
                  }}
                >新建 Story Packet</Button>
              </div>
              <Spin spinning={packetsLoading}>
              {eventPackets.length === 0 ? (
                <Empty description={<span style={{ color: TEXT_MUTED }}>暂无关联任务包</span>} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {eventPackets.map((sp: any) => (
                    <div key={sp.id} onClick={() => navigate(`/story-packets/${sp.id}`)} style={{
                      background: BG_CARD, borderRadius: 10, padding: 16, cursor: 'pointer',
                      border: `1px solid ${BORDER}`, transition: 'border-color 0.2s',
                    }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = GOLD_BORDER}
                      onMouseLeave={e => e.currentTarget.style.borderColor = BORDER}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            <span style={{ fontSize: 14, fontWeight: 500, color: TEXT_PRIMARY }}>{sp.title}</span>
                            <Tag style={{ background: statusColors[sp.status] || '#52525b', border: 'none', color: '#fff', fontSize: 11 }}>
                              {spStatusLabels[sp.status] || sp.status}
                            </Tag>
                            <Tag style={{ background: riskColors[sp.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(sp.risk_level), fontSize: 11 }}>
                              {sp.risk_level || 'L0'}
                            </Tag>
                          </div>
                          <div style={{ color: TEXT_MUTED, fontSize: 12, marginBottom: 6 }}>
                            {sp.content_type && <span style={{ marginRight: 12 }}>类型: {sp.content_type === 'in_depth' ? '深度稿' : sp.content_type === 'breaking' ? '快讯' : sp.content_type === 'explainer' ? '解读稿' : sp.content_type === 'video_script' ? '视频脚本' : sp.content_type}</span>}
                            更新于 {sp.updated_at ? new Date(sp.updated_at).toLocaleString('zh-CN') : '-'}
                          </div>
                          {sp.blockers && sp.blockers.length > 0 && (
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                              {sp.blockers.map((b: string, bi: number) => (
                                <Tag key={bi} style={{ background: 'rgba(239,68,68,0.1)', border: 'none', color: '#ef4444', fontSize: 10 }}>{b}</Tag>
                              ))}
                            </div>
                          )}
                        </div>
                        <Button size="small" style={{ background: 'rgba(212,168,83,0.1)', borderColor: GOLD_BORDER, color: GOLD, fontSize: 12 }}>查看详情</Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              </Spin>
            </div>
          )}

          {/* 证据素材（来源线索） */}
          {activeSection === 'evidence' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0, color: TEXT_PRIMARY, fontSize: 15, fontWeight: 600 }}>来源线索 ({sourceItems.length})</h3>
                <Button type="primary" icon={<UploadOutlined />}
                  loading={uploadProgress > 0 && uploadProgress < 100}
                  style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
                  onClick={() => {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.accept = '.pdf,.doc,.docx,.txt,.csv,.json,.png,.jpg,.jpeg,.gif,.bmp,.webp';
                    input.onchange = async (e: any) => {
                      const file = e.target?.files?.[0];
                      if (!file) return;
                      setUploadProgress(10);
                      const formData = new FormData();
                      formData.append('file', file);
                      if (id) formData.append('event_case_id', id);
                      try {
                        setUploadProgress(30);
                        const { sourcesApi } = await import('@/services/api');
                        setUploadProgress(50);
                        await sourcesApi.upload(formData);
                        setUploadProgress(100);
                        message.success(`「${file.name}」上传成功`);
                        loadSources();
                      } catch (err: any) {
                        message.error(`上传失败：${err?.response?.data?.detail || err?.message || '请重试'}`);
                      } finally {
                        setTimeout(() => setUploadProgress(0), 1000);
                      }
                    };
                    input.click();
                  }}
                >{uploadProgress > 0 && uploadProgress < 100 ? `上传中 ${uploadProgress}%` : '上传素材'}</Button>
              </div>
              <Spin spinning={sourcesLoading}>
              {sourceItems.length === 0 ? (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                  <FolderOpenOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                  <div style={{ color: TEXT_MUTED }}>暂无来源线索</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {sourceItems.map((src: any) => {
                    const st = sourceTypeLabels[src.source_type] || { label: src.source_type, color: '#71717a' };
                    const w5h1 = src.extracted_5w1h || {};
                    const hasHighRisk = (src.risk_tags || []).some((t: string) => t.includes('L3') || t.includes('匿名') || t.includes('内幕'));
                    const isVerified = src.agent_summary || (src.extracted_5w1h && Object.keys(src.extracted_5w1h).length > 0);
                    return (
                      <div key={src.id} style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${hasHighRisk ? 'rgba(239,68,68,0.2)' : BORDER}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Tag style={{ background: `${st.color}22`, border: 'none', color: st.color, fontSize: 11 }}>{st.label}</Tag>
                            {isVerified ? (
                              <Tag style={{ background: 'rgba(34,197,94,0.12)', border: 'none', color: '#22c55e', fontSize: 10 }}>
                                <CheckCircleOutlined style={{ marginRight: 3 }} />已处理
                              </Tag>
                            ) : (
                              <Tag style={{ background: 'rgba(234,179,8,0.12)', border: 'none', color: '#eab308', fontSize: 10 }}>
                                <ExclamationCircleOutlined style={{ marginRight: 3 }} />待核验
                              </Tag>
                            )}
                            {hasHighRisk && (
                              <Tag style={{ background: 'rgba(239,68,68,0.15)', border: 'none', color: '#ef4444', fontSize: 10 }}>
                                <SafetyCertificateOutlined style={{ marginRight: 3 }} />高风险
                              </Tag>
                            )}
                            {(src.risk_tags || []).map((rt: string, ri: number) => (
                              <Tag key={ri} style={{ background: 'rgba(239,68,68,0.1)', border: 'none', color: '#ef4444', fontSize: 10 }}>{rt}</Tag>
                            ))}
                          </div>
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>{new Date(src.ingested_at).toLocaleString('zh-CN')}</span>
                        </div>
                        {/* Credibility level (Issue 8) */}
                        {(() => {
                          const credMap: Record<string, { label: string; bg: string; color: string }> = {
                            government: { label: '权威官方', bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
                            official: { label: '权威官方', bg: 'rgba(34,197,94,0.15)', color: '#22c55e' },
                            rss: { label: '权威媒体', bg: 'rgba(59,130,246,0.15)', color: '#3b82f6' },
                            mainstream_media: { label: '权威媒体', bg: 'rgba(59,130,246,0.15)', color: '#3b82f6' },
                            website: { label: '网络来源', bg: 'rgba(234,179,8,0.15)', color: '#eab308' },
                            social_media: { label: '社交媒体/网友', bg: 'rgba(249,115,22,0.15)', color: '#f97316' },
                            reporter_tip: { label: '记者线报', bg: 'rgba(239,68,68,0.15)', color: '#ef4444' },
                            upload: { label: '人工上传', bg: 'rgba(139,92,246,0.15)', color: '#8b5cf6' },
                          };
                          const cred = credMap[src.source_type];
                          return cred ? (
                            <Tag style={{ fontSize: 10, background: cred.bg, border: 'none', color: cred.color, marginBottom: 6 }}>可信度: {cred.label}</Tag>
                          ) : null;
                        })()}
                        <div style={{ fontSize: 13, color: TEXT_SECONDARY, lineHeight: 1.7, marginBottom: 10 }}>{src.raw_content}</div>
                        {/* Source URL with link (Issue 10) */}
                        {src.url && <div style={{ fontSize: 11, marginBottom: 8, wordBreak: 'break-all' }}><a href={src.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3b82f6' }}>🔗 {src.url}</a></div>}
                        {/* Uploader info (Issue 10) */}
                        {src.uploaded_by && <div style={{ fontSize: 11, color: TEXT_MUTED, marginBottom: 4 }}>上传者: <span style={{ color: TEXT_SECONDARY }}>{src.uploaded_by}</span></div>}
                        {src.original_filename && <div style={{ fontSize: 11, color: TEXT_MUTED, marginBottom: 4 }}>📄 源文件: <span style={{ color: '#3b82f6' }}>{src.original_filename}</span></div>}
                        {Object.keys(w5h1).length > 0 && (
                          <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
                            <div style={{ fontSize: 11, color: GOLD, marginBottom: 6, fontWeight: 500 }}>5W1H 抽取结果（Source Monitor Agent）</div>
                            {w5h1.error ? (
                              <div style={{ fontSize: 12, color: '#f97316' }}>⚠️ 抽取失败，请重试或手动填写</div>
                            ) : w5h1._extraction_pending ? (
                              <div style={{ fontSize: 12, color: TEXT_MUTED }}>⏳ 正在抽取中...</div>
                            ) : (
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px 16px', fontSize: 12 }}>
                                {Object.entries(w5h1).filter(([k]) => !k.startsWith('_')).map(([k, v]) => (
                                  <div key={k}><span style={{ color: TEXT_MUTED }}>{k.toUpperCase()}: </span><span style={{ color: TEXT_SECONDARY }}>{v as string}</span></div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              </Spin>
            </div>
          )}

          {/* 签发记录 */}
          {activeSection === 'decisions' && (
            <div>
              <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16, fontSize: 15, fontWeight: 600 }}>签发记录 (Decision Log)</h3>
              <Spin spinning={decisionsLoading}>
              {decisionLogs.length === 0 ? (
                <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
                  <AuditOutlined style={{ fontSize: 32, color: GOLD, opacity: 0.4, marginBottom: 8 }} />
                  <div style={{ color: TEXT_MUTED }}>暂无签发记录</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {decisionLogs.map((dl: any) => {
                    const actionColor = dl.action === 'approve' ? '#22c55e' : dl.action === 'reject' ? '#ef4444' : '#eab308';
                    const actionLabel = dl.action === 'approve' ? '通过' : dl.action === 'reject' ? '驳回' : dl.action === 'request_changes' ? '要求修改' : dl.action;
                    return (
                      <div key={dl.id} style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${BORDER}`, borderLeft: `3px solid ${actionColor}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Tag style={{ background: `${actionColor}22`, border: 'none', color: actionColor, fontSize: 11 }}>{actionLabel}</Tag>
                            <span style={{ fontSize: 13, fontWeight: 500, color: TEXT_PRIMARY }}>{dl.signer_role === 'chief_editor' ? '主编' : dl.signer_role === 'desk_editor' ? '版面编辑' : dl.signer_role === 'compliance_editor' ? '合规编辑' : dl.signer_role}</span>
                            {dl.story_packet_title && <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, fontSize: 11 }}>{dl.story_packet_title}</Tag>}
                          </div>
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>{dl.created_at ? new Date(dl.created_at).toLocaleString('zh-CN') : '-'}</span>
                        </div>
                        <div style={{ fontSize: 13, color: TEXT_SECONDARY, lineHeight: 1.7 }}>{dl.decision_reason}</div>
                        {dl.conditions && <div style={{ fontSize: 12, color: '#eab308', marginTop: 8 }}>附加条件：{dl.conditions}</div>}
                      </div>
                    );
                  })}
                </div>
              )}
              </Spin>
            </div>
          )}

          {/* 勘误记录 */}
          {activeSection === 'corrections' && (
            <div>
              <h3 style={{ color: TEXT_PRIMARY, marginBottom: 16, fontSize: 15, fontWeight: 600 }}>勘误记录 (Correction Ticket)</h3>
              <Spin spinning={correctionsLoading}>
              {corrections.length === 0 ? (
                <Empty description={<span style={{ color: TEXT_MUTED }}>暂无勘误记录</span>} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {corrections.map((ct: any) => {
                    const isOpen = ct.status === 'open';
                    const closedStatusMap: Record<string, { label: string; color: string; bg: string }> = {
                      corrected: { label: '已修改', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
                      not_corrected: { label: '未修改', color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
                      rejected: { label: '已拒绝', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
                      closed: { label: '已修改', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
                    };
                    const closedInfo = !isOpen ? (closedStatusMap[ct.status] || closedStatusMap['closed']) : null;
                    const borderLeftColor = isOpen ? '#ef4444' : (closedInfo?.color || '#22c55e');
                    return (
                      <div key={ct.id} style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${isOpen ? 'rgba(239,68,68,0.3)' : BORDER}`, borderLeft: `3px solid ${borderLeftColor}` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                          <Tag style={{ background: isOpen ? 'rgba(239,68,68,0.15)' : closedInfo!.bg, border: 'none', color: isOpen ? '#ef4444' : closedInfo!.color, fontSize: 11 }}>
                            {isOpen ? '待处理' : closedInfo!.label}
                          </Tag>
                          <span style={{ fontSize: 11, color: TEXT_MUTED }}>{ct.created_at ? new Date(ct.created_at).toLocaleString('zh-CN') : '-'}</span>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: TEXT_PRIMARY, marginBottom: 8 }}>触发原因</div>
                        <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.7, marginBottom: 10 }}>{ct.trigger_reason}</div>
                        {ct.impact_scope && (
                          <div style={{ fontSize: 12, color: TEXT_MUTED, marginBottom: 6 }}>影响范围：<span style={{ color: TEXT_SECONDARY }}>{ct.impact_scope}</span></div>
                        )}
                        {ct.proposed_fix && (
                          <div style={{ background: '#0A0A0A', borderRadius: 8, padding: 12, marginTop: 8, border: `1px solid ${BORDER}` }}>
                            <div style={{ fontSize: 11, color: GOLD, fontWeight: 500, marginBottom: 4 }}>修正方案</div>
                            <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.7 }}>{ct.proposed_fix}</div>
                          </div>
                        )}
                        {ct.closed_at && (
                          <div style={{ fontSize: 11, color: '#22c55e', marginTop: 8 }}>关闭时间：{new Date(ct.closed_at).toLocaleString('zh-CN')}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              </Spin>
            </div>
          )}
        </div>

        {/* 右侧边栏 */}
        <div style={{
          width: 260,
          background: '#0A0A0A',
          borderLeft: `1px solid ${BORDER}`,
          padding: 16,
          overflow: 'auto'
        }}>
          {/* 风险摘要 */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>风险摘要</div>
            <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, border: `1px solid ${BORDER}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Tag style={{ background: riskColors[event?.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(event?.risk_level), fontSize: 11 }}>
                  {event?.risk_level || 'L0'}
                </Tag>
                <span style={{ fontSize: 13, color: TEXT_SECONDARY }}>
                  {event?.risk_level === 'L3' ? '红线风险' : event?.risk_level === 'L2' ? '高风险' : '一般'}
                </span>
              </div>
              {(event?.tags || []).map((tag: string, i: number) => (
                <div key={i} style={{ color: GOLD, fontSize: 12, marginBottom: 4 }}>
                  <ExclamationCircleOutlined style={{ marginRight: 4 }} />{tag}
                </div>
              ))}
            </div>
          </div>

          {/* 活跃任务包 */}
          <div>
            <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>活跃任务包 ({eventPackets.length})</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {eventPackets.length === 0 ? (
                <div style={{ background: BG_CARD, borderRadius: 8, padding: 12, textAlign: 'center', color: TEXT_MUTED, fontSize: 12, border: `1px solid ${BORDER}` }}>
                  暂无任务包
                </div>
              ) : eventPackets.map((sp: any) => (
                <div key={sp.id}
                  onClick={() => navigate(`/story-packets/${sp.id}`)}
                  style={{
                    background: BG_CARD, borderRadius: 8, padding: 10, cursor: 'pointer',
                    border: `1px solid ${BORDER}`, fontSize: 12, transition: 'border-color 0.15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = GOLD_BORDER}
                  onMouseLeave={e => e.currentTarget.style.borderColor = BORDER}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Tag style={{ background: riskColors[sp.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(sp.risk_level), fontSize: 10 }}>
                      {sp.risk_level || 'L0'}
                    </Tag>
                    <span style={{ fontWeight: 500, color: TEXT_PRIMARY, fontSize: 13 }}>{sp.title}</span>
                  </div>
                  <div style={{ color: TEXT_MUTED, marginTop: 4 }}>
                    {spStatusLabels[sp.status] || sp.status}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>

      {/* 合并/拆分 Modal (Issue 9) */}
      <Modal
        title="合并 / 拆分事件案卷"
        open={mergeSplitOpen}
        onCancel={() => setMergeSplitOpen(false)}
        footer={null}
        width={560}
      >
        <div style={{ marginBottom: 16, color: TEXT_MUTED, fontSize: 13, lineHeight: 1.7 }}>
          <p><strong style={{ color: TEXT_PRIMARY }}>合并</strong>：将多个相似事件案卷合并为一个，共享来源线索和任务包。适用于同一事件的重复报道。</p>
          <p><strong style={{ color: TEXT_PRIMARY }}>拆分</strong>：将当前事件中的部分任务包拆分为独立事件案卷。适用于同一事件中出现不同角度的重大分支。</p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <Button
            style={{ flex: 1, height: 64, background: 'rgba(34,197,94,0.08)', borderColor: 'rgba(34,197,94,0.3)', color: '#22c55e' }}
            onClick={() => {
              if (eventPackets.length < 2) {
                message.info('当前事件仅有 ' + eventPackets.length + ' 个任务包，无法演示合并（需 ≥ 2 个任务包）');
              } else {
                message.success('已模拟合并操作：' + eventPackets.length + ' 个任务包合并为 1 个综合任务包');
              }
              setMergeSplitOpen(false);
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 14 }}>合并任务包</div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>将选中任务包的素材和 Claim 合并</div>
          </Button>
          <Button
            style={{ flex: 1, height: 64, background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.3)', color: '#ef4444' }}
            onClick={() => {
              if (eventPackets.length < 2) {
                message.info('当前事件仅有 ' + eventPackets.length + ' 个任务包，无需拆分');
              } else {
                message.success('已模拟拆分操作：将第一个任务包拆分为独立事件案卷');
              }
              setMergeSplitOpen(false);
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 14 }}>拆分为新事件</div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>选中任务包独立为新案卷</div>
          </Button>
        </div>
        {eventPackets.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: TEXT_MUTED, marginBottom: 8 }}>当前任务包（{eventPackets.length}）：</div>
            {eventPackets.map((sp: any) => (
              <div key={sp.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: BG_CARD, borderRadius: 6, marginBottom: 4, border: `1px solid ${BORDER}` }}>
                <Tag style={{ background: riskColors[sp.risk_level] || '#52525b', border: 'none', color: getRiskTextColor(sp.risk_level), fontSize: 10 }}>{sp.risk_level || 'L0'}</Tag>
                <span style={{ fontSize: 12, color: TEXT_PRIMARY }}>{sp.title}</span>
                <span style={{ fontSize: 11, color: TEXT_MUTED, marginLeft: 'auto' }}>{spStatusLabels[sp.status] || sp.status}</span>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </Spin>
  );
}
