import { createRouter, createWebHashHistory } from 'vue-router'

import ImportWorkspace from '../views/ImportWorkspace.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/workspace/import' },
    {
      path: '/workspace/import',
      name: 'Import',
      component: ImportWorkspace,
      meta: { title: '导入视频' },
    },
    {
      path: '/workspace/history',
      name: 'History',
      component: () => import('../views/History.vue'),
      meta: { title: '知识与历史' },
    },
    {
      path: '/workspace/tasks/:id',
      name: 'TaskDetail',
      component: () => import('../views/TaskDetail.vue'),
      props: true,
      meta: { title: '任务详情' },
    },
    {
      path: '/workspace/note/:id',
      name: 'Note',
      component: () => import('../views/Note.vue'),
      props: true,
      meta: { title: '笔记' },
    },
    {
      path: '/workspace/mindmap/:id',
      name: 'Mindmap',
      component: () => import('../views/Mindmap.vue'),
      props: true,
      meta: { title: '思维导图' },
    },
    {
      path: '/workspace/settings',
      name: 'Settings',
      component: () => import('../views/Settings.vue'),
      meta: { title: '设置' },
    },
    { path: '/history', redirect: '/workspace/history' },
    { path: '/settings', redirect: '/workspace/settings' },
    { path: '/tasks/:id', redirect: (to) => `/workspace/tasks/${String(to.params.id)}` },
    { path: '/note/:id', redirect: (to) => `/workspace/note/${String(to.params.id)}` },
    { path: '/mindmap/:id', redirect: (to) => `/workspace/mindmap/${String(to.params.id)}` },
  ],
})

export default router
