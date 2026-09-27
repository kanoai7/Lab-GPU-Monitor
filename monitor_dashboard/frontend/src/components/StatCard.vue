<template>
  <div class="statcard" :class="level">
    <span class="sc-k">{{ k }}</span>
    <span class="sc-v">{{ v }}</span>
    <span v-if="sub" class="sc-sub">{{ sub }}</span>
  </div>
</template>

<script setup>
defineProps({
  k: { type: String, default: '' },      // 标签 / label
  v: { type: [String, Number], default: '—' },
  sub: { type: String, default: '' },
  level: { type: String, default: '' },  // '' | ok | warn | crit
})
</script>
