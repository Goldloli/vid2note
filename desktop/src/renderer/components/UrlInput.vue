<template>
  <div class="url-input">
    <el-input
      v-model="url"
      placeholder="输入视频链接（YouTube、Bilibili、直链等）"
      size="large"
      clearable
    >
      <template #append>
        <el-button type="primary" @click="submit">开始</el-button>
      </template>
    </el-input>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const url = ref('')

const submit = () => {
  console.log('提交 URL:', url.value)
}
</script>

<style scoped>
.url-input {
  margin-bottom: 20px;
}
</style>
