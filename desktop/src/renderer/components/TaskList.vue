<template>
  <div class="task-list">
    <el-card>
      <template #header>
        <span>任务列表</span>
      </template>
      <el-empty description="暂无任务" />
    </el-card>
  </div>
</template>

<script setup>
</script>

<style scoped>
.task-list {
  margin-top: 20px;
}
</style>
