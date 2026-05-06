import { useState, useEffect, useCallback } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Badge, Typography } from 'antd'
import {
  HomeOutlined,
  FolderOutlined,
  FileTextOutlined,
  EditOutlined,
  CheckCircleOutlined,
  SendOutlined,
  RollbackOutlined,
  SettingOutlined,
  TeamOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { dashboardApi, authApi } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

const { Sider, Content } = Layout
const { Text } = Typography

// Black-Gold Design Tokens
const GOLD = '#D4A853'
const GOLD_DIM = 'rgba(212,168,83,0.15)'
const BG_PRIMARY = '#0A0A0A'
const BG_SECONDARY = '#141414'
const BORDER_COLOR = 'rgba(212,168,83,0.12)'
const TEXT_PRIMARY = '#F5F5F5'
const TEXT_SECONDARY = 'rgba(245,245,245,0.75)'
const TEXT_MUTED = 'rgba(245,245,245,0.50)'

interface SidebarCounts {
  event_cases: number
  story_packets: number
  pending_me: number
  my_submitted: number
  my_returned: number
  sign_off_badge: number
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [counts, setCounts] = useState<SidebarCounts | null>(null)
  const [userInfo, setUserInfo] = useState<{ display_name: string; desk: string | null } | null>(null)
  const clearToken = useAuthStore(s => s.clearToken)

  const loadCounts = useCallback(async () => {
    try {
      const res = await dashboardApi.getSidebarCounts()
      setCounts(res)
    } catch {
      // 未登录或接口不可用时保持 null
    }
  }, [])

  useEffect(() => {
    loadCounts()
    const interval = setInterval(loadCounts, 30000)
    return () => clearInterval(interval)
  }, [loadCounts])

  useEffect(() => {
    authApi.getMe().then(u => setUserInfo({ display_name: u.display_name, desk: u.desk })).catch(() => {})
  }, [])

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  // Derive selectedSideKey from current route
  const getSelectedSideKey = () => {
    const path = location.pathname
    const search = location.search
    if (path === '/dashboard' || path === '/') return 'dashboard'
    if (path.startsWith('/story-packet')) return 'story-packets'
    if (path.startsWith('/sign-off')) {
      const params = new URLSearchParams(search)
      const view = params.get('view')
      if (view === 'initiated') return 'my-submitted'
      if (view === 'returned') return 'my-returned'
      return 'pending-me'
    }
    if (path.startsWith('/events')) {
      const params = new URLSearchParams(search)
      const desk = params.get('desk')
      if (desk === 'finance') return 'desk-finance'
      if (desk === 'politics') return 'desk-politics'
      if (desk === 'society') return 'desk-society'
      if (desk === 'tech') return 'desk-tech'
      if (desk === 'other') return 'desk-other'
      return 'event-cases'
    }
    if (path === '/settings/team') return 'settings-team'
    if (path.startsWith('/settings')) return 'settings-llm'
    return 'dashboard'
  }
  const selectedSideKey = getSelectedSideKey()

  // 顶部主导航
  const topNavItems = [
    { key: 'overview', label: '概览', path: '/dashboard' },
    { key: 'events', label: '事件案卷', path: '/events' },
    { key: 'story-packet', label: 'Story Packet', path: '/story-packets' },
    { key: 'sign-off', label: '签发中心', path: '/sign-off', badge: counts?.sign_off_badge || 0 },
  ]

  // 获取当前激活的顶部导航
  const getActiveTopNav = () => {
    const path = location.pathname
    if (path.startsWith('/sign-off')) return 'sign-off'
    if (path.startsWith('/story-packet')) return 'story-packet'
    if (path.startsWith('/events')) return 'events'
    return 'overview'
  }

  // 左侧边栏菜单项
  const sideMenuItems = [
    {
      key: 'workspace',
      label: '工作台',
      type: 'group',
      children: [
        { key: 'dashboard', icon: <HomeOutlined />, label: '今日概览' },
        { key: 'event-cases', icon: <FolderOutlined />, label: '事件案卷', badge: counts?.event_cases || 0 },
        { key: 'story-packets', icon: <FileTextOutlined />, label: '任务包', badge: counts?.story_packets || 0 },
      ],
    },
    {
      key: 'signoff',
      label: '签发',
      type: 'group',
      children: [
        { key: 'pending-me', icon: <CheckCircleOutlined />, label: '待我签发', badge: counts?.pending_me || 0 },
        { key: 'my-submitted', icon: <SendOutlined />, label: '我发起的', badge: counts?.my_submitted || 0 },
        { key: 'my-returned', icon: <RollbackOutlined />, label: '我退回的', badge: counts?.my_returned || 0 },
      ],
    },
    {
      key: 'desk',
      label: 'DESK',
      type: 'group',
      children: [
        { key: 'desk-finance', icon: <EditOutlined />, label: '财经' },
        { key: 'desk-politics', icon: <EditOutlined />, label: '时政' },
        { key: 'desk-society', icon: <EditOutlined />, label: '社会' },
        { key: 'desk-tech', icon: <EditOutlined />, label: '科技' },
        { key: 'desk-other', icon: <EditOutlined />, label: '其他' },
      ],
    },
    {
      key: 'settings',
      label: '设置',
      type: 'group',
      children: [
        { key: 'settings-llm', icon: <SettingOutlined />, label: 'API Key 设置' },
        { key: 'settings-team', icon: <TeamOutlined />, label: '团队管理' },
      ],
    },
  ]

  // 处理左侧菜单点击
  const handleSideMenuClick = (key: string) => {
    switch (key) {
      case 'dashboard':
        navigate('/dashboard')
        break
      case 'event-cases':
        navigate('/events')
        break
      case 'story-packets':
        navigate('/story-packets')
        break
      case 'pending-me':
        navigate('/sign-off?view=pending')
        break
      case 'my-submitted':
        navigate('/sign-off?view=initiated')
        break
      case 'my-returned':
        navigate('/sign-off?view=returned')
        break
      case 'desk-finance':
        navigate('/events?desk=finance')
        break
      case 'desk-politics':
        navigate('/events?desk=politics')
        break
      case 'desk-society':
        navigate('/events?desk=society')
        break
      case 'desk-tech':
        navigate('/events?desk=tech')
        break
      case 'desk-other':
        navigate('/events?desk=other')
        break
      case 'settings-llm':
        navigate('/settings/llm')
        break
      case 'settings-team':
        navigate('/settings/team')
        break
      default:
        break
    }
  }

  // 渲染侧边栏菜单项
  const renderMenuItem = (item: any) => {
    const isActive = selectedSideKey === item.key
    return (
      <div
        key={item.key}
        onClick={() => handleSideMenuClick(item.key)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '9px 14px',
          cursor: 'pointer',
          borderRadius: 6,
          marginBottom: 2,
          backgroundColor: isActive ? GOLD_DIM : 'transparent',
          borderLeft: isActive ? `2px solid ${GOLD}` : '2px solid transparent',
          color: isActive ? GOLD : TEXT_SECONDARY,
          transition: 'all 0.2s ease',
          fontSize: 13,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {item.icon}
          <span>{item.label}</span>
        </span>
        {item.badge ? (
          <Badge 
            count={item.badge} 
            style={{ 
              backgroundColor: item.key === 'pending-me' ? '#C0392B' : 'rgba(212,168,83,0.3)',
              color: item.key === 'pending-me' ? '#fff' : GOLD,
              fontSize: 11,
              minWidth: 18,
              height: 18,
              lineHeight: '18px',
              boxShadow: 'none',
            }} 
          />
        ) : null}
      </div>
    )
  }

  return (
    <Layout style={{ minHeight: '100vh', background: BG_PRIMARY }}>
      {/* 顶部导航栏 */}
      <div style={{ 
        height: 56, 
        background: BG_PRIMARY, 
        borderBottom: `1px solid ${BORDER_COLOR}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
      }}>
        {/* Logo */}
        <div style={{ 
          color: GOLD, 
          fontSize: 18, 
          fontWeight: 700,
          marginRight: 32,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          letterSpacing: '0.5px',
        }}>
          <span style={{ fontFamily: 'Georgia, serif' }}>NewsFlow</span>
          <Text style={{ color: TEXT_MUTED, fontSize: 11, fontWeight: 400, letterSpacing: '1px', textTransform: 'uppercase' }}>
            AI Newsroom
          </Text>
        </div>

        {/* 主导航 */}
        <div style={{ display: 'flex', gap: 4 }}>
          {topNavItems.map(item => {
            const isActive = getActiveTopNav() === item.key
            return (
              <div
                key={item.key}
                onClick={() => navigate(item.path)}
                style={{
                  padding: '6px 16px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  backgroundColor: isActive ? GOLD_DIM : 'transparent',
                  color: isActive ? GOLD : TEXT_SECONDARY,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 13,
                  fontWeight: isActive ? 500 : 400,
                  transition: 'all 0.2s ease',
                  borderBottom: isActive ? `2px solid ${GOLD}` : '2px solid transparent',
                }}
              >
                {item.label}
                {item.badge ? (
                  <Badge 
                    count={item.badge} 
                    size="small"
                    style={{ backgroundColor: '#C0392B', boxShadow: 'none' }} 
                  />
                ) : null}
              </div>
            )
          })}
        </div>

        {/* 右侧用户信息 */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ 
              width: 7, 
              height: 7, 
              borderRadius: '50%', 
              backgroundColor: '#22c55e',
              boxShadow: '0 0 6px rgba(34,197,94,0.4)',
            }} />
            <Text style={{ color: TEXT_PRIMARY, fontSize: 13 }}>
              {userInfo?.display_name || '...'}
              {userInfo?.desk && <span style={{ color: TEXT_MUTED, marginLeft: 4 }}>· {userInfo.desk}</span>}
            </Text>
          </div>
          <div
            onClick={handleLogout}
            style={{ cursor: 'pointer', color: TEXT_MUTED, fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <LogoutOutlined />
          </div>
        </div>
      </div>

      <Layout style={{ marginTop: 56 }}>
        {/* 左侧边栏 */}
        <Sider 
          width={200} 
          style={{ 
            background: BG_PRIMARY,
            borderRight: `1px solid ${BORDER_COLOR}`,
            position: 'fixed',
            left: 0,
            top: 56,
            bottom: 0,
            overflow: 'auto',
          }}
        >
          <div style={{ padding: '16px 8px' }}>
            {sideMenuItems.map(group => (
              <div key={group.key} style={{ marginBottom: 20 }}>
                <div style={{ 
                  color: TEXT_MUTED, 
                  fontSize: 10, 
                  padding: '0 14px 6px',
                  fontWeight: 600,
                  letterSpacing: '1.5px',
                  textTransform: 'uppercase',
                }}>
                  {group.label}
                </div>
                {group.children?.map(item => renderMenuItem(item))}
              </div>
            ))}
          </div>
        </Sider>

        {/* 主内容区 */}
        <Content style={{ 
          marginLeft: 200,
          background: BG_SECONDARY,
          minHeight: 'calc(100vh - 56px)',
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
