<template>
  <div class="app">
    <header class="titlebar">
      <button
        class="icon-btn tb-menu"
        type="button"
        :aria-label="$t('nav.menu')"
        :aria-expanded="navOpen"
        @click="navOpen = !navOpen"
      >
        <AppIcon :name="navOpen ? 'close' : 'menu'" :size="20" />
      </button>
      <div class="tb-title">
        <img src="/icons/vid2note-icon-64.png?v=3" alt="" aria-hidden="true">
        <span>{{ $t('nav.brand') }}</span>
      </div>
      <div class="tb-spacer"></div>
      <span class="service-pill">
        <span class="dot-live" aria-hidden="true"></span>
        {{ $t('nav.local') }}
      </span>
      <button
        class="icon-btn"
        type="button"
        :aria-label="$t('nav.themeTip')"
        :title="$t('nav.themeTip')"
        @click="config.toggleTheme()"
      >
        <AppIcon name="moon" :size="19" />
      </button>
    </header>

    <div class="body">
      <button
        v-if="navOpen"
        class="nav-scrim"
        type="button"
        :aria-label="$t('nav.closeMenu')"
        @click="navOpen = false"
      ></button>

      <aside class="sidebar" :class="{ open: navOpen }">
        <div class="brand">
          <img class="mark" src="/icons/vid2note-icon-64.png?v=3" alt="" aria-hidden="true">
          <div class="brand-copy">
            <div class="name">vid2note</div>
            <div class="ver">{{ $t('nav.workspace') }}</div>
          </div>
        </div>

        <div class="nav-label">{{ $t('nav.label') }}</div>
        <nav class="nav-list" :aria-label="$t('nav.label')">
          <router-link
            v-for="item in navItems"
            :key="item.to"
            class="nav-item"
            :class="{ active: isNavActive(item) }"
            :to="item.to"
            :title="$t(item.label)"
            @click="navOpen = false"
          >
            <AppIcon :name="item.icon" :size="19" :weight="isNavActive(item) ? 'fill' : 'regular'" />
            <span class="nav-text">{{ $t(item.label) }}</span>
          </router-link>
        </nav>

        <div class="sidebar-foot">
          <div class="engine-card">
            <div class="engine-card-head">
              <span class="engine-health"><span class="dot-live" aria-hidden="true"></span></span>
              <span class="engine-summary">{{ $t('nav.engineSummary') }}</span>
            </div>
            <div class="engine-row-side">
              <span class="lbl">ASR</span>
              <span class="val" data-testid="sidebar-asr" :data-engine="currentAsr">{{ $t('engine.short.' + currentAsr) }}</span>
            </div>
            <div class="engine-row-side">
              <span class="lbl">LLM</span>
              <span class="val" data-testid="sidebar-llm" :data-model="currentLlm">{{ currentLlm || '-' }}</span>
            </div>
          </div>
        </div>
      </aside>

      <main class="content">
        <div class="scroll"><router-view /></div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import { useConfigStore } from '@/stores/config'

const config = useConfigStore()
const route = useRoute()
const navOpen = ref(false)
const navItems = [
  { to: '/', icon: 'console', label: 'nav.console', routes: ['console', 'task-detail'] },
  { to: '/notes', icon: 'notes', label: 'nav.note', routes: ['notes-browser', 'note'] },
  { to: '/mindmaps', icon: 'mindmap', label: 'nav.mindmap', routes: ['mindmaps-browser', 'mindmap'] },
  { to: '/history', icon: 'clock-history', label: 'nav.history', routes: ['history'] },
  { to: '/asr', icon: 'asr', label: 'nav.asr', routes: ['asr'] },
  { to: '/settings', icon: 'settings', label: 'nav.settings', routes: ['settings'] },
]

const currentAsr = computed(() => config.settings?.settings?.['asr.engine'] || config.health?.engines?.asr_engine || 'bcut')
const currentLlm = computed(() => config.settings?.settings?.['llm.model'] || config.health?.engines?.llm_model || '')
const isNavActive = item => item.routes.includes(route.name)

onMounted(() => {
  config.applyAppearance()
  config.fetchAll()
})
</script>
