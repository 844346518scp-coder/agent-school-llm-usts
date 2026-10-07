/**
 * 轻量 Markdown 渲染（会议「Markdown 兼容」条目）。
 *
 * 背景：Agent 的输出直接走 `{{ }}` 纯文本插值，模型返回的 `**重点**`、`- 列表`、
 * `` `代码` `` 会原样带上星号和反引号显示，看起来像乱码。
 *
 * 为什么不引第三方库：项目坚持不新增依赖，而教学场景实际只用到一个很小的子集，
 * 因此这里手写实现：标题、有序/无序列表、引用、分隔线、代码块，以及行内
 * 代码 / 粗体 / 斜体。
 *
 * 安全：输出会被 v-html 插入，所以**先转义 HTML** 再做替换，模型输出无法注入标签。
 */

const HTML_ESCAPES: Array<[RegExp, string]> = [
  [/&/g, '&amp;'],
  [/</g, '&lt;'],
  [/>/g, '&gt;'],
  [/"/g, '&quot;']
]

export function escapeHtml(value: string): string {
  return HTML_ESCAPES.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value)
}

/** 行内语法：代码 → 粗体 → 斜体。输入必须已经过 escapeHtml。 */
export function inlineMarkdown(value: string): string {
  return value
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/(^|[^\w_])_([^_\n]+)_(?![\w_])/g, '$1<em>$2</em>')
}

/**
 * 把一段纯文本转成安全的 HTML。
 * 公式与代码先保护成不可执行占位符，再统一解析块结构。
 */
export function renderMarkdown(raw: string, math?: (tex: string, display: boolean) => string): string {
  // Preserve code/formulas while parsing the whole document: formulas must not
  // split ordered lists or become Markdown emphasis.
  const tokens: string[] = []
  const token = (html: string) => { tokens.push(html); return `\uE000${tokens.length - 1}\uE001` }
  const protectedText = raw.replace(/[\uE000\uE001]/g, '').replace(
    /```[^\n]*\n[\s\S]*?(?:```|$)|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$/g,
    value => {
      if (value.startsWith('```')) return '\n' + token(`<pre><code>${escapeHtml(value.replace(/^```[^\n]*\n/, '').replace(/```$/, ''))}</code></pre>`) + '\n'
      if (value.startsWith('`')) return token(`<code>${escapeHtml(value.slice(1, -1))}</code>`)
      const display = value.startsWith('$$') || value.startsWith('\\[')
      const width = value.startsWith('\\') || display ? 2 : 1
      return token(math ? math(value.slice(width, -width), display) : escapeHtml(value))
    })
  const lines = escapeHtml(protectedText).split('\n')
  const out: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let inCodeBlock = false

  const closeList = () => {
    if (listType) {
      out.push(listType === 'ul' ? '</ul>' : '</ol>')
      listType = null
    }
  }

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]
    if (/^\s*```/.test(line)) {
      closeList()
      out.push(inCodeBlock ? '</code></pre>' : '<pre><code>')
      inCodeBlock = !inCodeBlock
      continue
    }

    if (inCodeBlock) {
      out.push(line + '\n')
      continue
    }

    const trimmed = line.trim()
    if (!trimmed) {
      closeList()
      continue
    }

    if (/^\uE000\d+\uE001$/.test(trimmed) && tokens[Number(trimmed.slice(1, -1))]?.startsWith('<pre>')) {
      closeList(); out.push(trimmed); continue
    }

    const cells = (row: string) => row.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim())
    if (trimmed.includes('|') && index + 1 < lines.length && cells(lines[index + 1]).every(cell => /^:?-{3,}:?$/.test(cell))) {
      closeList()
      out.push('<div class="markdown-table"><table><thead><tr>' + cells(trimmed).map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('') + '</tr></thead><tbody>')
      index += 2
      while (index < lines.length && lines[index].trim().includes('|')) {
        out.push('<tr>' + cells(lines[index]).map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('') + '</tr>')
        index++
      }
      index--
      out.push('</tbody></table></div>')
      continue
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = Math.min(heading[1].length + 2, 6)
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    if (/^([-*_])\1{2,}$/.test(trimmed)) {
      closeList()
      out.push('<hr />')
      continue
    }

    // 注意：此前已 escapeHtml，> 会变成 &gt;，所以两种写法都要认
    const quote = trimmed.match(/^(?:&gt;|>)\s?(.*)$/)
    if (quote) {
      closeList()
      out.push(`<blockquote>${inlineMarkdown(quote[1])}</blockquote>`)
      continue
    }

    const unordered = trimmed.match(/^[-*+]\s+(.+)$/)
    if (unordered) {
      if (listType !== 'ul') {
        closeList()
        out.push('<ul>')
        listType = 'ul'
      }
      out.push(`<li>${inlineMarkdown(unordered[1])}</li>`)
      continue
    }

    const ordered = trimmed.match(/^(\d+)[.)]\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') {
        closeList()
        out.push(`<ol start="${Number(ordered[1])}">`)
        listType = 'ol'
      }
      out.push(`<li value="${Number(ordered[1])}">${inlineMarkdown(ordered[2])}</li>`)
      continue
    }

    closeList()
    out.push(`<p>${inlineMarkdown(trimmed)}</p>`)
  }

  if (inCodeBlock) out.push('</code></pre>')
  closeList()
  return out.join('').replace(/\uE000(\d+)\uE001/g, (_, index) => tokens[Number(index)] ?? '')
}
