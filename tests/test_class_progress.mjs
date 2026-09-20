// Pure Node regression: no browser, database, network, or extra dependencies.
// Run: .runtime/node-v22.23.2-win-x64/node.exe --experimental-strip-types --test tests/test_class_progress.mjs
import assert from 'node:assert/strict'
import test from 'node:test'
import { classProgressCsv, downloadCsv, filterClassStudents, memberBatchTargets, runMemberBatch } from '../frontend/src/shared/classProgress.ts'

test('bulk membership affects only selected visible members with a different membership state', () => {
  const roster = [student({ id: 'one', manageable: false }), student({ id: 'two', member_active: false }), student({ id: 'three', active: false })]
  assert.deepEqual(memberBatchTargets(roster, ['one', 'two', 'hidden', 'one'], false).map(s => s.id), ['one'])
  assert.deepEqual(memberBatchTargets(roster, ['one', 'two'], true).map(s => s.id), ['two'])
  assert.deepEqual(memberBatchTargets(roster, ['three'], false).map(s => s.id), ['three'])
  assert.deepEqual(memberBatchTargets(roster, [], false), [])
})

test('bulk execution stops on first uncertain result without retrying or touching later members', async () => {
  const targets = ['one', 'two', 'three'].map(id => student({ id }))
  const calls = []
  const result = await runMemberBatch(targets, async s => { calls.push(s.id); if (s.id === 'two') throw new Error('超时') })
  assert.deepEqual(calls, ['one', 'two'])
  assert.deepEqual(result.completed, ['one'])
  assert.equal(result.failed.id, 'two')
  assert.equal(result.error, '超时')
  assert.equal(result.unprocessed, 1)
  const success = await runMemberBatch(targets, async () => {})
  assert.deepEqual(success.completed, ['one', 'two', 'three'])
  assert.equal(success.failed, null)
})

function student(overrides = {}) {
  return {
    id: 'synthetic-1', username: 'learner.one', name: '合成学生', active: true,
    must_change_password: false, member_active: true, manageable: true,
    expected: 7, submitted: 4, pending: 2, needs_improvement: 1, completed: 1,
    ...overrides,
  }
}

// Independent CSV reader: verifies round trips rather than repeating the writer.
function readCsv(text) {
  assert.equal(text.codePointAt(0), 0xfeff)
  const rows = [], row = []
  let value = '', quoted = false
  for (let index = 1; index < text.length; index++) {
    const character = text[index]
    if (character === '"') {
      if (quoted && text[index + 1] === '"') { value += '"'; index++ }
      else quoted = !quoted
    } else if (character === ',' && !quoted) {
      row.push(value); value = ''
    } else if ((character === '\r' || character === '\n') && !quoted) {
      if (character === '\r' && text[index + 1] === '\n') index++
      row.push(value); rows.push([...row]); row.length = 0; value = ''
    } else value += character
  }
  assert.equal(quoted, false, 'all quoted cells must close')
  row.push(value); rows.push(row)
  return rows
}

test('exports only the current search and membership filter, without mutating the roster', () => {
  const roster = [
    student({ id: 'one', username: 'Lin.A', name: '林甲' }),
    student({ id: 'two', username: 'Lin.B', name: '林乙', member_active: false }),
    student({ id: 'three', username: 'Zhou.C', name: '周丙', active: false }),
  ]
  const original = structuredClone(roster)
  const selected = filterClassStudents(roster, '  LIN.a  ', 'active')
  assert.deepEqual(selected.map(item => item.id), ['one'])
  assert.deepEqual(filterClassStudents(roster, '林', 'removed').map(item => item.id), ['two'])
  assert.deepEqual(filterClassStudents(roster, '  ', 'active').map(item => item.id), ['one', 'three'])
  assert.equal(filterClassStudents(roster, '', 'all').length, 3)
  assert.deepEqual(filterClassStudents(roster, '不存在', 'all'), [])
  const rows = readCsv(classProgressCsv('合成教学班', selected))
  assert.equal(rows.length, 2)
  assert.deepEqual(rows[1], ['合成教学班', 'Lin.A', '林甲', '在班', '正常', '7', '4', '3', '2', '1', '1'])
  assert.deepEqual(roster, original)
})

test('UTF-8 BOM and CSV quoting preserve Chinese, commas, quotes and multiline text', () => {
  const names = ['班级,中文', '班级"引用"', '班级\n第二行', '班级\r\n第二行', '班级, "复合"\r\n末行']
  for (const name of names) {
    const content = classProgressCsv(name, [student({ name })])
    const bytes = Buffer.from(content, 'utf8')
    assert.deepEqual([...bytes.subarray(0, 3)], [0xef, 0xbb, 0xbf])
    const rows = readCsv(bytes.toString('utf8'))
    assert.equal(rows.length, 2)
    assert.equal(rows[0].length, 11)
    assert.equal(rows[1].length, 11)
    assert.equal(rows[1][0], name)
    assert.equal(rows[1][2], name)
  }
})

test('neutralizes spreadsheet formula starts and leading whitespace in every free-text field', () => {
  const payloads = ['=1+1', '+1+1', '-1+1', '@SUM(1,2)', '  =1+1', '\u3000+1+1', '\t=1+1', '\r=1+1', '\n=1+1', ' \t姓名', '\r姓名', '\n姓名', '\u0000=1+1']
  for (const payload of payloads) {
    const row = readCsv(classProgressCsv(payload, [student({ username: payload, name: payload })]))[1]
    for (const column of [0, 1, 2]) assert.equal(row[column], "'" + payload)
  }
})

test('ordinary text remains unchanged; status and progress reflect supplied data', () => {
  for (const name of ['0', '普通姓名', '  普通姓名', 'abc=123', "'已是文本", '班级-甲', '章\t节']) {
    const row = readCsv(classProgressCsv(name, [student({ name, member_active: false, active: false, expected: 0, submitted: 0, pending: 0, needs_improvement: 0, completed: 0 })]))[1]
    assert.equal(row[0], name)
    assert.equal(row[2], name)
    assert.deepEqual(row.slice(3), ['已移出', '停用', '0', '0', '0', '0', '0', '0'])
  }
  assert.equal(readCsv(classProgressCsv('空班级', [])).length, 1)
})

async function checkDownloadLifecycle(failClick) {
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL, originalTimeout = globalThis.setTimeout
  const events = []
  let blob, callback
  const link = {
    href: '', download: '', hidden: false, connected: false,
    click() { assert.equal(this.connected, true, 'download link is attached before click'); events.push('click'); if (failClick) throw new Error('synthetic click failure') },
    remove() { events.push('remove'); this.connected = false },
  }
  Object.defineProperty(globalThis, 'document', { configurable: true, value: {
    createElement(tag) { assert.equal(tag, 'a'); return link },
    body: { appendChild(element) { assert.equal(element, link); element.connected = true; events.push('append') } },
  } })
  URL.createObjectURL = value => { blob = value; events.push('create-url'); return 'blob:synthetic-csv' }
  URL.revokeObjectURL = url => { assert.equal(url, 'blob:synthetic-csv'); events.push('revoke') }
  globalThis.setTimeout = (fn, delay) => { assert.ok(delay >= 1000); callback = fn; events.push('schedule'); return 1 }
  try {
    const content = classProgressCsv('合成下载班', [student()])
    if (failClick) assert.throws(() => downloadCsv(content, '进度.csv'), /synthetic click failure/)
    else downloadCsv(content, '进度.csv')
    assert.deepEqual(events, ['create-url', 'append', 'click', 'remove', 'schedule'])
    assert.equal(link.href, 'blob:synthetic-csv')
    assert.equal(link.download, '进度.csv')
    assert.equal(link.hidden, true)
    assert.equal(blob.type, 'text/csv;charset=utf-8;')
    assert.deepEqual(Buffer.from(await blob.arrayBuffer()), Buffer.from(content, 'utf8'))
    assert.equal(link.connected, false)
    callback()
    assert.equal(events.at(-1), 'revoke')
  } finally {
    if (previousDocument) Object.defineProperty(globalThis, 'document', previousDocument)
    else delete globalThis.document
    URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; globalThis.setTimeout = originalTimeout
  }
}

test('download attaches the link, clicks, removes it and releases the URL only after a delay', () => checkDownloadLifecycle(false))
test('failed click still removes the link and schedules object URL cleanup', () => checkDownloadLifecycle(true))
