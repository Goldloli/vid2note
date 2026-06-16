<template>
  <div class="url-input">
    <el-input
      v-model="url"
      placeholder="输入视频链接（YouTube、Bilibili、直链等）"
      size="large"
      clearable
      :disabled="store.isCreating"
      @keyup.enter="submit"
    >
      <template #append>
        <el-button type="primary" :loading="store.isCreating" @click="submit">开始</el-button>
      </template>
    </el-input>
    <p v-if="store.error" class="error">{{ store.error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useTaskStore } from '../stores/task'

const url = ref('')
const store = useTaskStore()

const submit = async () => {
  if (!url.value.trim()) return
  if (!url.value.startsWith('http://') && !url.value.startsWith('https://')) {
    store.error = '请输入有效的 URL（以 http:// 或 https:// 开头）'
    return
  }
  store.error = ''
  await store.addTask(url.value.trim())
  url.value = ''
}
</script>

<style scoped>
.url-input {
  margin-bottom: 20px;
}
.error {
  color: #f56c6c;
  font-size: 14px;
  margin-top: 8px;
}
</style>
