<template>
  <div id="app">
    <el-menu mode="horizontal" router :default-active="activeRoute" class="nav-menu">
      <el-menu-item index="/">vid2note</el-menu-item>
      <el-menu-item index="/settings">设置</el-menu-item>
    </el-menu>
    <router-view />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeRoute = computed(() => {
  if (route.path.startsWith('/settings')) return '/settings'
  return '/'
})
</script>

<style>
#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.nav-menu {
  margin-bottom: 8px;
}
</style>
