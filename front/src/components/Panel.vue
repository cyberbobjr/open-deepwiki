<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    collapsible?: boolean
    collapsed?: boolean
    collapseText?: string
    expandText?: string
  }>(),
  {
    subtitle: undefined,
    collapsible: false,
    collapsed: false,
    collapseText: 'Collapse',
    expandText: 'Expand',
  },
)

const emit = defineEmits<{
  (e: 'toggle'): void
}>()

const buttonLabel = computed(() => (props.collapsed ? props.expandText : props.collapseText))
</script>

<template>
  <section class="rounded-lg border border-slate-200 bg-white">
    <div class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <div class="min-w-0">
        <div class="truncate text-sm font-semibold text-slate-900" :title="title">
          {{ title }}
        </div>
        <div v-if="subtitle" class="truncate text-xs text-slate-600" :title="subtitle">
          {{ subtitle }}
        </div>
      </div>

      <div class="flex shrink-0 items-center gap-3">
        <slot name="headerRight" />
        <button
          v-if="collapsible"
          type="button"
          class="h-7 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700"
          @click="emit('toggle')"
        >
          {{ buttonLabel }}
        </button>
      </div>
    </div>

    <Transition name="odw-collapse">
      <div v-if="!collapsible || !collapsed" class="odw-collapsible-body">
        <slot />
      </div>
    </Transition>
  </section>
</template>
