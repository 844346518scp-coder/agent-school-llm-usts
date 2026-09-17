<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { init, use, type EChartsType } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
const props = defineProps<{ dates: string[]; green?: boolean }>()
const el = ref<HTMLDivElement>()
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined
function draw() {
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() - 6 + i); return d })
  const values = days.map(d => props.dates.filter(s => new Date(s).toDateString() === d.toDateString()).length)
  const color = props.green ? '#43877a' : '#8b75ce'
  chart?.setOption({ grid: { left: 24, right: 10, top: 20, bottom: 25 }, tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${v} 次提问` }, xAxis: { type: 'category', boundaryGap: false, data: days.map(d => `${d.getMonth() + 1}/${d.getDate()}`), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#9b96a7', fontSize: 10 } }, yAxis: { type: 'value', minInterval: 1, max: Math.max(4, ...values), splitLine: { lineStyle: { color: '#f0eef4', type: 'dashed' } }, axisLabel: { color: '#aaa3b4', fontSize: 10 } }, series: [{ type: 'line', data: values, smooth: true, symbolSize: 6, itemStyle: { color }, lineStyle: { width: 2.5, color }, areaStyle: { color, opacity: .09 } }] })
}
onMounted(() => { chart = init(el.value!); draw(); observer = new ResizeObserver(() => chart?.resize()); observer.observe(el.value!) })
watch(() => props.dates, draw, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<template><div ref="el" class="activity-chart" role="img" aria-label="近七天实际提问次数折线图"></div></template>
