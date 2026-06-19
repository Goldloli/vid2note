<template>
  <nav class="tool-rail" aria-label="主工具">
    <RouterLink class="rail-brand" to="/workspace/import" aria-label="vid2note 工作台">V</RouterLink>
    <div class="rail-tools">
      <RouterLink to="/workspace/history" aria-label="知识库" title="知识库"><Collection /></RouterLink>
      <RouterLink to="/workspace/import" aria-label="导入视频" title="导入视频"><Upload /></RouterLink>
      <RouterLink to="/workspace/import?tool=media" aria-label="媒体工具" title="媒体工具"><VideoCamera /></RouterLink>
      <RouterLink to="/workspace/history?view=mindmap" aria-label="思维导图" title="思维导图"><Share /></RouterLink>
    </div>
    <RouterLink class="rail-settings" to="/workspace/settings" aria-label="设置" title="设置"><Setting /></RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { Collection, Setting, Share, Upload, VideoCamera } from '@element-plus/icons-vue'
</script>
