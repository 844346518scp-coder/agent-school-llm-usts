import test from 'node:test'
import assert from 'node:assert/strict'
import { renderMarkdown, escapeHtml } from '../frontend/src/shared/markdown.ts'
const math = (value, display) => `<span class="${display ? 'display' : 'inline'}">${escapeHtml(value)}</span>`

test('formulas preserve list numbering and inline layout', () => {
  const html = renderMarkdown('1. 求 $x^2$ 的导数。\n2. 得到 $2x$。\n3. 代入 $x=2$。', math)
  assert.equal((html.match(/<ol /g) || []).length, 1)
  assert.match(html, /<li value="2">得到 <span class="inline">2x<\/span>。<\/li>/)
  assert.match(renderMarkdown('3. 独立编号'), /start="3"/)
})
test('both latex delimiter families render; code is literal', () => {
  const html = renderMarkdown('\\(x^2\\)\n\\[x=2\\]\n`$not_math$ **literal**`\n```python\n<x> $x$\n```', math)
  assert.match(html, /class="inline">x\^2/)
  assert.match(html, /class="display">x=2/)
  assert.match(html, /<code>\$not_math\$ \*\*literal\*\*<\/code>/)
  assert.match(html, /&lt;x&gt; \$x\$/)
})
test('headings emphasis quote and unsafe html', () => {
  const html = renderMarkdown('## 结论\n**重点**\n> 引用\n<img src=x onerror=alert(1)>\n\uE0000\uE001')
  assert.match(html, /<h4>结论<\/h4>/)
  assert.match(html, /<strong>重点<\/strong>/)
  assert.match(html, /<blockquote>引用<\/blockquote>/)
  assert.ok(!html.includes('<img'))
  assert.ok(!html.includes('undefined'))
})
test('tables keep formula cells and escape HTML', () => {
  const html = renderMarkdown('| 函数 | 导数 |\n| --- | --- |\n| $x^2$ | $2x$ |\n| <script> | 0 |', math)
  assert.match(html, /<table>/)
  assert.match(html, /<td><span class="inline">2x<\/span><\/td>/)
  assert.ok(!html.includes('<script>'))
})
