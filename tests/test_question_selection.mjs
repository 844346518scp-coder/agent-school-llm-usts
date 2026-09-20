import assert from 'node:assert/strict'
import test from 'node:test'
import { courseChapters, chapterTitle, filterQuestions, appendQuestions, groupQuestions, assignmentTopic } from '../frontend/src/shared/courseChapters.ts'

const question = (id, topic, extra = {}) => ({ id, topic, title: `题目${id}`, content: `求解 $x+${id}=4$。`, reference_answer: 'PRIVATE_ANSWER', archived: false, ...extra })

test('chapter groups are numeric textbook order, with legacy names merged and custom chapters last', () => {
  const items = [question('12', '无穷级数'), question('custom', '期末复习'), question('10', '重积分'), question('2', '第 2 章 导数与微分'), question('1', '函数与极限'), question('2b', '第二章 导数与微分')]
  const before = structuredClone(items)
  const groups = groupQuestions(items)
  assert.deepEqual(groups.map(g => g.title), ['函数与极限', '导数与微分', '重积分', '无穷级数', '期末复习'])
  assert.deepEqual(groups[1].questions.map(q => q.id), ['2', '2b'])
  assert.equal(groups[2].label, '第 10 章 重积分')
  assert.deepEqual(groupQuestions(items, '题目10').map(g => g.title), ['重积分'])
  assert.deepEqual(groupQuestions(items, '无匹配'), [])
  assert.deepEqual(items, before)
})

test('assignment chapter is derived without a prerequisite selector and respects existing content', () => {
  const items = [question('2', '第二章 导数与微分')]
  assert.equal(assignmentTopic('', '综合练习', items), '导数与微分')
  assert.equal(assignmentTopic('原要求', '导数与微分', items), '导数与微分')
  assert.equal(assignmentTopic('旧题干', '函数与极限', items), '综合练习')
  assert.equal(assignmentTopic('', '', [...items, question('12', '无穷级数')]), '综合练习')
  assert.equal(assignmentTopic('', '', [question('x', '自定义练习')]), '自定义练习')
})

test('chapter filtering includes numbered legacy chapters and preserves custom topics', () => {
  const items = [question('1', '导数与微分'), question('2', '第二章 导数与微分'), question('3', '期末复习'), question('4', '无穷级数')]
  assert.deepEqual(filterQuestions(items, '导数与微分', '').map(q => q.id), ['1', '2'])
  assert.deepEqual(filterQuestions(items, '期末复习', '').map(q => q.id), ['3'])
  assert.equal(chapterTitle('第十二章 无穷级数'), '无穷级数')
  assert.equal(chapterTitle('自行设计的章节'), '自行设计的章节')
  assert.deepEqual(filterQuestions(items, '', '  题目4 ').map(q => q.id), ['4'])
  assert.equal(items[1].topic, '第二章 导数与微分')
})

test('upper and lower volumes have distinct integral and series categories', () => {
  assert.equal(courseChapters.length, 12)
  assert.deepEqual(courseChapters.filter(c => c.volume === '上册').map(c => c.number), [1, 2, 3, 4, 5, 6, 7])
  assert.deepEqual(courseChapters.filter(c => c.volume === '下册').map(c => c.number), [8, 9, 10, 11, 12])
  assert.ok(courseChapters.some(c => c.title === '定积分'))
  assert.ok(courseChapters.some(c => c.title === '定积分的应用'))
})

test('selection preserves existing instructions and cross-chapter order, never private answers', () => {
  const items = [question('12', '无穷级数'), question('2', '导数与微分')]
  const before = structuredClone(items)
  const result = appendQuestions('请写出过程。\n', items)
  assert.ok(result.startsWith('请写出过程。\n\n\n1. 题目12'))
  assert.ok(result.indexOf('1. 题目12') < result.indexOf('2. 题目2'))
  assert.ok(result.includes('$x+12=4$'))
  assert.ok(!result.includes('PRIVATE_ANSWER'))
  assert.deepEqual(items, before)
})

test('rejects obsolete, repeated and oversized choices without changing input', () => {
  const q = question('1', '函数与极限')
  assert.throws(() => appendQuestions('原内容', [q, q]), /不重复/)
  assert.throws(() => appendQuestions('原内容', [{ ...q, archived: true }]), /归档/)
  assert.throws(() => appendQuestions('原内容', []), /1–30/)
  assert.throws(() => appendQuestions('原内容', Array.from({ length: 31 }, (_, i) => question(String(i), '函数与极限'))), /1–30/)
  const existing = '字'.repeat(2999)
  assert.throws(() => appendQuestions(existing, [q]), /3000/)
  assert.equal(existing.length, 2999)
})
