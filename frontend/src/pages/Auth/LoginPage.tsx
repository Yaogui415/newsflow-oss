import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, message, Radio, Progress } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined, TeamOutlined, KeyOutlined, LoadingOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { authApi } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'
import axios from 'axios'

const GOLD = '#D4A853'
const GOLD_BORDER = 'rgba(212,168,83,0.25)'
const BG_INPUT = '#1A1A1A'
const TEXT_MUTED = 'rgba(245,245,245,0.35)'

const configuredApiBase = import.meta.env.VITE_BACKEND_DIRECT_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'
const BACKEND_DIRECT = configuredApiBase.replace(/\/$/, '')
const BACKEND_HEALTH_URL = import.meta.env.VITE_BACKEND_HEALTH_URL || BACKEND_DIRECT.replace(/\/api\/v1\/?$/, '/health')

// 直连后端的登录（绕过 Vercel 代理，避免代理超时）
const directLogin = async (username: string, password: string) => {
  const res = await axios.post(`${BACKEND_DIRECT}/auth/login`, { username, password }, { timeout: 30000 })
  return res.data as { access_token: string; token_type: string }
}
const directRegister = async (data: Record<string, unknown>) => {
  const res = await axios.post(`${BACKEND_DIRECT}/auth/register`, data, { timeout: 30000 })
  return res.data
}

type WarmupStatus = 'checking' | 'waking' | 'ready' | 'failed'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [teamMode, setTeamMode] = useState<'create' | 'join' | 'skip'>('create')
  const [warmupStatus, setWarmupStatus] = useState<WarmupStatus>('checking')
  const [warmupSeconds, setWarmupSeconds] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const navigate = useNavigate()
  const setToken = useAuthStore((s) => s.setToken)
  const timerRef = useRef<ReturnType<typeof setInterval>>()

  const warmup = useCallback(async () => {
    setWarmupStatus('checking')
    setWarmupSeconds(0)
    setStatusMsg('正在连接服务器...')

    const startTime = Date.now()
    timerRef.current = setInterval(() => {
      setWarmupSeconds(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    const healthUrl = BACKEND_HEALTH_URL
    const maxAttempts = 12  // 最多尝试12次 x 10秒 = 2分钟
    for (let i = 0; i < maxAttempts; i++) {
      try {
        await axios.get(healthUrl, { timeout: 15000 })
        clearInterval(timerRef.current)
        setWarmupStatus('ready')
        setStatusMsg('服务器已就绪')
        return
      } catch {
        if (i === 0) {
          setWarmupStatus('waking')
          setStatusMsg('服务器正在唤醒（免费版首次访问需30-60秒）...')
        } else if (i >= 3) {
          setStatusMsg(`服务器仍在启动中，请耐心等待...（已等${Math.floor((Date.now() - startTime) / 1000)}秒）`)
        }
        await new Promise(r => setTimeout(r, 5000))
      }
    }
    clearInterval(timerRef.current)
    setWarmupStatus('failed')
    setStatusMsg('服务器启动超时，请刷新页面重试')
  }, [])

  useEffect(() => {
    warmup()
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [warmup])

  // 先通过 Vercel 代理，失败则直连后端
  const loginWithFallback = async (username: string, password: string): Promise<{ access_token: string; token_type: string }> => {
    // 第一次尝试：通过 Vercel 代理
    try {
      setStatusMsg('正在登录...')
      return await authApi.login(username, password)
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 401 || status === 400 || status === 422) throw err
      // 代理超时或网络错误，降级直连
    }
    // 第二次尝试：直连后端
    setStatusMsg('代理超时，尝试直连后端...')
    try {
      return await directLogin(username, password)
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 401 || status === 400 || status === 422) throw err
      // 直连也失败，再试一次
    }
    // 最后一次尝试
    setStatusMsg('重试中...')
    await new Promise(r => setTimeout(r, 2000))
    return await directLogin(username, password)
  }

  const registerWithFallback = async (data: Record<string, unknown>) => {
    try {
      return await authApi.register(data as any)
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 400 || status === 409 || status === 422) throw err
    }
    setStatusMsg('代理超时，尝试直连后端...')
    return await directRegister(data)
  }

  const onLogin = async (values: { username: string; password: string }) => {
    if (warmupStatus === 'waking' || warmupStatus === 'checking') {
      message.warning('服务器正在启动中，请稍等几秒再试')
      return
    }
    setLoading(true)
    try {
      const res = await loginWithFallback(values.username, values.password)
      setToken(res.access_token)
      setStatusMsg('')
      message.success('登录成功')
      navigate('/')
    } catch (err: any) {
      if (err?.response?.status === 401) {
        message.error('用户名或密码错误')
        setStatusMsg('')
      } else {
        const msg = err?.message?.includes('timeout') ? '网络超时，请检查VPN或稍后重试' : '登录失败，请稍后重试'
        message.error(msg)
        setStatusMsg(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  const onRegister = async (values: any) => {
    if (warmupStatus === 'waking' || warmupStatus === 'checking') {
      message.warning('服务器正在启动中，请稍等几秒再试')
      return
    }
    setLoading(true)
    setStatusMsg('正在注册...')
    try {
      const data: any = {
        username: values.username,
        display_name: values.display_name,
        email: values.email,
        password: values.password,
      }
      if (teamMode === 'create' && values.org_name) data.org_name = values.org_name
      if (teamMode === 'join' && values.invite_code) data.invite_code = values.invite_code

      await registerWithFallback(data)
      message.success('注册成功，正在登录...')
      setStatusMsg('注册成功，正在自动登录...')
      const loginRes = await loginWithFallback(values.username, values.password)
      setToken(loginRes.access_token)
      setStatusMsg('')
      navigate('/')
    } catch (err: any) {
      const apiMsg = err?.response?.data?.message
      message.error(apiMsg || '注册失败，请稍后重试')
      setStatusMsg('')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = { background: BG_INPUT, borderColor: GOLD_BORDER, color: '#F5F5F5', height: 42 }
  const btnStyle = {
    height: 44, background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`,
    border: 'none', fontWeight: 600, fontSize: 15, letterSpacing: '1px',
    boxShadow: '0 4px 16px rgba(212,168,83,0.25)',
  }

  const warmupBar = () => {
    if (warmupStatus === 'ready') {
      return (
        <div style={{ textAlign: 'center', marginBottom: 16, padding: '8px 12px', borderRadius: 8, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}>
          <CheckCircleOutlined style={{ color: '#22c55e', marginRight: 6 }} />
          <span style={{ color: '#22c55e', fontSize: 12 }}>服务器已就绪，可以登录</span>
        </div>
      )
    }
    if (warmupStatus === 'failed') {
      return (
        <div style={{ textAlign: 'center', marginBottom: 16, padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <span style={{ color: '#ef4444', fontSize: 12 }}>服务器连接超时 </span>
          <a onClick={warmup} style={{ color: GOLD, cursor: 'pointer', fontSize: 12 }}>点击重试</a>
        </div>
      )
    }
    // checking or waking
    const pct = Math.min(warmupSeconds * 2, 95) // ~50秒到95%
    return (
      <div style={{ marginBottom: 16, padding: '10px 12px', borderRadius: 8, background: 'rgba(212,168,83,0.06)', border: `1px solid ${GOLD_BORDER}` }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
          <LoadingOutlined style={{ color: GOLD, marginRight: 8 }} />
          <span style={{ color: GOLD, fontSize: 12, fontWeight: 500 }}>
            {warmupStatus === 'checking' ? '连接服务器...' : `服务器唤醒中（${warmupSeconds}秒）`}
          </span>
        </div>
        <Progress percent={pct} showInfo={false} strokeColor={GOLD} trailColor="rgba(212,168,83,0.1)" size="small" />
        <div style={{ color: TEXT_MUTED, fontSize: 11, marginTop: 4 }}>
          免费服务器闲置15分钟后会休眠，首次访问需30-60秒唤醒
        </div>
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      minHeight: '100vh', background: '#0A0A0A',
      backgroundImage: 'radial-gradient(ellipse at 50% 0%, rgba(212,168,83,0.06) 0%, transparent 60%)',
    }}>
      <div style={{
        width: 420, padding: 40,
        background: '#111111',
        border: `1px solid ${GOLD_BORDER}`,
        borderRadius: 12,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 80px rgba(212,168,83,0.03)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ color: GOLD, fontSize: 28, fontWeight: 700, fontFamily: 'Georgia, serif', letterSpacing: '1px' }}>
            NewsFlow
          </div>
          <div style={{ color: TEXT_MUTED, fontSize: 12, marginTop: 6, letterSpacing: '2px', textTransform: 'uppercase' }}>
            AI Newsroom Platform
          </div>
        </div>

        {warmupBar()}

        {statusMsg && warmupStatus === 'ready' && !loading && (
          <div style={{ textAlign: 'center', marginBottom: 12, fontSize: 12, color: '#f97316' }}>
            {statusMsg}
          </div>
        )}

        <div style={{ display: 'flex', marginBottom: 24, borderBottom: `1px solid ${GOLD_BORDER}` }}>
          {(['login', 'register'] as const).map(m => (
            <div key={m} onClick={() => setMode(m)} style={{
              flex: 1, textAlign: 'center', padding: '10px 0', cursor: 'pointer',
              color: mode === m ? GOLD : TEXT_MUTED, fontWeight: mode === m ? 600 : 400, fontSize: 14,
              borderBottom: mode === m ? `2px solid ${GOLD}` : '2px solid transparent',
              transition: 'all 0.2s',
            }}>
              {m === 'login' ? '登 录' : '注 册'}
            </div>
          ))}
        </div>

        {mode === 'login' ? (
          <Form onFinish={onLogin} size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="用户名" style={inputStyle} />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="密码" style={inputStyle} />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button type="primary" htmlType="submit" loading={loading} disabled={warmupStatus !== 'ready'} block style={{
                ...btnStyle,
                opacity: warmupStatus !== 'ready' ? 0.5 : 1,
              }}>
                {loading ? '登录中...' : warmupStatus !== 'ready' ? '等待服务器就绪...' : '登 录'}
              </Button>
            </Form.Item>
            <div style={{ textAlign: 'center', marginTop: 10, fontSize: 11, color: TEXT_MUTED }}>
              演示账号：zhangzhubian / newsflow123
            </div>
          </Form>
        ) : (
          <Form onFinish={onRegister} size="large">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="用户名" style={inputStyle} />
            </Form.Item>
            <Form.Item name="display_name" rules={[{ required: true, message: '请输入显示名称' }]}>
              <Input prefix={<UserOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="显示名称（如：张三）" style={inputStyle} />
            </Form.Item>
            <Form.Item name="email" rules={[{ required: true, type: 'email', message: '请输入有效邮箱' }]}>
              <Input prefix={<MailOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="邮箱" style={inputStyle} />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, min: 6, message: '密码至少6位' }]}>
              <Input.Password prefix={<LockOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="密码" style={inputStyle} />
            </Form.Item>

            <div style={{ marginBottom: 16 }}>
              <div style={{ color: 'rgba(245,245,245,0.55)', fontSize: 12, marginBottom: 8 }}>新闻工作团队</div>
              <Radio.Group value={teamMode} onChange={e => setTeamMode(e.target.value)} style={{ width: '100%' }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[
                    { v: 'create' as const, label: '创建新团队' },
                    { v: 'join' as const, label: '加入团队' },
                    { v: 'skip' as const, label: '暂不设置' },
                  ].map(o => (
                    <Radio.Button key={o.v} value={o.v} style={{
                      flex: 1, textAlign: 'center', fontSize: 12,
                      background: teamMode === o.v ? 'rgba(212,168,83,0.15)' : '#1A1A1A',
                      borderColor: teamMode === o.v ? GOLD : GOLD_BORDER,
                      color: teamMode === o.v ? GOLD : 'rgba(245,245,245,0.5)',
                    }}>{o.label}</Radio.Button>
                  ))}
                </div>
              </Radio.Group>
            </div>

            {teamMode === 'create' && (
              <Form.Item name="org_name" rules={[{ required: true, message: '请输入团队名称' }]}>
                <Input prefix={<TeamOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="团队名称（如：财新新闻编辑部）" style={inputStyle} />
              </Form.Item>
            )}
            {teamMode === 'join' && (
              <Form.Item name="invite_code" rules={[{ required: true, message: '请输入邀请码' }]}>
                <Input prefix={<KeyOutlined style={{ color: 'rgba(212,168,83,0.5)' }} />} placeholder="团队邀请码（8位大写字母+数字）" style={inputStyle} />
              </Form.Item>
            )}

            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button type="primary" htmlType="submit" loading={loading} disabled={warmupStatus !== 'ready'} block style={{
                ...btnStyle,
                opacity: warmupStatus !== 'ready' ? 0.5 : 1,
              }}>
                {loading ? '注册中...' : warmupStatus !== 'ready' ? '等待服务器就绪...' : '注册并开始'}
              </Button>
            </Form.Item>
          </Form>
        )}

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: TEXT_MUTED }}>
          {mode === 'login'
            ? <span>还没有账号？<a onClick={() => setMode('register')} style={{ color: GOLD, cursor: 'pointer' }}>立即注册</a></span>
            : <span>已有账号？<a onClick={() => setMode('login')} style={{ color: GOLD, cursor: 'pointer' }}>返回登录</a></span>
          }
        </div>
      </div>
    </div>
  )
}
