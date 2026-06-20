<template><section class="contradiction-panel"><h3>矛盾：{{ contradiction.topic }}</h3><div class="diff-columns"><blockquote>{{ contradiction.claim_a }}</blockquote><blockquote>{{ contradiction.claim_b }}</blockquote></div><fieldset><legend>处理方式</legend><label><input v-model="choice" type="radio" value="keep">同时保留</label><label><input v-model="choice" type="radio" value="revise">要求修订</label><label><input v-model="choice" type="radio" value="reject">拒绝该块</label></fieldset><button data-testid="confirm-contradiction" type="button" @click="confirm">确认</button><p v-if="prompt" role="alert">请选择处理方式</p></section></template>
<script setup lang="ts">
import { ref } from 'vue'
type Contradiction = { topic: string; claim_a: string; claim_b: string }
defineProps<{ contradiction: Contradiction }>(); const emit = defineEmits<{ choose: [choice: string] }>(); const choice = ref(''); const prompt = ref(false)
function confirm(): void { prompt.value = !choice.value; if (choice.value) emit('choose', choice.value) }
</script>
