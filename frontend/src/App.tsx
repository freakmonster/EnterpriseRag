// 主应用 — 公司职员智能助手（重构版）
import {
    CheckOutlined,
    CopyOutlined,
    FileTextOutlined,
    FolderOutlined,
    LeftOutlined,
    LogoutOutlined,
    MessageOutlined,
    MoonOutlined,
    PauseCircleOutlined,
    PlusOutlined,
    RedoOutlined,
    RightOutlined,
    RobotOutlined,
    SafetyCertificateOutlined,
    SearchOutlined,
    SendOutlined,
    SunOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons'
import { App as AntApp, Button, ConfigProvider, Dropdown, Input, Modal, Spin, theme } from 'antd'
import type React from 'react'
import { Fragment, type ReactNode, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import { fetchPolicyDoc, getHistory, getSessions, sendMessageStream } from './api'
import './App.css'
import Login from './Login'

// 引用来源项类型
interface CitationItem {
  id: number
  title: string
  file_name: string
  chunk_idx: number
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

// 日期分组展示（今天 / 昨天 / 具体日期）
function formatDay(iso?: string): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((today.getTime() - day.getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

// 时间格式化 HH:mm
function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 建议问题
const SUGGESTIONS = [
  '年假有几天？满一年和满五年分别是多少？',
  '迟到和旷工会怎么处理？',
  '绩效考核的等级有哪些？绩效奖金怎么算？',
  '出差住宿标准是多少？怎么报销？',
  '公司的福利待遇包括哪些？',
  '入职流程是怎样的？',
  '个人敏感信息有什么保护规定？',
  '员工培训有哪些？培训费用谁出？',
]

// 能力卡片
const CAPABILITIES: { icon: ReactNode; title: string; desc: string; prompt: string }[] = [
  { icon: <SearchOutlined />, title: '制度问答', desc: '快速获取公司制度答案', prompt: '公司的考勤制度是怎样的？' },
  { icon: <SafetyCertificateOutlined />, title: '原文溯源', desc: '每条回答附政策出处', prompt: '请假需要走什么流程？' },
  { icon: <FolderOutlined />, title: '会话管理', desc: '多会话自由切换', prompt: '入职流程是怎样的？' },
  { icon: <MessageOutlined />, title: '持续对话', desc: '上下文连贯理解', prompt: '公司的福利待遇包括哪些？' },
]

// 输入框轮播提示语
const PLACEHOLDERS = [
  '输入问题，例如：年假有几天？',
  '问我关于公司制度的问题…',
  '例如：绩效考核怎么算？',
  '例如：出差住宿标准是多少？',
]

function App() {
  const [isDark, setIsDark] = useState<boolean>(() => localStorage.getItem('theme') === 'dark')

  return (
    <ConfigProvider theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
      <AntApp>
        <AppInner isDark={isDark} onToggleTheme={() => setIsDark(v => !v)} />
      </AntApp>
    </ConfigProvider>
  )
}

// 内层应用：位于 <AntApp> provider 内部，可正常使用 useApp() 的 message
function AppInner({ isDark, onToggleTheme }: { isDark: boolean; onToggleTheme: () => void }) {
  const { message } = AntApp.useApp()
  const [token, setToken] = useState<string>(localStorage.getItem('token') || '')
  const [username, setUsername] = useState<string>(() => getUsername(token))
  const [sessions, setSessions] = useState<{ session_id: string; title: string }[]>([]) // 会话列表
  const [activeSession, setActiveSession] = useState<string>('') // 当前会话ID
  const [messages, setMessages] = useState<ChatMsg[]>([])        // 当前会话的消息
  const [input, setInput] = useState('')                        // 输入框内容
  const [loading, setLoading] = useState(false)                 // 发送中loading
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false) // 侧边栏收起
  const [sessionsLoading, setSessionsLoading] = useState(false)  // 会话列表加载中
  const [sessionQuery, setSessionQuery] = useState('')           // 会话搜索关键字
  const [copiedId, setCopiedId] = useState<number | null>(null)  // 复制成功反馈
  const [phIdx, setPhIdx] = useState(0)                          // 轮播提示语索引
  const msgEndRef = useRef<HTMLDivElement>(null)                // 用于自动滚到底部
  const abortRef = useRef<AbortController | null>(null)         // 用于中断请求
  const policyModalRef = useRef<HTMLDivElement>(null)           // 政策弹窗内容区

  // 政策原文弹窗状态
  const [policyModalOpen, setPolicyModalOpen] = useState(false)
  const [policyContent, setPolicyContent] = useState('')
  const [policySections, setPolicySections] = useState<{ title: string; line: number }[]>([])
  const [policyActiveSectionIdx, setPolicyActiveSectionIdx] = useState(-1)
  const [policyLoading, setPolicyLoading] = useState(false)

  // 明暗主题：同步到 <html data-theme> 与 localStorage
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
    localStorage.setItem('theme', isDark ? 'dark' : 'light')
  }, [isDark])

  // 登录后 / token 变化时获取会话列表
  useEffect(() => {
    if (token) loadSessions()
  }, [token])

  // 切换会话时加载历史消息
  useEffect(() => {
    if (activeSession) {
      loadHistory(activeSession)
    }
  }, [activeSession])

  // 消息更新时自动滚到底部
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 政策弹窗打开后，自动滚动到对应章节并高亮
  useEffect(() => {
    if (policyModalOpen && policyActiveSectionIdx >= 0 && policyActiveSectionIdx < policySections.length) {
      const timer = setTimeout(() => {
        const sectionTitle = policySections[policyActiveSectionIdx].title
        const container = policyModalRef.current
        if (!container) return
        const h2Elements = Array.from(container.querySelectorAll('h2'))
        for (const h2 of h2Elements) {
          if (h2.textContent?.trim() === sectionTitle) {
            h2.scrollIntoView({ behavior: 'smooth', block: 'start' })
            h2.classList.add('policy-section-highlight')
            setTimeout(() => h2.classList.remove('policy-section-highlight'), 2000)
            break
          }
        }
      }, 200)
      return () => clearTimeout(timer)
    }
  }, [policyModalOpen, policyContent, policyActiveSectionIdx, policySections])

  // 输入框提示语轮播
  useEffect(() => {
    const t = setInterval(() => setPhIdx(i => (i + 1) % PLACEHOLDERS.length), 3500)
    return () => clearInterval(t)
  }, [])

  // 打开政策原文弹窗
  async function openPolicyModal(citation: CitationItem) {
    if (!citation.file_name) return
    setPolicyLoading(true)
    setPolicyModalOpen(true)
    setPolicyContent('')
    setPolicyActiveSectionIdx(citation.chunk_idx ?? -1)
    try {
      const data = await fetchPolicyDoc(citation.file_name)
      setPolicyContent(data.content)
      setPolicySections(data.sections)
    } catch {
      message.error('无法加载政策原文')
      setPolicyModalOpen(false)
    } finally {
      setPolicyLoading(false)
    }
  }

  // 政策弹窗内容滚动时，同步高亮当前章节
  function handlePolicyScroll() {
    const container = policyModalRef.current
    if (!container || policySections.length === 0) return
    const h2s = Array.from(container.querySelectorAll('h2'))
    let current = 0
    const top = container.getBoundingClientRect().top + 72
    for (let i = 0; i < h2s.length; i++) {
      if (h2s[i].getBoundingClientRect().top <= top) current = i
    }
    if (current !== policyActiveSectionIdx) setPolicyActiveSectionIdx(current)
  }

  // 加载会话列表
  async function loadSessions() {
    setSessionsLoading(true)
    try {
      const data = await getSessions()
      setSessions(data)
      // 如果有会话，默认选中第一个
      if (data.length > 0 && !activeSession) {
        setActiveSession(data[0].session_id)
      }
    } catch {
      message.error('加载会话列表失败')
    } finally {
      setSessionsLoading(false)
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
    setSessionQuery('')
  }

  // 发送消息（支持预设文本，如建议标签点击）
  async function handleSend(preset?: string) {
    const text = (preset ?? input).trim()
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
  async function handleCopy(msg: ChatMsg) {
    try {
      await navigator.clipboard.writeText(msg.content)
      setCopiedId(msg.id)
      setTimeout(() => setCopiedId(prev => (prev === msg.id ? null : prev)), 1800)
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
  // 将正文中的 [n] 渲染为上标引用标记，内联在文本中
  function renderContent(msg: ChatMsg): ReactNode {
    // 预处理：将 [n] 替换为自定义内联标签 <cite-ref>，使 ReactMarkdown 在同一个 <p> 内渲染
    const processed = msg.content.replace(/\[(\d+)\]/g, '<cite-ref id="$1">[$1]</cite-ref>')
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          'cite-ref': ({ id }: { id?: string }) => {
            const cid = parseInt(id ?? '')
            const hasCitation = msg.citations?.some(c => c.id === cid)
            const title = hasCitation ? '跳转到引用来源' : ''
            return (
              <sup
                className={`citation-ref ${hasCitation ? 'clickable' : ''}`}
                title={title}
                onClick={() => {
                  if (!hasCitation) return
                  const citation = msg.citations?.find(c => c.id === cid)
                  if (citation?.file_name && citation.chunk_idx !== undefined) {
                    openPolicyModal(citation)
                  } else {
                    const el = document.getElementById(`citation-src-${cid}`)
                    if (el) {
                      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                      el.classList.add('citation-highlight')
                      setTimeout(() => el.classList.remove('citation-highlight'), 2500)
                    }
                  }
                }}
              >
                [{cid}]
              </sup>
            )
          }
        } as unknown as Parameters<typeof ReactMarkdown>[0]['components']}
      >
        {processed}
      </ReactMarkdown>
    )
  }

  // 登录处理
  function handleLogin(t: string) {
    localStorage.setItem('token', t)
    setToken(t)
    setUsername(getUsername(t))
  }

  // 退出登录
  function handleLogout() {
    abortRef.current?.abort()
    localStorage.removeItem('token')
    setToken('')
    setUsername('用户')
    setSessions([])
    setActiveSession('')
    setMessages([])
    setSessionQuery('')
  }

  // 建议标签直接发送
  function handleSendWith(text: string) {
    setInput('')
    void handleSend(text)
  }

  // 会话列表（按关键字过滤）
  const filteredSessions = sessionQuery.trim()
    ? sessions.filter(s => s.title.toLowerCase().includes(sessionQuery.trim().toLowerCase()))
    : sessions

  // 当前会话标题
  const activeTitle = sessions.find(s => s.session_id === activeSession)?.title || '新对话'

  return (
    <>
      {!token ? (
        <Login onLogin={handleLogin} />
      ) : (
        <div className="app-container">
          {/* 动态极光背景 */}
          <div className="aurora">
            <div className="aurora-blob blob-1" />
            <div className="aurora-blob blob-2" />
            <div className="aurora-blob blob-3" />
          </div>

          <div className="app-content">
            {/* 左侧会话栏 */}
            <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
              <div className="sidebar-inner">
                {/* 品牌区 */}
                <div className="sidebar-brand">
                  <div className="brand-mark">
                    <ThunderboltOutlined />
                  </div>
                  <div className="brand-text">
                    <span className="brand-name">智能助手</span>
                    <span className="brand-sub">公司制度 · 即问即答</span>
                  </div>
                </div>

                {/* 新建会话 */}
                <div className="new-session-wrap">
                  <Button className="new-session-btn" onClick={newSession}>
                    <PlusOutlined />
                    <span className="btn-label">新建会话</span>
                  </Button>
                </div>

                {/* 搜索会话 */}
                {!sidebarCollapsed && (
                  <div className="session-search">
                    <Input
                      prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
                      placeholder="搜索会话"
                      value={sessionQuery}
                      onChange={e => setSessionQuery(e.target.value)}
                      allowClear
                    />
                  </div>
                )}

                {/* 会话列表 */}
                <div className="session-list">
                  {sessionsLoading ? (
                    <div className="session-skeleton">
                      {[0, 1, 2, 3].map(i => <div key={i} className="sk-line skeleton-shimmer" />)}
                    </div>
                  ) : filteredSessions.length === 0 ? (
                    <div className="session-empty">
                      {sessionQuery ? '未找到匹配的会话' : '暂无会话，点击"新建会话"开始提问'}
                    </div>
                  ) : (
                    filteredSessions.map(item => (
                      <div
                        key={item.session_id}
                        className={`session-item ${item.session_id === activeSession ? 'active' : ''}`}
                        onClick={() => setActiveSession(item.session_id)}
                        title={item.title}
                      >
                        <MessageOutlined className="session-icon" />
                        <span className="session-text">{item.title}</span>
                      </div>
                    ))
                  )}
                </div>

                {/* 底部用户区 */}
                <div className="sidebar-footer">
                  <Dropdown
                    menu={{
                      items: [
                        {
                          key: 'logout',
                          icon: <LogoutOutlined />,
                          label: '退出登录',
                          onClick: handleLogout,
                        },
                      ],
                    }}
                    trigger={['click']}
                    placement="topRight"
                  >
                    <div className="user-chip">
                      <div className="user-avatar">{username.charAt(0).toUpperCase()}</div>
                      <div className="user-meta">
                        <span className="user-name">{username}</span>
                        <span className="user-role">在线 · 职员</span>
                      </div>
                    </div>
                  </Dropdown>
                  <Button
                    className="icon-btn"
                    icon={isDark ? <SunOutlined /> : <MoonOutlined />}
                    onClick={onToggleTheme}
                    title={isDark ? '切换到浅色模式' : '切换到深色模式'}
                  />
                </div>
              </div>
            </aside>

            {/* 右侧聊天区 */}
            <main className="chat-area">
              {/* 顶部栏 */}
              <header className="chat-header">
                <div className="chat-header-left">
                  <Button
                    className="header-icon-btn"
                    icon={sidebarCollapsed ? <RightOutlined /> : <LeftOutlined />}
                    onClick={() => setSidebarCollapsed(v => !v)}
                    title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
                  />
                  <div className="chat-header-title">
                    <span className="online-dot" />
                    <span className="chat-title-text">{activeTitle}</span>
                  </div>
                </div>
                <div className="chat-header-right">
                  <Button
                    className="icon-btn"
                    icon={isDark ? <SunOutlined /> : <MoonOutlined />}
                    onClick={onToggleTheme}
                    title={isDark ? '切换到浅色模式' : '切换到深色模式'}
                  />
                  <Dropdown
                    menu={{
                      items: [
                        {
                          key: 'logout',
                          icon: <LogoutOutlined />,
                          label: '退出登录',
                          onClick: handleLogout,
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
              </header>

              {/* 消息区域 */}
              <div className="chat-messages" role="log" aria-live="polite">
                <div className="chat-messages-inner">
                  {messages.length === 0 && (
                    <div className="empty-state">
                      <div className="welcome-logo">
                        <ThunderboltOutlined />
                      </div>
                      <div className="welcome-title grad-text">公司职员智能助手</div>
                      <div className="welcome-sub">检索公司制度，快速获得精准回答 —— 每条回答都附原文出处</div>
                      <div className="capability-grid">
                        {CAPABILITIES.map(cap => (
                          <div key={cap.title} className="capability-card" onClick={() => setInput(cap.prompt)}>
                            <div className="cap-card-icon">{cap.icon}</div>
                            <div className="cap-card-title">{cap.title}</div>
                            <div className="cap-card-desc">{cap.desc}</div>
                          </div>
                        ))}
                      </div>
                      <div className="suggestions">
                        {SUGGESTIONS.map(s => (
                          <span key={s} className="suggestion-chip" onClick={() => { setInput(''); handleSendWith(s) }}>
                            <ThunderboltOutlined className="chip-icon" />
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {(() => {
                    let lastDay: string | null = null
                    return messages.map(msg => {
                      const day = formatDay(msg.created_at)
                      const showDivider = day !== null && day !== lastDay
                      if (day !== null) lastDay = day
                      const isLast = messages.length > 0 && messages[messages.length - 1].id === msg.id
                      return (
                        <Fragment key={msg.id}>
                          {showDivider && <div className="date-divider">{day}</div>}
                          <div className={`msg-row ${msg.role === 'USER' ? 'user' : 'assistant'}`}>
                            {msg.role === 'USER' ? (
                              <div className="msg-body" style={{ alignItems: 'flex-end' }}>
                                <div className="msg-bubble user">
                                  {msg.content.split('\n').map((line, i) => (
                                    <span key={i}>
                                      {line}
                                      {i < msg.content.split('\n').length - 1 && <br />}
                                    </span>
                                  ))}
                                </div>
                                {msg.created_at && <div className="msg-time">{formatTime(msg.created_at)}</div>}
                              </div>
                            ) : (
                              <>
                                <div className="assistant-avatar">
                                  <RobotOutlined />
                                </div>
                                <div className="msg-body">
                                  <div className="msg-bubble assistant">
                                    {renderContent(msg)}
                                    {loading && msg.content === '' && (
                                      <div className="thinking-bubble">
                                        <div className="dot-pulse">
                                          <span /><span /><span />
                                        </div>
                                        <span>正在思考</span>
                                      </div>
                                    )}
                                    {loading && isLast && msg.content !== '' && <span className="stream-cursor" />}
                                  </div>
                                  {msg.created_at && <div className="msg-time">{formatTime(msg.created_at)}</div>}
                                  {/* 引用来源卡片 */}
                                  {msg.citations && msg.citations.length > 0 && (
                                    <div className="citation-card">
                                      <div className="citation-card-title">
                                        <FileTextOutlined className="cite-icon" />
                                        <span>引用来源 —— 点击下方卡片查看政策文档详情</span>
                                      </div>
                                      {msg.citations.map(c => (
                                        <div
                                          key={c.id}
                                          id={`citation-src-${c.id}`}
                                          className="citation-item citation-clickable"
                                          onClick={() => {
                                            if (c.file_name && c.chunk_idx !== undefined) {
                                              openPolicyModal(c)
                                            }
                                          }}
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
                                        icon={copiedId === msg.id ? <CheckOutlined /> : <CopyOutlined />}
                                        onClick={() => handleCopy(msg)}
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
                              </>
                            )}
                          </div>
                        </Fragment>
                      )
                    })
                  })()}
                  <div ref={msgEndRef} />
                </div>
              </div>

              {/* 输入区域 */}
              <div className="chat-input-wrap">
                <div className="chat-input-box">
                  <div className="chat-input">
                    <Input.TextArea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder={PLACEHOLDERS[phIdx]}
                      autoSize={{ minRows: 1, maxRows: 4 }}
                      disabled={loading}
                    />
                    {loading ? (
                      <Button className="stop-btn" icon={<PauseCircleOutlined />} onClick={handleStop} title="停止生成" />
                    ) : (
                      <Button
                        className="send-btn"
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={() => handleSend()}
                        disabled={!input.trim()}
                        title="发送"
                      />
                    )}
                  </div>
                  <div className="input-hint">
                    <span className="input-hint-left">
                      <ThunderboltOutlined className="hint-icon" />
                      智能制度检索助手
                    </span>
                    <span className="input-hint-right">Enter 发送 · Shift + Enter 换行</span>
                  </div>
                </div>
              </div>
            </main>
          </div>

          {/* 政策原文弹窗 */}
          <Modal
            title={<span><FileTextOutlined style={{ color: 'var(--accent)' }} /> 政策原文</span>}
            open={policyModalOpen}
            onCancel={() => setPolicyModalOpen(false)}
            footer={null}
            width={820}
            className="policy-modal"
            destroyOnHidden
          >
            <div className="policy-nav visible">
              <div className="policy-nav-title">目录</div>
              {policySections.map((s, i) => (
                <button
                  key={i}
                  className={`policy-nav-item ${i === policyActiveSectionIdx ? 'active' : ''}`}
                  onClick={() => setPolicyActiveSectionIdx(i)}
                >
                  {s.title}
                </button>
              ))}
            </div>
            <div className="policy-modal-body" ref={policyModalRef} onScroll={handlePolicyScroll}>
              {policyLoading ? (
                <div style={{ textAlign: 'center', padding: 48 }}>
                  <Spin tip="加载中..." />
                </div>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{policyContent}</ReactMarkdown>
              )}
            </div>
          </Modal>
        </div>
      )}
    </>
  )
}

export default App
