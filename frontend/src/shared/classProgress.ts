import type { ClassStudent } from './api'

export type MemberFilter = 'active' | 'removed' | 'all'

export function memberBatchTargets(visible: readonly ClassStudent[], selectedIds: readonly string[], active: boolean): ClassStudent[] {
  const selected = new Set(selectedIds)
  // Membership is separate from account management, including legacy accounts.
  return visible.filter(student => selected.has(student.id) && student.member_active !== active)
}

export async function runMemberBatch(targets: readonly ClassStudent[], update: (student: ClassStudent) => Promise<unknown>) {
  const completed: string[] = []
  for (const student of targets) {
    try { await update(student); completed.push(student.id) }
    catch (error) {
      // A timeout may have committed. Do not retry or continue silently.
      return { completed, failed: student, error: error instanceof Error ? error.message : '请求失败', unprocessed: targets.length - completed.length - 1 }
    }
  }
  return { completed, failed: null, error: '', unprocessed: 0 }
}

export function filterClassStudents(students: readonly ClassStudent[], search: string, memberFilter: MemberFilter): ClassStudent[] {
  const query = search.trim().toLowerCase()
  return students.filter(student =>
    (memberFilter === 'all' || (memberFilter === 'active' ? student.member_active : !student.member_active)) &&
    `${student.name} ${student.username}`.toLowerCase().includes(query),
  )
}

function csvCell(value: string | number): string {
  let text = String(value)
  // Quoting alone does not prevent spreadsheets from interpreting formulas.
  // Preserve the original text after a leading apostrophe, including whitespace.
  if (/^[\s\u0000-\u001f]*[=+\-@\t\r\n]/u.test(text)) text = "'" + text
  return `"${text.replace(/"/g, '""')}"`
}

export function classProgressCsv(className: string, students: readonly ClassStudent[]): string {
  const rows: (string | number)[][] = [
    ['班级', '账号', '姓名', '成员状态', '账号状态', '应交', '已交', '未交', '待批改', '待改进', '已完成'],
    ...students.map(student => [
      className, student.username, student.name,
      student.member_active ? '在班' : '已移出', student.active ? '正常' : '停用',
      student.expected, student.submitted, Math.max(0, student.expected - student.submitted),
      student.pending, student.needs_improvement, student.completed,
    ]),
  ]
  // BOM lets common Windows spreadsheet tools recognize Chinese UTF-8 text.
  return '\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n')
}

export function downloadCsv(content: string, filename: string): void {
  const link = document.createElement('a')
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8;' }))
  link.href = url
  link.download = filename
  link.hidden = true
  try {
    document.body.appendChild(link)
    link.click()
  } finally {
    link.remove()
    // Give the browser's download task time to consume the URL before revoking it.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
