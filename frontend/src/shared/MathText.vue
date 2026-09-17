<script setup lang="ts">
import { computed } from 'vue'
import katex from 'katex'
const props = defineProps<{ text: string }>()
const parts = computed(() => props.text.split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g).map(part => {
  if (part.startsWith('$')) {
    const display = part.startsWith('$$')
    return { math: true, html: katex.renderToString(part.slice(display ? 2 : 1, display ? -2 : -1), { throwOnError: false, trust: false, displayMode: display, maxExpand: 200 }) }
  }
  return { math: false, text: part }
}))
</script>
<template><div class="math-text"><template v-for="(part, i) in parts" :key="i"><span v-if="part.math" v-html="part.html"></span><span v-else>{{ part.text }}</span></template></div></template>
