<script setup lang="ts">
import { computed } from 'vue'
import { Monitor, Moon, Sun } from 'lucide-vue-next'
import { cycleMode, isDark, mode, modeLabel } from './theme'

const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const icon = computed(() => (mode.value === 'light' ? Sun : mode.value === 'dark' ? Moon : Monitor))
const hint = computed(() => `当前：${modeLabel()}${isDark.value ? '（深色）' : '（浅色）'}，点击切换`)
</script>

<template>
  <button
    class="theme-toggle"
    :class="{ 'is-compact': props.compact }"
    type="button"
    :title="hint"
    :aria-label="`切换主题，${hint}`"
    @click="cycleMode()"
  >
    <component :is="icon" :size="16" />
    <span v-if="!props.compact" class="theme-toggle-label">{{ modeLabel() }}</span>
  </button>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 11px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--surface, #fff);
  color: var(--muted);
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
  transition: color .18s, border-color .18s, background .18s;
}
.theme-toggle:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.theme-toggle:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
.theme-toggle.is-compact {
  padding: 7px;
  gap: 0;
}
.theme-toggle-label {
  font-size: 12px;
}
@media (max-width: 760px) {
  .theme-toggle-label { display: none; }
  .theme-toggle { padding: 7px; }
}
</style>
