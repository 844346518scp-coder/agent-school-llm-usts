import type { Question } from './api'

// 同济大学数学科学学院《高等数学》第八版，高等教育出版社。
// 上册 ISBN 9787040589818；下册 ISBN 9787040588682。来源见 docs/architecture.md。
export const courseChapters = [
  { number: 1, volume: '上册', title: '函数与极限' },
  { number: 2, volume: '上册', title: '导数与微分' },
  { number: 3, volume: '上册', title: '微分中值定理与导数的应用' },
  { number: 4, volume: '上册', title: '不定积分' },
  { number: 5, volume: '上册', title: '定积分' },
  { number: 6, volume: '上册', title: '定积分的应用' },
  { number: 7, volume: '上册', title: '微分方程' },
  { number: 8, volume: '下册', title: '向量代数与空间解析几何' },
  { number: 9, volume: '下册', title: '多元函数微分法及其应用' },
  { number: 10, volume: '下册', title: '重积分' },
  { number: 11, volume: '下册', title: '曲线积分与曲面积分' },
  { number: 12, volume: '下册', title: '无穷级数' },
] as const

export function chapterTitle(topic: string): string {
  const title = topic.trim().replace(/^第\s*[一二三四五六七八九十\d]+\s*章\s*/, '')
  return courseChapters.find(chapter => chapter.title === title)?.title || topic
}

export function filterQuestions(questions: readonly Question[], chapter: string, search: string): Question[] {
  const query = search.trim().toLocaleLowerCase()
  return questions.filter(question => (!chapter || chapterTitle(question.topic) === chapter) &&
    `${question.title} ${question.content}`.toLocaleLowerCase().includes(query))
}

export function groupQuestions(questions: readonly Question[], search = '') {
  const groups = new Map<string, Question[]>()
  for (const question of filterQuestions(questions, '', search)) {
    const title = chapterTitle(question.topic)
    const group = groups.get(title) || []
    group.push(question)
    groups.set(title, group)
  }
  const standard = courseChapters.filter(c => groups.has(c.title)).map(c => ({
    title: c.title, label: `第 ${c.number} 章 ${c.title}`, volume: c.volume, questions: groups.get(c.title)!,
  }))
  const custom = [...groups.keys()].filter(title => !courseChapters.some(c => c.title === title))
    .sort((a, b) => a.localeCompare(b, 'zh-CN')).map(title => ({ title, label: title, volume: '自定义章节', questions: groups.get(title)! }))
  return [...standard, ...custom]
}

export function assignmentTopic(content: string, currentTopic: string, questions: readonly Question[]): string {
  const topics = new Set(questions.map(q => chapterTitle(q.topic)))
  if (content.trim() && currentTopic.trim()) topics.add(chapterTitle(currentTopic))
  return topics.size === 1 ? [...topics][0] : '综合练习'
}

// Only the question stem is copied: never spread a Question (which contains the private answer).
export function appendQuestions(content: string, questions: readonly Question[]): string {
  if (!questions.length || questions.length > 30 || new Set(questions.map(q => q.id)).size !== questions.length) {
    throw new Error('请选择 1–30 道不重复的题目。')
  }
  if (questions.some(q => q.archived)) throw new Error('已归档题目不能加入作业，请重新选择。')
  const block = questions.map((q, index) => `${index + 1}. ${q.title}\n${q.content}`).join('\n\n')
  const combined = content.trim() ? `${content}\n\n${block}` : block
  if (combined.length > 3000) throw new Error('加入后题目与要求超过 3000 字，请减少选题或精简现有内容。')
  return combined
}
