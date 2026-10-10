// A 端接入 B 模块第三/四阶段能力的纯逻辑测试（原生 Node，无新依赖）。
// Run: .runtime/node-v22.23.2-win-x64/node.exe --experimental-strip-types --test tests/test_agent_tools.mjs
//
// 覆盖范围：与后端契约相关的长度/取值上限、分层提示的层级推进、主题下拉的取舍、
// 图形批注的坐标映射与断线、语音的格式与体积自检、纠错条目的展示、浏览器原生语音的容错读取。
// 这些函数是「提前拦截 + 如实说明」的实现，测试同时锁住它们与 docs/contracts/README.md 的一致性。
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AUDIO_MIN_BYTES,
  HINT_QUESTION_MAX,
  PLOT_SAMPLES_MAX,
  audioBase64Bytes,
  axisTicks,
  checkAudioClip,
  checkPlotParams,
  clampForHint,
  createProjection,
  decideTopic,
  describeCorrections,
  describeSpeechError,
  formatBytes,
  formatTick,
  nextHintLevel,
  normalizeAudioMediaType,
  readSpeechError,
  readSpeechTranscript,
  toPolylineSegments,
} from '../frontend/src/shared/agentTools.ts'

const STUDENT_TOPICS = ['函数与极限', '导数与微分', '费曼练习']

test('clampForHint truncates and reports the truncation instead of cutting silently', () => {
  assert.deepEqual(clampForHint('  求极限  '), { text: '求极限', truncated: false })
  const clamped = clampForHint('x'.repeat(HINT_QUESTION_MAX + 200))
  assert.equal(clamped.text.length, HINT_QUESTION_MAX)
  assert.equal(clamped.truncated, true)
})

test('nextHintLevel only accepts an increasing level reported by the backend', () => {
  assert.equal(nextHintLevel(1, 2), 2)
  assert.equal(nextHintLevel(2, 3), 3)
  assert.equal(nextHintLevel(1, 1), null)
  assert.equal(nextHintLevel(1, 3), 3)
  assert.equal(nextHintLevel(1, 4), null)
  assert.equal(nextHintLevel(1, 0), null)
  assert.equal(nextHintLevel(3, null), null)
  assert.equal(nextHintLevel(1, undefined), null)
  assert.equal(nextHintLevel(1, Number.NaN), null)
})

test('decideTopic never writes a topic the select cannot display', () => {
  assert.deepEqual(decideTopic('student', '导数与微分', '', STUDENT_TOPICS),
    { topic: '导数与微分', applied: true, suggested: '导数与微分' })

  // 课程知识点的主题名（极限与连续 / 一元函数积分学 / 无穷级数）不在对话页下拉里 ——
  // 必须保留原主题并回传建议值，不能写进 v-model 让下拉变空白。
  const outside = decideTopic('student', '极限与连续', '', STUDENT_TOPICS)
  assert.equal(outside.topic, '')
  assert.equal(outside.applied, false)
  assert.equal(outside.suggested, '极限与连续')

  // 没有后端建议时退回关键词推断；教师端不猜主题。
  assert.equal(decideTopic('student', null, '用定义求导数', STUDENT_TOPICS).topic, '导数与微分')
  const teacher = decideTopic('teacher', null, '用定义求导数', ['导数与微分'])
  assert.equal(teacher.applied, false)
  assert.equal(teacher.suggested, '')
})

test('checkPlotParams blocks exactly what the backend would reject', () => {
  assert.equal(checkPlotParams(-6, 6, 49), '')
  assert.match(checkPlotParams(6, 6, 49), /左端点/)
  assert.match(checkPlotParams(6, -6, 49), /左端点/)
  assert.match(checkPlotParams(-6, 6, 1), /采样点数/)
  assert.match(checkPlotParams(-6, 6, PLOT_SAMPLES_MAX + 1), /采样点数/)
  assert.match(checkPlotParams(-2e4, 6, 49), /以内/)
  assert.match(checkPlotParams(Number.NaN, 6, 49), /数字/)
})

test('projection maps the viewport and flips the y axis', () => {
  const plain = { top: 0, right: 0, bottom: 0, left: 0 }
  const projection = createProjection({ x_min: -1, x_max: 1, y_min: -1, y_max: 1 }, 100, 100, plain)
  assert.equal(Math.round(projection.x(-1)), 0)
  assert.equal(Math.round(projection.x(1)), 100)
  assert.equal(Math.round(projection.y(1)), 0)   // 数学上的最大值画在画布顶部
  assert.equal(Math.round(projection.y(-1)), 100)

  // 视窗退化（span 为 0）时不能出现 Infinity/NaN 坐标。
  const degenerate = createProjection({ x_min: 1, x_max: 1, y_min: 1, y_max: 1 }, 100, 100)
  assert.ok(Number.isFinite(degenerate.x(1)))
  assert.ok(Number.isFinite(degenerate.y(1)))
})

test('polyline breaks at samples without a value', () => {
  const identity = { x: value => value, y: value => value }
  const segments = toPolylineSegments([[0, 0], [1, null], [2, 2], ['x', 3]], identity)
  assert.deepEqual(segments, [[[0, 0]], [[2, 2]]])
  assert.deepEqual(toPolylineSegments([], identity), [])
  assert.deepEqual(toPolylineSegments([[1, null]], identity), [])
})

test('axis ticks and labels stay readable', () => {
  assert.deepEqual(axisTicks(0, 4, 4), [0, 1, 2, 3, 4])
  assert.deepEqual(axisTicks(4, 4), [])
  assert.equal(formatTick(0), '0')
  assert.equal(formatTick(-0.0000001), '0')
  assert.equal(formatTick(1.239), '1.24')
  assert.equal(formatTick(Number.NaN), '')
})

test('audio helpers mirror the backend limits', () => {
  assert.equal(normalizeAudioMediaType('audio/webm;codecs=opus'), 'audio/webm')
  assert.equal(normalizeAudioMediaType('AUDIO/MP3'), 'audio/mp3')
  assert.equal(normalizeAudioMediaType('audio/flac'), null)
  assert.equal(normalizeAudioMediaType(null), null)

  const short = Buffer.alloc(100).toString('base64')
  assert.equal(audioBase64Bytes(short), 100)
  assert.equal(audioBase64Bytes(''), 0)
  assert.equal(checkAudioClip(short, 'audio/webm', 3).ok, false)
  assert.match(checkAudioClip(short, 'audio/webm', 3).reason, /重新录/)

  const usable = Buffer.alloc(AUDIO_MIN_BYTES + 8).toString('base64')
  assert.equal(checkAudioClip(usable, 'audio/webm', 30).ok, true)
  assert.match(checkAudioClip(usable, null, 30).reason, /不在后端支持范围内/)
  assert.match(checkAudioClip(usable, 'audio/webm', 300).reason, /120 秒/)
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(1536), '1.5 KB')
})

test('describeCorrections shows what the speech layer changed', () => {
  assert.equal(describeCorrections([{ from: '平方', to: '^2', count: 2 }, { from: '趋于', to: '→', count: 1 }]),
    '平方 → ^2（2 次）；趋于 → →')
  assert.equal(describeCorrections([]), '')
  assert.equal(describeCorrections(null), '')
  assert.equal(describeCorrections([{ from: '', to: '' }]), '')
})

test('browser speech readers tolerate unknown structures', () => {
  assert.deepEqual(readSpeechTranscript(null), { final: '', interim: '' })
  const event = {
    results: [
      Object.assign([{ transcript: 'sin x ' }], { isFinal: true }),
      Object.assign([{ transcript: 'div' }], { isFinal: false }),
    ],
  }
  assert.deepEqual(readSpeechTranscript(event), { final: 'sin x', interim: 'div' })
  assert.equal(readSpeechError({ error: 'no-speech' }), 'no-speech')
  assert.equal(readSpeechError(null), '')
  assert.match(describeSpeechError('no-speech').title, /没有听到/)
  assert.match(describeSpeechError('not-allowed').detail, /麦克风/)
  assert.equal(describeSpeechError('mystery').title, '语音识别失败')
})
