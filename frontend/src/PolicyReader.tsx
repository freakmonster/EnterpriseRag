// 规章制度文档阅览页 — 文档列表 + 章节目录 + 正文展示
import {
  MenuOutlined,
  MessageOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { App as AntApp, Button, Drawer, Input, Spin } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import { fetchPolicyDoc, fetchPolicyList, type PolicyDocMeta } from './api'

// 文档正文数据（含章节目录）
interface DocData {
  content: string
  sections: { title: string; line: number }[]
}

// Props：由 App 传入的正文搜索关键词与「咨询助手」回调
interface PolicyReaderProps {
  textQuery: string
  onAskAssistant: (question: string) => void
}

// 转义正则特殊字符，避免关键词作为正则时出错
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// 正文中命中关键词用 <mark> 包裹（配合 rehypeRaw 渲染为高亮）
function highlightMarkdown(content: string, q: string): string {
  if (!q.trim()) return content
  const re = new RegExp(escapeRegExp(q.trim()), 'gi')
  return content.replace(re, m => `<mark>${m}</mark>`)
}

function PolicyReader({ textQuery, onAskAssistant }: PolicyReaderProps) {
  const { message } = AntApp.useApp()

  // 文档列表
  const [docList, setDocList] = useState<PolicyDocMeta[]>([])
  const [docListLoading, setDocListLoading] = useState(true)
  const [docListError, setDocListError] = useState('')
  const [docQuery, setDocQuery] = useState('')        // 文档列表过滤关键词

  // 当前文档与正文
  const [activeDoc, setActiveDoc] = useState('')       // 当前文档 file_name
  const [contentData, setContentData] = useState<DocData | null>(null)
  const [docLoading, setDocLoading] = useState(false)
  const docCache = useRef<Map<string, DocData>>(new Map()) // 已加载文档缓存

  // 阅读器交互
  const [activeSectionIdx, setActiveSectionIdx] = useState(0) // 当前高亮章节
  const [sideOpen, setSideOpen] = useState(false)      // 移动端文档列表抽屉
  const contentRef = useRef<HTMLDivElement>(null)      // 正文滚动容器（scroll-spy）

  const q = textQuery.trim().toLowerCase()
  const activeTitle = docList.find(d => d.file_name === activeDoc)?.title || ''

  // 加载文档清单
  async function loadDocList() {
    setDocListLoading(true)
    setDocListError('')
    try {
      const data = await fetchPolicyList()
      setDocList(data.items)
      // 默认选中第一份文档
      if (data.items.length > 0) {
        void selectDoc(data.items[0].file_name)
      }
    } catch {
      setDocListError('加载失败')
    } finally {
      setDocListLoading(false)
    }
  }

  useEffect(() => {
    void loadDocList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 选择文档：命中缓存直接展示，否则请求正文并缓存
  async function selectDoc(fileName: string) {
    if (!fileName || fileName === activeDoc) return
    setActiveDoc(fileName)
    setActiveSectionIdx(0)
    const cached = docCache.current.get(fileName)
    if (cached) {
      setContentData(cached)
      return
    }
    setDocLoading(true)
    try {
      const data = await fetchPolicyDoc(fileName)
      docCache.current.set(fileName, data)
      setContentData(data)
    } catch {
      message.error('无法加载政策原文')
    } finally {
      setDocLoading(false)
    }
  }

  // 按章节标题滚动正文到对应 h2
  function scrollToSection(idx: number) {
    const container = contentRef.current
    if (!container || !contentData) return
    const title = contentData.sections[idx]?.title
    if (!title) return
    const h2s = Array.from(container.querySelectorAll('h2'))
    for (const h2 of h2s) {
      if (h2.textContent?.trim() === title) {
        h2.scrollIntoView({ behavior: 'smooth', block: 'start' })
        break
      }
    }
  }

  // 正文滚动时同步高亮当前章节（scroll-spy）
  function handleContentScroll() {
    const container = contentRef.current
    if (!container || !contentData || contentData.sections.length === 0) return
    const h2s = Array.from(container.querySelectorAll('h2'))
    let current = 0
    const top = container.getBoundingClientRect().top + 72
    for (let i = 0; i < h2s.length; i++) {
      if (h2s[i].getBoundingClientRect().top <= top) current = i
    }
    if (current !== activeSectionIdx) setActiveSectionIdx(current)
  }

  // 章节是否命中搜索关键词（标题或该章节正文）
  const sectionMatches = useMemo<boolean[] | null>(() => {
    if (!q || !contentData) return null
    const lines = contentData.content.split('\n')
    return contentData.sections.map((s, i) => {
      const start = s.line
      const end = i + 1 < contentData.sections.length ? contentData.sections[i + 1].line : lines.length
      const body = lines.slice(start, end).join('\n')
      return s.title.toLowerCase().includes(q) || body.toLowerCase().includes(q)
    })
  }, [q, contentData])

  // 搜索关键词变化时，滚动到第一个命中章节
  useEffect(() => {
    if (!q || !sectionMatches) return
    const firstIdx = sectionMatches.findIndex(m => m)
    if (firstIdx >= 0) {
      setActiveSectionIdx(firstIdx)
      scrollToSection(firstIdx)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, sectionMatches])

  // 构造咨询问题
  function buildQuestion(docTitle: string, sectionTitle?: string): string {
    if (sectionTitle) {
      return `关于《${docTitle}》「${sectionTitle}」，请解答相关规定与办理流程`
    }
    return `请介绍《${docTitle}》的主要内容与重点规定`
  }

  // 移动端 FAB：咨询当前章节（无章节时咨询整篇文档）
  function askCurrent() {
    if (!contentData) return
    const section = contentData.sections[activeSectionIdx]?.title
    onAskAssistant(buildQuestion(activeTitle, section))
  }

  // 文档列表（侧栏 / 抽屉共用）
  const filteredDocList = docQuery.trim()
    ? docList.filter(d => d.title.toLowerCase().includes(docQuery.trim().toLowerCase()))
    : docList

  function renderDocList() {
    if (docListLoading) {
      return (
        <div className="doc-list-skeleton">
          {[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="sk-line skeleton-shimmer" />)}
        </div>
      )
    }
    if (docListError) {
      return <div className="doc-list-empty" onClick={() => void loadDocList()}>{docListError}，点击重试</div>
    }
    if (filteredDocList.length === 0) {
      return <div className="doc-list-empty">{docQuery ? '未找到匹配的文档' : '暂无制度文档'}</div>
    }
    return filteredDocList.map(item => (
      <div
        key={item.file_name}
        className={`doc-item ${item.file_name === activeDoc ? 'active' : ''}`}
        onClick={() => { selectDoc(item.file_name); setSideOpen(false) }}
        title={item.title}
      >
        <span className="doc-item-name">{item.title}</span>
      </div>
    ))
  }

  // 章节目录（桌面目录列）
  function renderTocItems() {
    if (!contentData) return null
    return contentData.sections.map((s, i) => {
      const dimmed = sectionMatches !== null && !sectionMatches[i]
      return (
        <div
          key={i}
          className={`toc-item ${i === activeSectionIdx ? 'active' : ''} ${dimmed ? 'dimmed' : ''}`}
          onClick={() => {
            setActiveSectionIdx(i)
            scrollToSection(i)
          }}
        >
          <span className="toc-label">{s.title}</span>
          <button
            className="toc-ask"
            onClick={e => {
              e.stopPropagation()
              onAskAssistant(buildQuestion(activeTitle, s.title))
            }}
            title="咨询智能助手"
          >
            咨询
          </button>
        </div>
      )
    })
  }

  return (
    <>
      {/* 移动端文档列表抽屉 */}
      <Drawer
        title="制度文档"
        placement="left"
        width={264}
        open={sideOpen}
        onClose={() => setSideOpen(false)}
        className="doc-drawer"
        destroyOnHidden
      >
        <div className="doc-side-search">
          <Input
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            placeholder="搜索文档…"
            value={docQuery}
            onChange={e => setDocQuery(e.target.value)}
            allowClear
          />
        </div>
        <div className="doc-list">{renderDocList()}</div>
      </Drawer>

      {/* 桌面侧栏：制度文档列表 */}
      <aside className="sidebar doc-sidebar">
        <div className="sidebar-inner">
          <div className="doc-side-head">
            <span>制度文档</span>
            <span className="count">{docList.length}</span>
          </div>
          <div className="doc-side-search">
            <Input
              prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
              placeholder="搜索文档…"
              value={docQuery}
              onChange={e => setDocQuery(e.target.value)}
              allowClear
            />
          </div>
          <div className="doc-list">{renderDocList()}</div>
        </div>
      </aside>

      {/* 主区：文档头部 + 阅读器 */}
      <main className="doc-main">
        <div className="doc-main-head">
          <Button
            className="header-icon-btn doc-mobile-menu"
            icon={<MenuOutlined />}
            onClick={() => setSideOpen(true)}
            title="文档列表"
          />
          <span className="doc-title">{activeTitle || '制度文档阅览'}</span>
          {contentData && (
            <div className="doc-chips">
              <span className="chip">{contentData.sections.length} 章节</span>
              <span className="chip">更新 {docList.find(d => d.file_name === activeDoc)?.updated_at}</span>
            </div>
          )}
        </div>

        <div className="doc-reader">
          {/* 章节目录列（桌面） */}
          <div className="doc-toc">
            <div className="toc-title">目录</div>
            {renderTocItems()}
          </div>

          {/* 正文区 */}
          <div className="doc-content" ref={contentRef} onScroll={handleContentScroll}>
            {docLoading ? (
              <div style={{ textAlign: 'center', padding: 48 }}><Spin tip="加载中..." /></div>
            ) : contentData ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw]}
              >
                {highlightMarkdown(contentData.content, q)}
              </ReactMarkdown>
            ) : (
              <div className="doc-empty">
                <div className="doc-empty-icon"><MessageOutlined /></div>
                <div className="doc-empty-text">从左侧选择一份制度文档开始阅读</div>
              </div>
            )}
            {q && contentData && sectionMatches !== null && !sectionMatches.some(m => m) && (
              <div className="doc-no-match">未找到相关内容</div>
            )}
          </div>
        </div>
      </main>

      {/* 移动端悬浮「咨询助手」按钮 */}
      <button className="ask-fab" onClick={askCurrent} title="咨询智能助手">
        <MessageOutlined />
        <span>咨询助手</span>
      </button>
    </>
  )
}

export default PolicyReader
