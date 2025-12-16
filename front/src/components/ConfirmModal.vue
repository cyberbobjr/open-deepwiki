<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'

type Props = {
  open: boolean
  mode?: 'confirm' | 'info'
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  busy?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'confirm',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  busy: false,
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

function onKeydown(e: KeyboardEvent): void {
  if (!props.open) return
  if (e.key === 'Escape') emit('cancel')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})

watch(
  () => props.open,
  (open) => {
    if (open) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
  },
  { immediate: true },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-slate-900/30" @click="emit('cancel')" />

      <div class="relative flex h-full items-center justify-center p-4">
        <div
          class="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          @click.stop
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-base font-semibold text-slate-900">{{ title }}</div>
              <div class="mt-2 whitespace-pre-line text-sm text-slate-700">{{ message }}</div>
            </div>

            <button
              class="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700 disabled:opacity-60"
              :disabled="busy"
              @click="emit('cancel')"
              aria-label="Close"
              title="Close"
            >
              ✕
            </button>
          </div>

          <div class="mt-5 flex items-center justify-end gap-2">
            <button
              class="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 disabled:opacity-60"
              :disabled="busy"
              @click="emit('cancel')"
            >
              {{ props.mode === 'confirm' ? cancelText : 'Close' }}
            </button>
            <button
              v-if="props.mode === 'confirm'"
              class="h-9 rounded-md border border-red-200 bg-white px-3 text-sm text-red-700 disabled:opacity-60"
              :disabled="busy"
              @click="emit('confirm')"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
