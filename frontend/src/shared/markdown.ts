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
 * 行内公式已经在本模块之外拆走，所以这里不必考虑 `$`。
 */
export function renderMarkdown(raw: string): string {
  const lines = escapeHtml(raw).split('\n')
  const out: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let inCodeBlock = false

  const closeList = () => {
    if (listType) {
      out.push(listType === 'ul' ? '</ul>' : '</ol>')
      listType = null
    }
  }

  for (const line of lines) {
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

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') {
        closeList()
        out.push('<ol>')
        listType = 'ol'
      }
      out.push(`<li>${inlineMarkdown(ordered[1])}</li>`)
      continue
    }

    closeList()
    out.push(`<p>${inlineMarkdown(trimmed)}</p>`)
  }

  if (inCodeBlock) out.push('</code></pre>')
  closeList()
  return out.join('')
}
