import { nextTick, onMounted } from 'vue'

export function useReveal(router) {
  function triggerReveal() {
    const els = document.querySelectorAll('.reveal:not(.in)')
    els.forEach((el, i) => {
      setTimeout(() => el.classList.add('in'), 50 + i * 45)
    })
  }

  onMounted(() => {
    nextTick(() => triggerReveal())
    if (router) {
      router.afterEach(() => {
        nextTick(() => triggerReveal())
      })
    }
  })
}
