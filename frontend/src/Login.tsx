import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Input, Tabs, message } from 'antd'
import { useState } from 'react'

interface Props {
  onLogin: (token: string) => void
}

function Login({ onLogin }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState('login')

  async function handleSubmit() {
    if (!username.trim() || !password.trim()) {
      message.warning('请输入用户名和密码')
      return
    }
    if (tab === 'register' && password !== confirmPassword) {
      message.error('密码不一致，请重新确认密码')
      return
    }
    setLoading(true)
    try {
      const endpoint = tab === 'login' ? '/api/login' : '/api/register'
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      const data = await res.json()
      if (!res.ok) {
        message.error(data.detail || '请求失败')
        return
      }
      localStorage.setItem('token', data.token)
      onLogin(data.token)
    } catch {
      message.error('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit()
  }

  return (
    <div className="login-page">
      <div className="login-bg-decor" />
      <div className="login-card">
        <div className="login-content">
          <div className="login-brand">
            <h1>公司职员智能助手</h1>
            <p>智能检索，精准回答，让每一条公司制度触手可及</p>
          </div>

          <Tabs
            activeKey={tab}
            onChange={setTab}
            centered
            className="login-tabs"
            items={[
              { key: 'login', label: '登录' },
              { key: 'register', label: '注册' },
            ]}
          />

          <div className="login-form">
            <Input
              prefix={<UserOutlined style={{color:'var(--text-muted)'}}/>}
              placeholder="用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={20}
            />
            <Input.Password
              prefix={<LockOutlined style={{color:'var(--text-muted)'}}/>}
              placeholder="密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              maxLength={50}
            />
            {tab === 'register' && (
              <Input.Password
                prefix={<LockOutlined style={{color:'var(--text-muted)'}}/>}
                placeholder="确认密码"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                maxLength={50}
              />
            )}
            <Button
              type="primary"
              block
              loading={loading}
              onClick={handleSubmit}
              className="login-btn"
            >
              {tab === 'login' ? '登录' : '注册'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login
