export type Role = 'student' | 'teacher'
export interface User { id: string; username: string; name: string; role: Role }
export interface Conversation { id: string; question: string; answer: string; topic: string; favorite: boolean; created_at: string; mode: 'demo' }
export interface Assignment { id: string; title: string; content: string; topic: string; due_date: string; created_at: string; submitted: boolean; answer: string; submissions?: { student_name: string; answer: string; created_at: string }[] }

export class ApiError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch(`/api${path}`, { ...options, signal: controller.signal, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'shuban-web', ...options.headers } })
    const data = await response.json()
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'))
      throw new ApiError(typeof data.detail === 'string' ? data.detail : '请检查填写内容后重试。', response.status)
    }
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new Error('暂时无法连接服务，请确认后端已启动后重试。')
  } finally { clearTimeout(timeout) }
}

export const formatDate = (date: string) => new Date(date).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
