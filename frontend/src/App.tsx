import { CopyOutlined, LeftOutlined, LogoutOutlined, PauseCircleOutlined, PlusOutlined, RedoOutlined, RightOutlined, SendOutlined } from '@ant-design/icons'
import { Button, Dropdown, Input, List, Spin, message } from 'antd'
import type React from 'react'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getHistory, getSessions, sendMessageStream } from './api'
import './App.css'
import Login from './Login'

// 引用来源项类型
interface CitationItem {
  id: number
  title: string
  file_name: string
}

// 消息类型
interface ChatMsg {
  id: number
  role: string      // USER 或 ASSISTANT
  content: string
  created_at: string
  citations?: CitationItem[] // 引用来源（仅助手消息）
}

// 从 JWT 中解码用户名
function getUsername(token: string): string {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.username || '用户'
  } catch {
    return '用户'
  }
}

function App() {
  const [token, setToken] = useState<string>(localStorage.getItem('token') || '')
  const [username, setUsername] = useState<string>(() => getUsername(token))
  const [sessions, setSessions] = useState<{session_id: string, title: string}[]>([]) // 会话列表
  const [activeSession, setActiveSession] = useState<string>('') // 当前会话ID
  const [messages, setMessages] = useState<ChatMsg[]>([])        // 当前会话的消息
  const [input, setInput] = useState('')                        // 输入框内容
  const [loading, setLoading] = useState(false)                 // 发送中loading
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false) // 侧边栏收起
  const msgEndRef = useRef<HTMLDivElement>(null)                // 用于自动滚到底部
  const abortRef = useRef<AbortController | null>(null)         // 用于中断请求

  // 登录后 / token 变化时获取会话列表
  useEffect(() => {
    if (token) loadSessions()
  }, [token])

  // 切换会话时加载历史消息
  useEffect(() => {
    if (activeSession) {
      loadHistory(activeSession)
    } else {
      setMessages([])
    }
  }, [activeSession])

  // 消息更新时自动滚到底部
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 加载会话列表
  async function loadSessions() {
    try {
      const data = await getSessions()
      setSessions(data)
      // 如果有会话，默认选中第一个
      if (data.length > 0 && !activeSession) {
        setActiveSession(data[0].session_id)
      }
    } catch {
      message.error('加载会话列表失败')
    }
  }

  // 加载会话历史
  async function loadHistory(sessionId: string) {
    try {
      const data = await getHistory(sessionId)
      setMessages(data)
    } catch {
      message.error('加载历史消息失败')
    }
  }

  // 新建会话
  function newSession() {
    setActiveSession('')
    setMessages([])
  }

  // 发送消息
  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setLoading(true)

    // 创建 AbortController 用于停止生成
    const controller = new AbortController()
    abortRef.current = controller

    // 先在界面上显示用户消息（乐观更新）
    const tempUserMsg: ChatMsg = {
      id: Date.now(),
      role: 'USER',
      content: text,
      created_at: new Date().toISOString(),
    }
    // 先加用户消息，再加一个空的助手消息占位
    const assistantMsgId = Date.now() + 1
    const emptyAssistantMsg: ChatMsg = {
      id: assistantMsgId,
      role: 'ASSISTANT',
      content: '',
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempUserMsg, emptyAssistantMsg])
    setInput('')

    try {
      let finalSessionId = activeSession
      await sendMessageStream(
        text,
        activeSession || undefined,
        (chunk) => {
          // 流式接收每个chunk，追加到助手消息
          setMessages(prev => prev.map(msg => {
            if (msg.id === assistantMsgId) {
              return { ...msg, content: msg.content + chunk }
            }
            return msg
          }))
        },
        (sessionId) => {
          finalSessionId = sessionId
          if (!activeSession) {
            setActiveSession(sessionId)
            loadSessions()
          }
        },
        (error) => {
          message.error(error)
        },
        controller.signal,
        (citations) => {
          // 收到引用来源数据
          setMessages(prev => prev.map(msg => {
            if (msg.id === assistantMsgId) {
              return { ...msg, citations }
            }
            return msg
          }))
        }
      )
    } catch {
      message.error('发送失败，请重试')
    } finally {
      abortRef.current = null
      setLoading(false)
    }
  }

  // 停止生成
  function handleStop() {
    abortRef.current?.abort()
    abortRef.current = null
    setLoading(false)
  }

  // 复制消息内容到剪贴板
  async function handleCopy(content: string) {
    try {
      await navigator.clipboard.writeText(content)
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败')
    }
  }

  // 重新生成回复
  function handleRegenerate(assistantMsgId: number) {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === assistantMsgId)
      if (idx <= 0) return prev
      const userMsg = prev[idx - 1]
      if (userMsg.role !== 'USER') return prev

      const filtered = prev.filter(m => m.id !== assistantMsgId)
      setLoading(true)
      const controller = new AbortController()
      abortRef.current = controller

      const newAssistantId = Date.now()
      const emptyMsg: ChatMsg = {
        id: newAssistantId,
        role: 'ASSISTANT',
        content: '',
        created_at: new Date().toISOString(),
      }

      ;(async () => {
        try {
          await sendMessageStream(
            userMsg.content,
            activeSession || undefined,
            (chunk) => {
              setMessages(prev => prev.map(m =>
                m.id === newAssistantId ? { ...m, content: m.content + chunk } : m
              ))
            },
            (sessionId) => {
              if (!activeSession) {
                setActiveSession(sessionId)
                loadSessions()
              }
            },
            (error) => { message.error(error) },
            controller.signal,
            (citations) => {
              setMessages(prev => prev.map(m =>
                m.id === newAssistantId ? { ...m, citations } : m
              ))
            }
          )
        } catch {
          message.error('重新生成失败')
        } finally {
          abortRef.current = null
          setLoading(false)
        }
      })()

      return [...filtered, emptyMsg]
    })
  }

  // Enter发送，Shift+Enter换行
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // 渲染带引用标记的消息内容
  // 将正文中的 [n] 渲染为上标引用标记，其他部分正常用 ReactMarkdown
  function renderContent(msg: ChatMsg): ReactNode {
    const content = msg.content
    // 分割正文，将 [n] 和普通文本交替渲染
    const parts = content.split(/(\[\d+\])/g)
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/)
      if (match) {
        const cid = parseInt(match[1])
        const hasCitation = msg.citations?.some(c => c.id === cid)
        const title = hasCitation ? '跳转到引用来源' : ''
        return (
          <sup
            key={i}
            className={`citation-ref ${hasCitation ? 'clickable' : ''}`}
            title={title}
            onClick={() => {
              if (!hasCitation) return
              const el = document.getElementById(`citation-src-${cid}`)
              if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                el.classList.add('citation-highlight')
                setTimeout(() => el.classList.remove('citation-highlight'), 2500)
              }
            }}
          >
            [{cid}]
          </sup>
        )
      }
      return <ReactMarkdown key={i} remarkPlugins={[remarkGfm]}>{part}</ReactMarkdown>
    })
  }

  // 登录处理
  function handleLogin(t: string) {
    localStorage.setItem('token', t)
    setToken(t)
    setUsername(getUsername(t))
  }

  if (!token) {
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className="app-container">
      {/* 左侧会话列表 */}
      <div className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className={`sidebar-header ${sidebarCollapsed ? 'collapsed' : ''}`}>
          {sidebarCollapsed ? (
            <>
              <Button icon={<PlusOutlined />} onClick={newSession} />
              <Button icon={<RightOutlined />} onClick={() => setSidebarCollapsed(false)} />
            </>
          ) : (
            <div className="sidebar-header-row">
              <Button icon={<PlusOutlined />} onClick={newSession} className="new-session-btn">
                新建会话
              </Button>
              <Button icon={<LeftOutlined />} onClick={() => setSidebarCollapsed(true)} className="collapse-btn" />
            </div>
          )}
        </div>
        {!sidebarCollapsed && (
          <List
            className="session-list"
            dataSource={sessions}
            renderItem={(item) => (
            <List.Item
              className={`session-item ${item.session_id === activeSession ? 'active' : ''}`}
              onClick={() => setActiveSession(item.session_id)}
            >
              <span className="session-text">{item.title}</span>
            </List.Item>
          )}
          />
        )}
      </div>

      {/* 右侧聊天区 */}
      <div className="chat-area">
        {/* 标题栏 */}
        <div className="chat-header">
            <span style={{ flex: 1, textAlign: 'center' }}>公司职员智能助手</span>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出',
                    onClick: () => {
                      localStorage.removeItem('token')
                      setToken('')
                      setUsername('用户')
                      setSessions([])
                      setActiveSession('')
                      setMessages([])
                    },
                  },
                ],
              }}
              trigger={['click']}
              placement="bottomRight"
            >
              <div className="user-avatar">
                {username.charAt(0).toUpperCase()}
              </div>
            </Dropdown>
          </div>

        {/* 消息区域 */}
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="empty-tip">输入问题开始对话</div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={`msg-row ${msg.role === 'USER' ? 'user' : 'assistant'}`}>
              {msg.role === 'USER' ? (
                <div className="msg-bubble user">
                  {msg.content.split('\n').map((line, i) => (
                    <span key={i}>
                      {line}
                      {i < msg.content.split('\n').length - 1 && <br />}
                    </span>
                  ))}
                </div>
              ) : (
                <div>
                  <div className="msg-bubble assistant">
                    {renderContent(msg)}
                    {loading && msg.content === '' && (
                      <Spin size="small" />
                    )}
                  </div>
                  {/* 引用来源卡片 */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citation-card">
                      <div className="citation-card-title">引用来源</div>
                      {msg.citations.map(c => (
                        <div
                          key={c.id}
                          id={`citation-src-${c.id}`}
                          className="citation-item"
                        >
                          <span className="citation-id">[{c.id}]</span>
                          <span className="citation-title">{c.title}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.content && !loading && (
                    <div className="msg-actions">
                      <Button
                        size="small"
                        type="text"
                        icon={<CopyOutlined />}
                        onClick={() => handleCopy(msg.content)}
                      />
                      <Button
                        size="small"
                        type="text"
                        icon={<RedoOutlined />}
                        onClick={() => handleRegenerate(msg.id)}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={msgEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="chat-input">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题......"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
          />
          {loading ? (
            <Button className="stop-btn" icon={<PauseCircleOutlined />} onClick={handleStop} />
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!input.trim()}
            />
          )}
        </div>
        <div className="input-hint">Enter发送，Shift+Enter换行</div>
      </div>
    </div>
  )
}

export default App
