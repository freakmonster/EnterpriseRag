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
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message, sessionId: sessionId || null }),
    signal,
  })

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
  } catch (e: any) {
    // 用户主动中止不显示错误
    if (e?.name === 'AbortError') return
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
  return res.json() as Promise<{ content: string; sections: { title: string; line: number }[] }>
}
