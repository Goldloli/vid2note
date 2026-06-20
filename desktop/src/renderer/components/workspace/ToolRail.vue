<template>
  <nav class="tool-rail" aria-label="主工具">
    <RouterLink class="rail-brand" to="/workspace/wiki" aria-label="vid2note 工作台">V</RouterLink>
    <div class="rail-tools">
      <RouterLink to="/workspace/wiki" aria-label="知识库" title="知识库"><Collection /></RouterLink>
      <RouterLink to="/workspace/import" aria-label="导入视频" title="导入视频"><Upload /></RouterLink>
      <RouterLink to="/workspace/media" aria-label="媒体工具" title="媒体工具"><VideoCamera /></RouterLink>
      <RouterLink to="/workspace/changesets" aria-label="变更审批" title="变更审批"><Finished /></RouterLink>
      <RouterLink to="/workspace/agent" aria-label="Agent 会话" title="Agent 会话"><ChatDotRound /></RouterLink>
      <RouterLink to="/workspace/health" aria-label="Wiki 健康" title="Wiki 健康"><FirstAidKit /></RouterLink>
    </div>
    <RouterLink class="rail-settings" to="/workspace/settings" aria-label="设置" title="设置"><Setting /></RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { ChatDotRound, Collection, Finished, FirstAidKit, Setting, Upload, VideoCamera } from '@element-plus/icons-vue'
</script>
