<script setup lang="ts">
import type { Submission } from './api'
import { reviewLabel, formatDate } from './api'
import MathText from './MathText.vue'
defineProps<{ submission: Submission }>()
</script>
<template>
  <section class="feedback-box" aria-label="教师反馈">
    <strong>{{ reviewLabel(submission.review?.status) }} · 第 {{ submission.version }} 版作答</strong>
    <template v-if="submission.review"><MathText :text="submission.review.comment"/><small class="muted">{{ formatDate(submission.review.reviewed_at) }}</small></template>
    <p v-else class="muted">当前版本尚未批改，请等待教师反馈。</p>
    <details v-if="submission.review_history.length"><summary>历史反馈（{{ submission.review_history.length }}）</summary><div v-for="r in submission.review_history" :key="r.id" class="history-feedback"><strong>第 {{ r.version }} 版 · {{ reviewLabel(r.status) }}（旧版结果）</strong><MathText :text="r.comment"/><small class="muted">{{ formatDate(r.reviewed_at) }} · 对应旧版作答</small><MathText :text="r.answer_snapshot"/></div></details>
  </section>
</template>
