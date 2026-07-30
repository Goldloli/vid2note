<template>
  <aside class="library-sidebar surface">
    <div class="library-sidebar-head">
      <div>
        <strong>{{ title }}</strong>
        <span>{{ items.length }}</span>
      </div>
      <label class="library-search">
        <AppIcon name="search" :size="16" />
        <input
          :value="query"
          :placeholder="searchPlaceholder"
          :aria-label="searchPlaceholder"
          @input="$emit('update:query', $event.target.value)"
        >
      </label>
    </div>

    <LoadingState v-if="loading" class="library-loading" :label="loadingLabel" :rows="5" />
    <EmptyState
      v-else-if="error"
      class="library-state"
      :title="errorTitle"
      :description="error"
      icon="warning"
      tone="danger"
    >
      <template #actions>
        <button class="btn btn-sm" type="button" @click="$emit('retry')">
          <AppIcon name="arrow-clockwise" :size="15" />
          {{ retryLabel }}
        </button>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="!items.length"
      class="library-state"
      :title="emptyTitle"
      :description="emptyDescription"
      icon="tray"
    />

    <div v-else class="library-list">
      <button
        v-for="item in items"
        :key="item.id"
        class="library-item"
        :class="{ active: selectedId === item.id }"
        type="button"
        @click="$emit('select', item.id)"
      >
        <span class="library-item-icon"><AppIcon :name="itemIcon" :size="17" weight="duotone" /></span>
        <span class="library-item-copy">
          <strong>{{ displayName(item) }}</strong>
          <small>{{ item.asr_engine || '-' }} / {{ item.llm_provider || item.llm_model || '-' }}</small>
        </span>
        <AppIcon name="caret-right" :size="14" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { displayName } from '@/format'

defineProps({
  title: { type: String, required: true },
  items: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  query: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  itemIcon: { type: String, default: 'file-text' },
  searchPlaceholder: { type: String, required: true },
  loadingLabel: { type: String, required: true },
  emptyTitle: { type: String, required: true },
  emptyDescription: { type: String, default: '' },
  errorTitle: { type: String, required: true },
  retryLabel: { type: String, required: true },
})

defineEmits(['update:query', 'select', 'retry'])
</script>

<style scoped>
.library-sidebar{display:flex;min-height:0;flex-direction:column;overflow:hidden}
.library-sidebar-head{padding:15px 14px 12px;border-bottom:1px solid var(--border)}
.library-sidebar-head>div{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.library-sidebar-head strong{font-size:13px}
.library-sidebar-head>div span{display:grid;place-items:center;min-width:22px;height:20px;padding:0 6px;border-radius:999px;background:var(--card-2);color:var(--muted);font-family:var(--mono);font-size:10px}
.library-search{display:flex;align-items:center;gap:7px;height:36px;padding:0 9px;border:1px solid var(--border-2);border-radius:var(--r-sm);background:var(--card);color:var(--muted)}
.library-search:focus-within{border-color:var(--accent);box-shadow:var(--ring)}
.library-search input{width:100%;min-width:0;border:0;outline:0;background:transparent;color:var(--text);font-size:12px}
.library-search input::placeholder{color:var(--muted-2)}
.library-list{flex:1;min-height:0;overflow:auto;padding:7px}
.library-item{display:grid;grid-template-columns:30px minmax(0,1fr) 14px;align-items:center;gap:8px;width:100%;padding:9px 8px;border:1px solid transparent;border-radius:var(--r-sm);color:var(--text-2);text-align:left;transition:color var(--ease),background var(--ease),border-color var(--ease)}
.library-item:hover{border-color:var(--border);background:var(--card-2);color:var(--text)}
.library-item.active{border-color:rgba(40,100,220,.2);background:var(--accent-soft);color:var(--accent)}
.library-item-icon{display:grid;place-items:center;width:30px;height:30px;border-radius:8px;background:var(--card-2)}
.library-item.active .library-item-icon{background:var(--card)}
.library-item-copy{min-width:0}
.library-item-copy strong,.library-item-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.library-item-copy strong{font-size:12px;font-weight:600}
.library-item-copy small{margin-top:2px;color:var(--muted);font-family:var(--mono);font-size:9.5px}
.library-loading{margin:10px;border:0;box-shadow:none}
.library-state{min-height:240px}
</style>
