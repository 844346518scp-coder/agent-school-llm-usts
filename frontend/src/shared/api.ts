export type Role = 'student' | 'teacher'
export interface User { id: string; username: string; name: string; role: Role }
export interface Reference { index: number; id: string; title: string; source: string; verified: boolean }
export interface Conversation { id: string; question: string; answer: string; topic: string; favorite: boolean; created_at: string; mode: 'demo' | 'live'; notice?: string | null; references?: Reference[] }
export type ReviewStatus = 'needs_improvement' | 'completed'
export interface Review { id: string; version: number; comment: string; status: ReviewStatus; answer_snapshot: string; reviewed_at: string }
export interface Submission { id: string; student_id: string; student_name: string; answer: string; created_at: string; version: number; review: Review | null; review_history: Review[] }
export interface Assignment { id: string; title: string; content: string; topic: string; due_date: string; created_at: string; status: 'draft' | 'published' | 'archived'; submitted: boolean; answer: string; submission: Submission | null; submissions?: Submission[] }
export interface Question { id: string; title: string; topic: string; content: string; reference_answer: string; archived: boolean }
export interface TeachingStats { published: number; submitted: number; pending: number; needs_improvement: number; completed: number }
export const localToday = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
export const reviewLabel = (status?: ReviewStatus) => status === 'completed' ? '教师确认完成' : status === 'needs_improvement' ? '待改进' : '待批改'

export class ApiError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const isAiWrite = options.method === 'POST' && (path === '/conversations' || path.startsWith('/agent/'))
  const timeout = setTimeout(() => controller.abort(), isAiWrite ? 90000 : 15000)
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
    if (isAiWrite) throw new Error('本次响应未能完成接收。请先刷新学习记录确认是否已保存，再决定是否重试，避免重复提问。')
    throw new Error('暂时无法连接服务，请确认后端已启动后重试。')
  } finally { clearTimeout(timeout) }
}

export const formatDate = (date: string) => new Date(date).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
