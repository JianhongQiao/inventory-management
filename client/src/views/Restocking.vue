<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.budget') }}</div>
          <div class="stat-value">{{ formatCurrency(recommendation ? recommendation.budget : budget) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.fundedCost') }}</div>
          <div class="stat-value">{{ formatCurrency(recommendation ? recommendation.funded_cost : 0) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.itemsFunded') }}</div>
          <div class="stat-value">{{ recommendation ? recommendation.funded_count : 0 }}</div>
        </div>
        <div :class="['stat-card', { warning: recommendation && recommendation.excluded_count > 0 }]">
          <div class="stat-label">{{ t('restocking.stats.itemsNotFunded') }}</div>
          <div class="stat-value">{{ recommendation ? recommendation.excluded_count : 0 }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>

        <div class="slider-row">
          <input
            type="range"
            class="budget-slider"
            :min="0"
            :max="sliderMax"
            step="100"
            :value="displayBudget"
            @input="displayBudget = Number($event.target.value)"
            @change="commitBudget"
          />
          <span class="slider-value">{{ formatCurrency(displayBudget) }}</span>
        </div>

        <div class="category-bar-container">
          <div class="category-bar" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <div class="progress-meta">
          <span>{{ formatCurrency(recommendation ? recommendation.funded_cost : 0) }} / {{ formatCurrency(budget) }}</span>
        </div>

        <div class="place-order-row">
          <button
            class="btn-primary"
            :disabled="submitting || !recommendation || recommendation.funded_count === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
          <span v-if="!recommendation || recommendation.funded_count === 0" class="hint">
            {{ t('restocking.noItemsFunded') }}
          </span>
          <span v-if="submitSuccess" class="success-message">
            {{ t('restocking.orderPlaced', { orderNumber: submitSuccess }) }}
          </span>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
        </div>
        <div v-if="!recommendation || recommendation.items.length === 0" class="no-data">
          {{ t('restocking.noCandidates') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.rank') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.warehouse') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.quantityOnHand') }}</th>
                <th>{{ t('restocking.table.reorderPoint') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.shortfall') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendation.items"
                :key="item.sku"
                :class="{ 'row-unfunded': !item.funded }"
              >
                <td>{{ item.rank }}</td>
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ item.name }}</td>
                <td>{{ item.category }}</td>
                <td>{{ item.warehouse }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.quantity_on_hand }}</td>
                <td>{{ item.reorder_point }}</td>
                <td>{{ item.forecasted_demand }}</td>
                <td>{{ item.shortfall_qty }}</td>
                <td>{{ formatCurrency(item.unit_cost) }}</td>
                <td>{{ formatCurrency(item.line_cost) }}</td>
                <td>{{ item.lead_time_days }} {{ t('orders.table.days') }}</td>
                <td>
                  <span v-if="item.funded" class="badge success">{{ t('restocking.funded') }}</span>
                  <span v-else class="badge warning">{{ t('restocking.notFunded') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useRestocking } from '../composables/useRestocking'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()
    const formatCurrency = (v) => formatCurrencyUtil(v, currentCurrency.value)
    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const submitSuccess = ref(null)
    const recommendation = ref(null)

    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()
    const { budget } = useRestocking()
    const displayBudget = ref(budget.value)

    const sliderMax = computed(() =>
      Math.max(recommendation.value?.total_shortfall_cost || 0, budget.value, 1000))

    const progressPercent = computed(() => {
      if (!recommendation.value || !budget.value) return 0
      const pct = (recommendation.value.funded_cost / budget.value) * 100
      return Math.min(100, Math.max(0, pct))
    })

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()
        recommendation.value = await api.getRestockingRecommendations({
          budget: budget.value, warehouse: filters.warehouse, category: filters.category
        })
      } catch (err) {
        error.value = 'Failed to load restocking recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const commitBudget = () => {
      submitSuccess.value = null
      budget.value = displayBudget.value
    }

    const placeOrder = async () => {
      try {
        submitting.value = true
        error.value = null
        const filters = getCurrentFilters()
        const order = await api.createRestockingOrder({
          budget: budget.value, warehouse: filters.warehouse, category: filters.category
        })
        submitSuccess.value = order.order_number
        await loadRecommendations()
      } catch (err) {
        error.value = err.response?.data?.detail || ('Failed to submit restocking order: ' + err.message)
      } finally {
        submitting.value = false
      }
    }

    watch([selectedLocation, selectedCategory, budget], loadRecommendations)
    onMounted(loadRecommendations)

    return {
      t, loading, error, submitting, submitSuccess, recommendation,
      budget, displayBudget, sliderMax, progressPercent, formatCurrency,
      commitBudget, placeOrder
    }
  }
}
</script>

<style scoped>
.slider-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.budget-slider {
  flex: 1;
  accent-color: #2563eb;
}

.slider-value {
  min-width: 120px;
  text-align: right;
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.category-bar-container {
  width: 100%;
  height: 8px;
  background: #f1f5f9;
  border-radius: 4px;
  overflow: hidden;
}

.category-bar {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-meta {
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.place-order-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.25rem;
  flex-wrap: wrap;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.625rem 1.5rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.hint {
  font-size: 0.875rem;
  color: #64748b;
}

.success-message {
  font-size: 0.875rem;
  color: #059669;
  font-weight: 600;
}

.row-unfunded {
  opacity: 0.55;
}

.no-data {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}
</style>
