<template>
  <div class="home">
    <el-container>
      <el-header>
        <h1>vid2note</h1>
        <p>视频链接 → Markdown 笔记 + 思维导图</p>
      </el-header>
      <el-main>
        <UrlInput />
        <TaskList />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import UrlInput from '../components/UrlInput.vue'
import TaskList from '../components/TaskList.vue'
</script>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}
</style>
