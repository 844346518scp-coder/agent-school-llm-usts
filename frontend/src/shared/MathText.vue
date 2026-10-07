<script setup lang="ts">
import { computed } from 'vue'
import katex from 'katex'
import { renderMarkdown } from './markdown'
const props = defineProps<{ text: string }>()
const html = computed(() => renderMarkdown(props.text, (tex, displayMode) =>
  katex.renderToString(tex, { throwOnError: false, trust: false, displayMode, maxExpand: 200 })))
</script>
<template><div class="math-text" v-html="html"></div></template>

<style scoped>
/* Markdown 片段（渲染在 .math-text 内）的类型样式，使用项目既有变量以适配主题 */
.math-text :deep(p) { margin: 0 0 9px; }
.math-text :deep(p:last-child) { margin-bottom: 0; }
.math-text :deep(h3),
.math-text :deep(h4),
.math-text :deep(h5),
.math-text :deep(h6) { margin: 15px 0 7px; font-size: 14px; line-height: 1.4; }
.math-text :deep(ul),
.math-text :deep(ol) { margin: 7px 0 10px; padding-left: 21px; }
.math-text :deep(li) { margin: 3px 0; }
.math-text :deep(code) { font-family: Consolas, "Courier New", monospace; font-size: .91em; background: var(--soft); color: var(--primary); padding: 1px 5px; border-radius: 5px; }
.math-text :deep(pre) { margin: 9px 0; padding: 11px 13px; overflow-x: auto; background: var(--soft); border: 1px solid var(--line); border-radius: 9px; }
.math-text :deep(pre code) { background: none; color: inherit; padding: 0; font-size: .88em; }
.math-text :deep(blockquote) { margin: 9px 0; padding: 5px 0 5px 12px; border-left: 3px solid var(--primary); color: var(--muted); }
.math-text :deep(hr) { margin: 14px 0; border: 0; border-top: 1px solid var(--line); }
.math-text :deep(strong) { font-weight: 650; }
.math-text :deep(.markdown-table) { overflow-x: auto; margin: 10px 0; }
.math-text :deep(table) { border-collapse: collapse; width: 100%; }
.math-text :deep(th), .math-text :deep(td) { padding: 7px 10px; border: 1px solid var(--line); text-align: left; }
.math-text :deep(th) { background: var(--soft); }
</style>
