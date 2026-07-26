import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  { path: '/', name: 'console', component: () => import('@/views/Console.vue') },
  { path: '/task/:id', name: 'task-detail', component: () => import('@/views/TaskDetail.vue') },
  { path: '/note/:id', name: 'note', component: () => import('@/views/Note.vue') },
  { path: '/notes', name: 'notes-browser', component: () => import('@/views/NotesBrowser.vue') },
  { path: '/mindmap/:id', name: 'mindmap', component: () => import('@/views/Mindmap.vue') },
  { path: '/mindmaps', name: 'mindmaps-browser', component: () => import('@/views/MindmapsBrowser.vue') },
  { path: '/history', name: 'history', component: () => import('@/views/History.vue') },
  { path: '/asr', name: 'asr', component: () => import('@/views/Asr.vue') },
  { path: '/settings', name: 'settings', component: () => import('@/views/Settings.vue') },
]
const router = createRouter({ history: createWebHistory(), routes })
export default router
