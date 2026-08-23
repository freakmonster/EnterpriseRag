// 后端API封装
// 后端地址通过vite proxy代理，前端直接请求 /api/xxx
// JWT token 从 localStorage 读取，自动附带 Authorization header

const API_BASE = '/api'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || ''
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

// 发送聊天消息（流式）
export async function sendMessageStream(
  message: string,
  sessionId: string | undefined,
  onChunk: (chunk: string) => void,
  onEnd: (sessionId: string) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
  onCitations?: (items: {id: number, title: string, file_name: string, chunk_idx: number}[]) => void
) {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message, sessionId: sessionId || null }),
      signal,
    })
  } catch (e) {
    // 用户主动中止（停止生成）不显示错误
    if (e instanceof Error && e.name === 'AbortError') return
    onError(e instanceof Error ? e.message : '未知错误')
    return
  }

  if (!res.ok) {
    onError(`请求失败: ${res.status}`)
    return
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'content') {
              onChunk(data.content)
            } else if (data.type === 'end') {
              onEnd(data.session_id)
            } else if (data.type === 'error') {
              onError(data.content)
            } else if (data.type === 'citations') {
              onCitations?.(data.items)
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  } catch (e) {
    // 用户主动中止不显示错误
    if (e instanceof Error && e.name === 'AbortError') return
    onError(e instanceof Error ? e.message : '未知错误')
  }
}

// 获取会话历史消息
export async function getHistory(sessionId: string) {
  const res = await fetch(`${API_BASE}/history?session_id=${encodeURIComponent(sessionId)}`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

// 获取用户的会话列表
export async function getSessions() {
  const res = await fetch(`${API_BASE}/sessions`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

// 获取政策原文（用于引用弹出查看）
export async function fetchPolicyDoc(fileName: string) {
  const res = await fetch(`${API_BASE}/policy/${encodeURIComponent(fileName)}`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json() as Promise<{ content: string; sections: { title: string; line: number }[]; title: string }>
}

// 制度文档元数据类型
export interface PolicyDocMeta {
  file_name: string
  title: string
  section_count: number
  updated_at: string
}

// 获取制度文档清单
export async function fetchPolicyList(): Promise<{ items: PolicyDocMeta[] }> {
  const res = await fetch(`${API_BASE}/policies`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

// ── 管理看板统计接口 ──────────────────────────────────

// 运营总览（时段统计）
export interface AdminOverview {
  active_users: number
  active_sessions: number
  total_calls: number
  total_cost: number
  total_input_tokens: number
  total_output_tokens: number
  error_count: number
  avg_latency_ms: number
}

// 某模型在某天的统计
export interface AdminModelStats {
  calls: number
  input_tokens: number
  output_tokens: number
  cost: number
  avg_latency_ms: number
}

// 趋势：按日期 + 模型类型聚合
export interface AdminTrend {
  days: {
    date: string
    models: Record<string, AdminModelStats>
    active_users: number
    active_sessions: number
  }[]
}

// 聚合：每用户 / 每会话平均
export interface AdminAggItem {
  avg_calls: number
  avg_input_tokens: number
  avg_output_tokens: number
  avg_cost: number
  avg_latency_ms: number
}

export interface AdminAggregation {
  per_user: AdminAggItem
  per_session: AdminAggItem
}

// 拼装日期范围查询串（可选 from/to，格式 YYYY-MM-DD）
function buildRangeQuery(from?: string, to?: string): string {
  const params = new URLSearchParams()
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

// 运营总览统计
export async function fetchAdminOverview(from?: string, to?: string): Promise<AdminOverview> {
  const res = await fetch(`/admin/stats/overview${buildRangeQuery(from, to)}`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

// 趋势统计（按日）
export async function fetchAdminTrend(from?: string, to?: string): Promise<AdminTrend> {
  const res = await fetch(`/admin/stats/trend${buildRangeQuery(from, to)}`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

// 聚合统计（人均 / 每会话）
export async function fetchAdminAggregation(from?: string, to?: string): Promise<AdminAggregation> {
  const res = await fetch(`/admin/stats/aggregation${buildRangeQuery(from, to)}`, {
    headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}
