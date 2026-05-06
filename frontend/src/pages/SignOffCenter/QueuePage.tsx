import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Tag, Button, Progress, Spin, Empty, Input, Select } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { approvalsApi } from '@/services/api';

const GOLD = '#D4A853';
const GOLD_BORDER = 'rgba(212,168,83,0.2)';
const BG_CARD = '#141414';
const BG_CARD_HOVER = '#1A1A1A';
const BORDER = 'rgba(212,168,83,0.1)';
const TEXT_PRIMARY = '#F5F5F5';
const TEXT_SECONDARY = 'rgba(245,245,245,0.65)';
const TEXT_MUTED = 'rgba(245,245,245,0.35)';

interface ApprovalTask {
  id: string;
  story_packet_id?: string;
  title: string;
  risk_level: string;
  approval_stage: string;
  desk: string;
  owner: string;
  sla_status: string;
  sla_text: string;
  signers: number[];
}

const riskColors: Record<string, { bg: string; text: string; border?: string }> = {
  L0: { bg: '#22c55e', text: '#fff' },
  L1: { bg: '#eab308', text: '#000' },
  L2: { bg: '#f97316', text: '#fff' },
  L3: { bg: '#ef4444', text: '#fff', border: '#ef4444' },
};

const viewLabels: Record<string, string> = {
  pending: '待我签发',
  initiated: '我发起的',
  returned: '我退回的',
  completed: '已签发',
  high_risk: '高风险',
  due_today: '今日到期',
  overdue: '已超时',
};

const stageLabels: Record<string, string> = {
  editorial_review: '编辑审',
  risk_review: '风险审',
  channel_review: '渠道审',
  final_review: '终审',
};

export default function QueuePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get('view') || 'pending';
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [, setApiAvailable] = useState(true);
  const [selectedTask, setSelectedTask] = useState<ApprovalTask | null>(null);
  const [searchText, setSearchText] = useState('');
  const [filterDesk, setFilterDesk] = useState<string | undefined>(undefined);
  const [filterRisk, setFilterRisk] = useState<string | undefined>(undefined);
  const [filterStage, setFilterStage] = useState<string | undefined>(undefined);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (view === 'pending' || view === 'initiated' || view === 'returned') {
        params.view = view;
      } else if (view === 'completed') {
        params.status = 'approved';
      } else if (view === 'high_risk') {
        params.view = 'pending';
      } else if (view === 'due_today' || view === 'overdue') {
        params.view = 'pending';
      }
      const res = await approvalsApi.listTasks(params);
      let items = res.items || res;
      if (!Array.isArray(items)) items = [];
      // Client-side filtering for special views
      if (view === 'high_risk') {
        items = items.filter((t: any) => t.risk_level === 'L2' || t.risk_level === 'L3');
      } else if (view === 'due_today') {
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        const todayStart = new Date();
        todayStart.setHours(0, 0, 0, 0);
        items = items.filter((t: any) => {
          if (!t.sla_deadline) return false;
          const d = new Date(t.sla_deadline);
          return d >= todayStart && d <= today;
        });
      } else if (view === 'overdue') {
        items = items.filter((t: any) => {
          if (!t.sla_deadline) return false;
          return new Date(t.sla_deadline) < new Date();
        });
      }
      setTasks(items.map((t: any) => ({
        id: t.id,
        story_packet_id: t.story_packet_id,
        title: t.title || `审批任务 ${t.id?.slice(0, 8)}`,
        risk_level: t.risk_level || 'L0',
        approval_stage: t.approval_stage || '',
        desk: t.desk || '',
        owner: t.owner || '',
        sla_status: t.sla_deadline && new Date(t.sla_deadline) < new Date() ? 'overdue' : 'normal',
        sla_text: t.sla_deadline ? `截止 ${new Date(t.sla_deadline).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` : '',
        signers: (t.signer_slots || []).map((s: any) => ['completed', 'approved'].includes(s.status) ? 1 : 0),
      })));
      setApiAvailable(true);
    } catch {
      setApiAvailable(false);
      // API 不可用时显示空列表，不使用假数据
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const handleViewChange = (newView: string) => {
    setSearchParams({ view: newView });
    setSelectedTask(null);
  };

  // Client-side filter
  const filteredTasks = tasks.filter(t => {
    if (searchText && !t.title.toLowerCase().includes(searchText.toLowerCase()) && !t.id.includes(searchText)) return false;
    if (filterDesk && t.desk !== filterDesk) return false;
    if (filterRisk && t.risk_level !== filterRisk) return false;
    if (filterStage && t.approval_stage !== filterStage) return false;
    return true;
  });

  const uniqueDesks = [...new Set(tasks.map(t => t.desk).filter(Boolean))];
  const uniqueStages = [...new Set(tasks.map(t => t.approval_stage).filter(Boolean))];

  const renderSignerStatus = (signers: number[]) => {
    return (
      <div style={{ display: 'flex', gap: 3 }}>
        {signers.map((status, index) => (
          <div
            key={index}
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              backgroundColor: status === 1 ? '#22c55e' : 'rgba(212,168,83,0.15)',
              border: status === 1 ? 'none' : `1px solid ${BORDER}`,
            }}
          />
        ))}
      </div>
    );
  };

  const renderTaskCard = (task: ApprovalTask, isCompleted = false) => (
    <div
      key={task.id}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '14px 16px',
        background: BG_CARD,
        borderRadius: 10,
        marginBottom: 10,
        cursor: 'pointer',
        border: `1px solid ${BORDER}`,
        borderLeftWidth: task.risk_level === 'L3' ? 3 : 1,
        borderLeftColor: task.risk_level === 'L3' ? '#C0392B' : BORDER,
        transition: 'all 0.2s ease',
      }}
      onClick={() => navigate(`/sign-off/${task.id}`)}
      onMouseEnter={(e) => { setSelectedTask(task); e.currentTarget.style.background = BG_CARD_HOVER; e.currentTarget.style.borderColor = GOLD_BORDER; if (task.risk_level === 'L3') e.currentTarget.style.borderLeftColor = '#C0392B'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = BG_CARD; e.currentTarget.style.borderColor = BORDER; if (task.risk_level === 'L3') e.currentTarget.style.borderLeftColor = '#C0392B'; }}
    >
      {/* 左侧状态点 */}
      {!isCompleted && (
        <div style={{ 
          width: 7, 
          height: 7, 
          borderRadius: '50%', 
          backgroundColor: task.sla_status === 'overdue' ? '#C0392B' : GOLD,
          boxShadow: task.sla_status === 'overdue' ? '0 0 6px rgba(192,57,43,0.4)' : `0 0 4px rgba(212,168,83,0.3)`,
          flexShrink: 0,
        }} />
      )}

      {/* 任务信息 */}
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 3, color: TEXT_PRIMARY }}>
          {task.title}
        </div>
        <div style={{ color: TEXT_MUTED, fontSize: 12 }}>
          {stageLabels[task.approval_stage] || task.approval_stage} · {task.desk} · {task.risk_level}
        </div>
      </div>

      {/* 风险标签 + SLA */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <Tag
          style={{
            background: riskColors[task.risk_level]?.bg,
            color: riskColors[task.risk_level]?.text,
            border: 'none',
            margin: 0,
            padding: '1px 8px',
            fontSize: 11,
          }}
        >
          {task.risk_level}
          {task.risk_level === 'L3' && ' 红线'}
        </Tag>

        {/* SLA 进度条 */}
        <div style={{ width: 80 }}>
          <Progress 
            percent={task.sla_status === 'overdue' ? 100 : task.sla_status === 'done' ? 100 : 60}
            strokeColor={task.sla_status === 'overdue' ? '#C0392B' : task.sla_status === 'done' ? '#22c55e' : GOLD}
            trailColor="rgba(212,168,83,0.1)"
            showInfo={false}
            size="small"
          />
        </div>

        {/* SLA 文字 */}
        <div style={{ 
          width: 70, 
          textAlign: 'right',
          color: task.sla_status === 'overdue' ? '#C0392B' : task.sla_status === 'done' ? '#22c55e' : TEXT_SECONDARY,
          fontSize: 12,
        }}>
          {task.sla_text}
        </div>

        {/* 签位状态 */}
        {renderSignerStatus(task.signers)}

        {/* 操作按钮 */}
        <Button
          size="small"
          style={{ 
            background: isCompleted ? 'rgba(34,197,94,0.1)' : 'rgba(212,168,83,0.1)',
            borderColor: isCompleted ? 'rgba(34,197,94,0.3)' : GOLD_BORDER,
            color: isCompleted ? '#22c55e' : GOLD,
            fontSize: 12,
          }}
        >
          {isCompleted ? '已签发' : stageLabels[task.approval_stage] || task.approval_stage.replace('_review', '审')}
        </Button>
      </div>
    </div>
  );

  return (
    <div style={{ padding: 28, color: TEXT_PRIMARY }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, color: TEXT_PRIMARY }}>签发中心</h1>
        <div style={{ color: TEXT_MUTED, marginTop: 4, fontSize: 12, letterSpacing: '0.5px' }}>
          Sign-off Center · {viewLabels[view] || '待我签发'}
        </div>
      </div>

      {/* 顶部过滤条 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          prefix={<SearchOutlined style={{ color: 'rgba(212,168,83,0.4)' }} />}
          placeholder="搜索任务标题或 ID"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          style={{ width: 220, background: BG_CARD, borderColor: BORDER, color: TEXT_PRIMARY }}
          allowClear
        />
        <Select
          placeholder="Desk"
          value={filterDesk}
          onChange={v => setFilterDesk(v)}
          allowClear
          style={{ width: 120 }}
          options={uniqueDesks.map(d => ({ label: d, value: d }))}
          popupMatchSelectWidth={false}
        />
        <Select
          placeholder="审批阶段"
          value={filterStage}
          onChange={v => setFilterStage(v)}
          allowClear
          style={{ width: 120 }}
          options={uniqueStages.map(s => ({ label: stageLabels[s] || s, value: s }))}
          popupMatchSelectWidth={false}
        />
        <Select
          placeholder="风险等级"
          value={filterRisk}
          onChange={v => setFilterRisk(v)}
          allowClear
          style={{ width: 110 }}
          options={[
            { label: 'L0', value: 'L0' },
            { label: 'L1', value: 'L1' },
            { label: 'L2', value: 'L2' },
            { label: 'L3', value: 'L3' },
          ]}
        />
      </div>

      {/* 导航分类 */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        {(['pending', 'initiated', 'returned'] as const).map(v => (
          <Button
            key={v}
            onClick={() => handleViewChange(v)}
            style={{
              background: view === v ? 'rgba(212,168,83,0.15)' : BG_CARD,
              borderColor: view === v ? GOLD_BORDER : BORDER,
              color: view === v ? GOLD : TEXT_SECONDARY,
              fontWeight: view === v ? 600 : 400,
              fontSize: 13,
            }}
          >
            {viewLabels[v]}
          </Button>
        ))}
        <div style={{ width: 1, height: 20, background: BORDER, margin: '0 4px' }} />
        {(['completed', 'high_risk', 'due_today', 'overdue'] as const).map(v => (
          <Button
            key={v}
            onClick={() => handleViewChange(v)}
            style={{
              background: view === v ? 'rgba(212,168,83,0.15)' : BG_CARD,
              borderColor: view === v ? GOLD_BORDER : BORDER,
              color: view === v ? (v === 'overdue' ? '#C0392B' : v === 'high_risk' ? '#f97316' : GOLD) : TEXT_SECONDARY,
              fontWeight: view === v ? 600 : 400,
              fontSize: 13,
            }}
          >
            {viewLabels[v]}
          </Button>
        ))}
      </div>

      {/* 主内容区：左侧列表 + 右侧预览 */}
      <div style={{ display: 'flex', gap: 20 }}>
        {/* 中间任务列表 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
          ) : filteredTasks.length === 0 ? (
            <Empty description={<span style={{ color: TEXT_MUTED }}>暂无{viewLabels[view]}任务</span>} />
          ) : (
            <div>
              <div style={{ color: TEXT_MUTED, fontSize: 10, marginBottom: 10, fontWeight: 600, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
                {viewLabels[view]} ({filteredTasks.length})
              </div>
              {filteredTasks.map(task => renderTaskCard(task, view === 'completed'))}
            </div>
          )}
        </div>

        {/* 右侧预览面板 */}
        <div style={{
          width: 300,
          flexShrink: 0,
          background: BG_CARD,
          borderRadius: 10,
          padding: 20,
          alignSelf: 'flex-start',
          position: 'sticky',
          top: 24,
          display: filteredTasks.length > 0 ? 'block' : 'none',
          border: `1px solid ${BORDER}`,
        }}>
          {selectedTask ? (
            <>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: TEXT_PRIMARY }}>{selectedTask.title}</div>
              <div style={{ marginBottom: 12 }}>
                <Tag
                  style={{
                    background: riskColors[selectedTask.risk_level]?.bg,
                    color: riskColors[selectedTask.risk_level]?.text,
                    border: 'none',
                    margin: 0,
                    fontSize: 11,
                  }}
                >
                  {selectedTask.risk_level}
                </Tag>
              </div>
              <div style={{ fontSize: 12, color: TEXT_SECONDARY, marginBottom: 12 }}>
                <div style={{ marginBottom: 4 }}>当前状态：<span style={{ color: TEXT_PRIMARY }}>{stageLabels[selectedTask.approval_stage] || selectedTask.approval_stage}</span></div>
                <div style={{ marginBottom: 4 }}>Desk：<span style={{ color: TEXT_PRIMARY }}>{selectedTask.desk || '—'}</span></div>
                <div style={{ marginBottom: 4 }}>Owner：<span style={{ color: TEXT_PRIMARY }}>{selectedTask.owner || '—'}</span></div>
                <div style={{ marginBottom: 4 }}>SLA：<span style={{ color: selectedTask.sla_status === 'overdue' ? '#C0392B' : TEXT_PRIMARY }}>{selectedTask.sla_text || '—'}</span></div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 10, color: TEXT_MUTED, marginBottom: 4, fontWeight: 600, letterSpacing: '1px', textTransform: 'uppercase' }}>签位状态</div>
                {renderSignerStatus(selectedTask.signers)}
              </div>
              <Button
                type="primary"
                block
                onClick={() => navigate(`/sign-off/${selectedTask.id}`)}
                style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600 }}
              >
                打开详情
              </Button>
            </>
          ) : (
            <div style={{ color: TEXT_MUTED, textAlign: 'center', padding: 32, fontSize: 13 }}>
              鼠标悬停任务查看预览
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
