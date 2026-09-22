/** 主题（浅色 / 深色 / 跟随系统）状态与持久化。
 *
 * 深色通过 <html class="dark"> 生效：它同时驱动 Element Plus 的深色变量与
 * 自动生成的 shared/dark-theme.css（见 build-dark-theme.py）。
 * 首屏防闪烁逻辑在 index.html 的内联脚本里，必须在 Vue 启动前执行。
 */
import { computed, ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'shuban-theme'
const MODES: ThemeMode[] = ['light', 'dark', 'system']

function readStored(): ThemeMode {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return MODES.includes(value as ThemeMode) ? (value as ThemeMode) : 'system'
  } catch {
    return 'system'
  }
}

function systemQuery(): MediaQueryList | null {
  return typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
}

export const mode = ref<ThemeMode>(readStored())
export const prefersDark = ref(systemQuery()?.matches ?? false)
export const isDark = computed(() => mode.value === 'dark' || (mode.value === 'system' && prefersDark.value))

export function applyTheme(): void {
  document.documentElement.classList.toggle('dark', isDark.value)
  document.documentElement.style.colorScheme = isDark.value ? 'dark' : 'light'
}

export function setMode(value: ThemeMode): void {
  mode.value = value
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* 隐私模式下无法持久化，仅本次会话生效 */
  }
}

/** 浅色 → 深色 → 跟随系统 循环切换。 */
export function cycleMode(): void {
  const index = MODES.indexOf(mode.value)
  setMode(MODES[(index + 1) % MODES.length])
}

export function modeLabel(value: ThemeMode = mode.value): string {
  return value === 'light' ? '浅色模式' : value === 'dark' ? '深色模式' : '跟随系统'
}

export function initTheme(): void {
  const query = systemQuery()
  query?.addEventListener('change', event => {
    prefersDark.value = event.matches
  })
  watch([mode, prefersDark], applyTheme, { immediate: true })
}
