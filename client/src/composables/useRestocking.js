import { ref } from 'vue'

// Shared budget state (singleton pattern), mirrors composables/useFilters.js
const budget = ref(20000)

export function useRestocking() {
  return {
    budget
  }
}
