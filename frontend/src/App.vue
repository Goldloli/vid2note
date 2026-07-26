<template>
  <div class="app">
    <div class="titlebar">
      <div class="tb-title">{{ $t('nav.brand') }}</div>
      <div class="tb-spacer"></div>
      <span class="tb-pill"><span class="dot-live"></span>{{ $t('nav.local') }}</span>
      <button class="btn btn-ghost btn-sm" @click="config.toggleTheme()" :title="$t('nav.themeTip')">◐</button>
    </div>
    <div class="body">
      <aside class="sidebar">
        <div class="brand"><div class="mark">V</div><div><div class="name">vid2note</div><div class="ver">v1.2 · mac</div></div></div>
        <div class="nav-label">{{ $t('nav.label') }}</div>
        <router-link class="nav-item" to="/" exact-active-class="active">{{ $t('nav.console') }}</router-link>
        <router-link class="nav-item" to="/notes" active-class="active">{{ $t('nav.note') }}</router-link>
        <router-link class="nav-item" to="/mindmaps" active-class="active">{{ $t('nav.mindmap') }}</router-link>
        <router-link class="nav-item" to="/history" active-class="active">{{ $t('nav.history') }}</router-link>
        <router-link class="nav-item" to="/asr" active-class="active">{{ $t('nav.asr') }}</router-link>
        <router-link class="nav-item" to="/settings" active-class="active">{{ $t('nav.settings') }}</router-link>
        <div class="sidebar-foot"><div class="engine-card">
          <div class="row"><span class="lbl">ASR</span><span class="val">{{ config.health?.engines?.asr_engine || '-' }}</span></div>
          <div class="row"><span class="lbl">LLM</span><span class="val">{{ config.health?.engines?.llm_model || '-' }}</span></div>
        </div></div>
      </aside>
      <main class="content"><div class="scroll"><router-view /></div></main>
    </div>
  </div>
</template>
<script setup>
import { onMounted, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
const config = useConfigStore()
onMounted(() => { config.applyTheme(); config.fetchAll() })
watch(() => config.settings, () => {}, { deep: true })
</script>
