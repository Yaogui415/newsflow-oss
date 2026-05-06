import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tag, Row, Col, Spin, Empty } from 'antd';
import { dashboardApi } from '@/services/api';

// Black-Gold Design Tokens
const GOLD = '#D4A853';
// dim variant used by child components
const GOLD_BORDER = 'rgba(212,168,83,0.2)';
const BG_CARD = '#1A1A1A';
const BG_CARD_HOVER = '#1A1A1A';
const BORDER = 'rgba(212,168,83,0.1)';
const TEXT_PRIMARY = '#F5F5F5';
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)';
const TEXT_MUTED = 'rgba(245,245,245,0.50)';

// Agent状态列表（系统内建 Agent，状态实时展示）
const agentStatusList = [
  { name: 'Source Monitor', status: 'active' },
  { name: 'Dedup & Cluster', status: 'active' },
  { name: 'Triage Agent', status: 'active' },
  { name: '证据结构化', status: 'active' },
  { name: '核验 Agent', status: 'active' },
  { name: '关系调查', status: 'active' },
  { name: 'Drafting', status: 'active' },
  { name: 'Redaction & Risk', status: 'active' },
];

interface DashboardStats {
  active_events: number;
  in_progress_packets: number;
  pending_approval: number;
  published_today: number;
  high_risk_count: number;
}

interface HighPriorityEvent {
  id: string;
  title: string;
  risk_level: string;
  status: string;
  desk: string | null;
  updated_at: string;
}

interface SLAAlert {
  task_id: string;
  story_packet_title: string;
  approval_stage: string;
  sla_status: string;
  minutes_remaining: number | null;
  minutes_overdue: number | null;
}

interface AgentActivity {
  timestamp: string;
  agent_name: string;
  action: string;
  object_type: string;
  object_id: string;
  summary: string;
}

const riskColors: Record<string, string> = {
  L0: '#22c55e',
  L1: '#eab308',
  L2: '#f97316',
  L3: '#ef4444',
};

const statusLabels: Record<string, string> = {
  active: '进行中',
  triaging: '分诊中',
  monitoring: '监测中',
  candidate: '候选',
  archived: '已归档',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [highPriorityEvents, setHighPriorityEvents] = useState<HighPriorityEvent[]>([]);
  const [slaAlerts, setSlaAlerts] = useState<SLAAlert[]>([]);
  const [agentActivities, setAgentActivities] = useState<AgentActivity[]>([]);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, eventsRes, slaRes, activityRes] = await Promise.allSettled([
        dashboardApi.getStats(),
        dashboardApi.getHighPriorityEvents(5),
        dashboardApi.getSlaAlerts(),
        dashboardApi.getAgentActivities(10),
      ]);

      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
      if (eventsRes.status === 'fulfilled') setHighPriorityEvents(eventsRes.value || []);
      if (slaRes.status === 'fulfilled') setSlaAlerts(slaRes.value || []);
      if (activityRes.status === 'fulfilled') setAgentActivities(activityRes.value || []);
    } catch {
      // 保持空状态
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  const isEmpty = !stats || (stats.active_events === 0 && stats.in_progress_packets === 0 && stats.pending_approval === 0);

  return (
    <Spin spinning={loading}>
    <div style={{ padding: 28, color: TEXT_PRIMARY }}>
      {/* 空数据提示 */}
      {!loading && isEmpty && (
        <div style={{
          background: BG_CARD,
          borderRadius: 10,
          padding: 32,
          marginBottom: 28,
          textAlign: 'center',
          border: `1px dashed ${GOLD_BORDER}`,
        }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: TEXT_SECONDARY }}>暂无数据，请通过线索采集或创建事件案卷开始工作</span>}
          />
        </div>
      )}

      {/* Agent 状态区 */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ color: TEXT_MUTED, fontSize: 10, marginBottom: 10, fontWeight: 600, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
          AGENT STATUS
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {agentStatusList.map(agent => (
            <div
              key={agent.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 12px',
                background: BG_CARD,
                borderRadius: 16,
                fontSize: 12,
                color: TEXT_SECONDARY,
                border: `1px solid ${BORDER}`,
              }}
            >
              <div style={{ 
                width: 5, 
                height: 5, 
                borderRadius: '50%', 
                backgroundColor: '#22c55e',
                boxShadow: '0 0 4px rgba(34,197,94,0.5)',
              }} />
              {agent.name}
            </div>
          ))}
        </div>
      </div>

      {/* 统计数字区 */}
      <Row gutter={20} style={{ marginBottom: 32 }}>
        {[
          { label: '活跃事件', value: stats?.active_events ?? 0, path: '/events', color: GOLD, sub: (stats?.high_risk_count ?? 0) > 0 ? `${stats?.high_risk_count} 个高风险` : null, subColor: '#C0392B', tooltip: '包括 candidate/triaging/active/monitoring 状态的事件' },
          { label: '进行中任务包', value: stats?.in_progress_packets ?? 0, path: '/story-packets?scope=in_progress', color: TEXT_PRIMARY, tooltip: '状态非 published/archived 的任务包' },
          { label: '待签发', value: stats?.pending_approval ?? 0, path: '/sign-off?view=pending', color: (stats?.pending_approval ?? 0) > 0 ? '#C0392B' : TEXT_PRIMARY, sub: slaAlerts.length > 0 ? `${slaAlerts.filter(a => a.sla_status === 'overdue').length} 超时 · ${slaAlerts.filter(a => a.sla_status === 'near').length} 临期` : null, subColor: '#C0392B', tooltip: '等待当前用户签发的审批任务数' },
          { label: '今日发布', value: stats?.published_today ?? 0, path: '/story-packets?status=published', color: '#22c55e', tooltip: '今日已发布的稿件数量' },
        ].map((card, i) => (
          <Col span={6} key={i}>
            <div
              onClick={() => navigate(card.path)}
              title={(card as any).tooltip || ''}
              style={{
                background: BG_CARD,
                borderRadius: 10,
                padding: '24px 20px',
                cursor: 'pointer',
                border: `1px solid ${BORDER}`,
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = GOLD_BORDER; e.currentTarget.style.boxShadow = '0 4px 20px rgba(212,168,83,0.08)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = BORDER; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <div style={{ fontSize: 42, fontWeight: 700, color: card.color, fontFamily: 'Georgia, serif' }}>
                {card.value}
              </div>
              <div style={{ color: TEXT_SECONDARY, marginTop: 6, fontSize: 13 }}>{card.label}</div>
              {card.sub && (
                <div style={{ color: card.subColor, fontSize: 11, marginTop: 4 }}>{card.sub}</div>
              )}
            </div>
          </Col>
        ))}
      </Row>

      {/* 高优先级事件 + SLA告警 + AI活动 */}
      <Row gutter={20}>
        <Col span={14}>
          <div style={{ marginBottom: 12, color: TEXT_MUTED, fontSize: 10, fontWeight: 600, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
            HIGH PRIORITY ({highPriorityEvents.length})
          </div>
          {highPriorityEvents.length === 0 ? (
            <div style={{ background: BG_CARD, borderRadius: 10, padding: 24, textAlign: 'center', border: `1px solid ${BORDER}` }}>
              <Empty description={<span style={{ color: TEXT_MUTED }}>暂无高优先级事件</span>} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {highPriorityEvents.map(event => (
                <div
                  key={event.id}
                  style={{
                    background: BG_CARD,
                    borderRadius: 10,
                    padding: '16px 20px',
                    borderLeft: `3px solid ${riskColors[event.risk_level] || TEXT_MUTED}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    border: `1px solid ${BORDER}`,
                    borderLeftColor: riskColors[event.risk_level] || TEXT_MUTED,
                    borderLeftWidth: 3,
                  }}
                  onClick={() => navigate(`/events/${event.id}`)}
                  onMouseEnter={(e) => { e.currentTarget.style.background = BG_CARD_HOVER; e.currentTarget.style.borderColor = GOLD_BORDER; e.currentTarget.style.borderLeftColor = riskColors[event.risk_level] || TEXT_MUTED; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = BG_CARD; e.currentTarget.style.borderColor = BORDER; e.currentTarget.style.borderLeftColor = riskColors[event.risk_level] || TEXT_MUTED; }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: TEXT_PRIMARY }}>{event.title}</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                    <Tag style={{ background: riskColors[event.risk_level], border: 'none', color: '#fff', margin: 0, fontSize: 11 }}>
                      {event.risk_level}
                    </Tag>
                    <Tag style={{ background: 'rgba(212,168,83,0.1)', border: `1px solid ${GOLD_BORDER}`, color: GOLD, margin: 0, fontSize: 11 }}>
                      {statusLabels[event.status] || event.status}
                    </Tag>
                    {event.desk && (
                      <Tag style={{ background: 'rgba(255,255,255,0.05)', border: `1px solid ${BORDER}`, color: TEXT_SECONDARY, margin: 0, fontSize: 11 }}>
                        {event.desk}
                      </Tag>
                    )}
                  </div>
                  <div style={{ color: TEXT_MUTED, fontSize: 11 }}>
                    更新于 {new Date(event.updated_at).toLocaleString('zh-CN')}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* SLA 告警区 */}
          {slaAlerts.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <div style={{ marginBottom: 10, color: TEXT_MUTED, fontSize: 10, fontWeight: 600, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
                SLA ALERTS ({slaAlerts.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {slaAlerts.map(alert => (
                  <div key={alert.task_id} style={{
                    background: BG_CARD,
                    borderRadius: 8,
                    padding: '10px 14px',
                    borderLeft: `3px solid ${alert.sla_status === 'overdue' ? '#C0392B' : GOLD}`,
                    cursor: 'pointer',
                    border: `1px solid ${BORDER}`,
                    borderLeftColor: alert.sla_status === 'overdue' ? '#C0392B' : GOLD,
                    borderLeftWidth: 3,
                  }}
                    onClick={() => navigate(`/sign-off/${alert.task_id}`)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: TEXT_PRIMARY }}>{alert.story_packet_title}</span>
                      <span style={{
                        color: alert.sla_status === 'overdue' ? '#C0392B' : GOLD,
                        fontSize: 12, fontWeight: 500,
                      }}>
                        {alert.sla_status === 'overdue'
                          ? `超时 ${alert.minutes_overdue}m`
                          : `剩余 ${alert.minutes_remaining}m`}
                      </span>
                    </div>
                    <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 3 }}>{alert.approval_stage}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Col>
        <Col span={10}>
          <div style={{ marginBottom: 12, color: TEXT_MUTED, fontSize: 10, fontWeight: 600, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
            AI AGENT ACTIVITY
          </div>
          <div style={{ background: BG_CARD, borderRadius: 10, padding: 16, border: `1px solid ${BORDER}` }}>
            {agentActivities.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 16 }}>
                <Empty description={<span style={{ color: TEXT_MUTED }}>暂无 Agent 活动记录</span>} />
              </div>
            ) : (
              agentActivities.map((activity, index) => (
                <div 
                  key={index}
                  style={{ 
                    display: 'flex', 
                    gap: 12, 
                    padding: '10px 0',
                    borderBottom: index < agentActivities.length - 1 ? `1px solid ${BORDER}` : 'none',
                  }}
                >
                  <div style={{ 
                    width: 6, 
                    height: 6, 
                    borderRadius: '50%', 
                    backgroundColor: GOLD,
                    marginTop: 6,
                    flexShrink: 0,
                    boxShadow: `0 0 4px rgba(212,168,83,0.4)`,
                  }} />
                  <div>
                    <div style={{ color: TEXT_MUTED, fontSize: 11, marginBottom: 3 }}>
                      {new Date(activity.timestamp).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} {new Date(activity.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div style={{ fontSize: 13 }}>
                      <span style={{ fontWeight: 600, color: GOLD }}>{activity.agent_name}</span>
                      <span style={{ color: TEXT_SECONDARY }}> {activity.summary}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Col>
      </Row>
    </div>
    </Spin>
  );
}
