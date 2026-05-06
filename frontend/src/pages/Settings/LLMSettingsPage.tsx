import { useState, useEffect } from 'react'
import { Button, Input, Select, InputNumber, message, Spin } from 'antd'
import { KeyOutlined, DeleteOutlined, SaveOutlined } from '@ant-design/icons'
import { authApi } from '@/services/api'

export default function LLMSettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hasKey, setHasKey] = useState(false)
  const [maskedKey, setMaskedKey] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('gpt-4o-mini')
  const [budget, setBudget] = useState<number>(20)

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    setLoading(true)
    try {
      const res = await authApi.getLLMSettings()
      setHasKey(res.has_api_key || false)
      setMaskedKey(res.api_key_masked || '')
      setProvider(res.provider || 'openai')
      setModel(res.model_preference || 'gpt-4o-mini')
      setBudget(res.daily_budget_usd ?? 20)
    } catch {
      // No settings yet
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!apiKey && !hasKey) {
      message.error('请输入 API Key')
      return
    }
    setSaving(true)
    try {
      const data: any = {
        daily_budget_usd: budget,
        model_preference: model,
        provider,
      }
      if (apiKey) data.api_key = apiKey
      await authApi.updateLLMSettings(data)
      message.success('API Key 配置已保存')
      setApiKey('')
      loadSettings()
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    try {
      await authApi.deleteLLMSettings()
      message.success('API Key 配置已清除')
      setHasKey(false)
      setMaskedKey('')
      setApiKey('')
    } catch {
      message.error('清除失败')
    }
  }

  const GOLD = '#D4A853'
  const GOLD_BORDER = 'rgba(212,168,83,0.25)'
  const BORDER = 'rgba(212,168,83,0.1)'
  const TEXT_PRIMARY = '#F5F5F5'
  const TEXT_MUTED = 'rgba(245,245,245,0.35)'
  const TEXT_LABEL = 'rgba(245,245,245,0.55)'
  const BG_CARD = '#141414'
  const BG_INPUT = '#0E0E0E'

  return (
    <div style={{ padding: 28, color: TEXT_PRIMARY, maxWidth: 580 }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, marginBottom: 6, color: TEXT_PRIMARY }}>API Key 设置</h1>
      <div style={{ color: TEXT_MUTED, marginBottom: 28, fontSize: 12, letterSpacing: '0.5px' }}>
        配置你的 LLM API Key，系统将使用你的额度运行 AI Agent
      </div>

      <Spin spinning={loading}>
        <div style={{ background: BG_CARD, borderRadius: 10, padding: 28, border: `1px solid ${BORDER}` }}>
          {hasKey && (
            <div style={{
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.2)',
              borderRadius: 8,
              padding: '10px 14px',
              marginBottom: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <KeyOutlined style={{ color: '#22c55e' }} />
                <span style={{ color: TEXT_PRIMARY }}>当前 Key：<span style={{ color: '#22c55e' }}>{maskedKey}</span></span>
              </div>
              <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDelete} style={{ fontSize: 12 }}>
                清除
              </Button>
            </div>
          )}

          <div style={{ marginBottom: 20 }}>
            <div style={{ color: TEXT_LABEL, marginBottom: 6, fontSize: 12, fontWeight: 500 }}>
              {hasKey ? '更换 API Key（留空则保持当前 Key）' : 'API Key'}
            </div>
            <Input.Password
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="sk-..."
              style={{ background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY, height: 40 }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <div style={{ color: TEXT_LABEL, marginBottom: 6, fontSize: 12, fontWeight: 500 }}>Provider</div>
            <Select
              value={provider}
              onChange={setProvider}
              style={{ width: '100%' }}
              showSearch
              allowClear
              placeholder="选择或输入 Provider"
              options={[
                { value: 'openai', label: 'OpenAI' },
                { value: 'anthropic', label: 'Anthropic' },
                { value: 'azure', label: 'Azure OpenAI' },
                { value: 'zhipu', label: '智谱 (Zhipu / GLM)' },
                { value: 'deepseek', label: 'DeepSeek' },
                { value: 'moonshot', label: 'Moonshot (Kimi)' },
                { value: 'baichuan', label: '百川 (Baichuan)' },
                { value: 'qwen', label: '通义千问 (Qwen)' },
                { value: 'minimax', label: 'MiniMax' },
                { value: 'yi', label: '零一万物 (Yi)' },
                { value: 'google', label: 'Google Gemini' },
                { value: 'mistral', label: 'Mistral' },
              ]}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <div style={{ color: TEXT_LABEL, marginBottom: 6, fontSize: 12, fontWeight: 500 }}>模型偏好</div>
            <Select
              value={model}
              onChange={setModel}
              style={{ width: '100%' }}
              showSearch
              allowClear
              placeholder="选择或输入模型名称"
              options={[
                { value: 'gpt-4o', label: 'GPT-4o' },
                { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
                { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
                { value: 'claude-3-5-sonnet', label: 'Claude 3.5 Sonnet' },
                { value: 'claude-3-opus', label: 'Claude 3 Opus' },
                { value: 'glm-4', label: 'GLM-4 (智谱)' },
                { value: 'glm-4-flash', label: 'GLM-4 Flash (智谱)' },
                { value: 'deepseek-chat', label: 'DeepSeek Chat' },
                { value: 'deepseek-coder', label: 'DeepSeek Coder' },
                { value: 'moonshot-v1-8k', label: 'Moonshot v1' },
                { value: 'qwen-max', label: 'Qwen Max' },
                { value: 'qwen-turbo', label: 'Qwen Turbo' },
                { value: 'gemini-pro', label: 'Gemini Pro' },
                { value: 'mistral-large', label: 'Mistral Large' },
              ]}
            />
          </div>

          <div style={{ marginBottom: 28 }}>
            <div style={{ color: TEXT_LABEL, marginBottom: 6, fontSize: 12, fontWeight: 500 }}>每日预算 (USD)</div>
            <InputNumber
              value={budget}
              onChange={v => setBudget(v ?? 20)}
              min={0}
              max={1000}
              style={{ width: '100%', background: BG_INPUT, borderColor: GOLD_BORDER, color: TEXT_PRIMARY }}
            />
          </div>

          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={handleSave}
            block
            style={{ background: `linear-gradient(135deg, ${GOLD} 0%, #B8860B 100%)`, border: 'none', color: '#0A0A0A', fontWeight: 600, height: 40 }}
          >
            保存配置
          </Button>
        </div>
      </Spin>
    </div>
  )
}
