export function notify({ title, message, type = 'success' }) {
  window.dispatchEvent(new CustomEvent('app-toast', {
    detail: { title, message, type }
  }))
}
