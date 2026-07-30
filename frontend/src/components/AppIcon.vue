<template>
  <component
    :is="iconComponent"
    class="app-icon"
    :size="size"
    :weight="weight"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
    :role="label ? 'img' : undefined"
  />
</template>

<script setup>
import { computed } from 'vue'
import {
  PhArrowClockwise,
  PhArrowDown,
  PhArrowLeft,
  PhArrowRight,
  PhArrowUp,
  PhArrowsOut,
  PhBookOpenText,
  PhCaretDown,
  PhCaretRight,
  PhCheckCircle,
  PhClockCounterClockwise,
  PhCopy,
  PhCrosshairSimple,
  PhDownloadSimple,
  PhFileAudio,
  PhFilePdf,
  PhFileText,
  PhFileVideo,
  PhFolderOpen,
  PhGearSix,
  PhInfo,
  PhLink,
  PhList,
  PhMagnifyingGlass,
  PhMagnifyingGlassMinus,
  PhMagnifyingGlassPlus,
  PhMoonStars,
  PhNotebook,
  PhSidebarSimple,
  PhSlidersHorizontal,
  PhSquaresFour,
  PhSunDim,
  PhTray,
  PhTreeStructure,
  PhUploadSimple,
  PhWarningCircle,
  PhWaveform,
  PhX,
} from '@phosphor-icons/vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
  weight: { type: String, default: 'regular' },
  label: { type: String, default: '' },
})

const icons = {
  'arrow-clockwise': PhArrowClockwise,
  'arrow-down': PhArrowDown,
  'arrow-left': PhArrowLeft,
  'arrow-right': PhArrowRight,
  'arrow-up': PhArrowUp,
  'arrows-out': PhArrowsOut,
  'book-open': PhBookOpenText,
  'caret-down': PhCaretDown,
  'caret-right': PhCaretRight,
  'check-circle': PhCheckCircle,
  'clock-history': PhClockCounterClockwise,
  copy: PhCopy,
  center: PhCrosshairSimple,
  download: PhDownloadSimple,
  'file-audio': PhFileAudio,
  'file-pdf': PhFilePdf,
  'file-text': PhFileText,
  'file-video': PhFileVideo,
  folder: PhFolderOpen,
  settings: PhGearSix,
  info: PhInfo,
  link: PhLink,
  menu: PhList,
  search: PhMagnifyingGlass,
  'zoom-out': PhMagnifyingGlassMinus,
  'zoom-in': PhMagnifyingGlassPlus,
  moon: PhMoonStars,
  notes: PhNotebook,
  sidebar: PhSidebarSimple,
  sliders: PhSlidersHorizontal,
  console: PhSquaresFour,
  sun: PhSunDim,
  tray: PhTray,
  mindmap: PhTreeStructure,
  upload: PhUploadSimple,
  warning: PhWarningCircle,
  asr: PhWaveform,
  close: PhX,
}

const iconComponent = computed(() => icons[props.name] || PhInfo)
</script>
