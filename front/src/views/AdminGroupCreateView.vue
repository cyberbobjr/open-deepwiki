<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const router = useRouter();
const authStore = useAuthStore();

const group = ref({
    name: '',
});
const loading = ref(false);
const error = ref('');

async function createGroup() {
    loading.value = true;
    error.value = '';
    try {
        const response = await fetch('/api/v1/groups/', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authStore.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(group.value)
        });
        if (response.ok) {
            router.push('/admin/groups');
        } else {
            const data = await response.json();
            error.value = data.detail || 'Failed to create group';
        }
    } catch (e) {
        error.value = 'Network error';
    } finally {
        loading.value = false;
    }
}
</script>

<template>
    <div class="p-6 max-w-2xl mx-auto">
        <h1 class="text-2xl font-bold mb-6 text-[var(--color-primary)]">Create New Group</h1>

        <div v-if="error" class="bg-red-100 text-red-700 p-4 rounded mb-4">{{ error }}</div>

        <div class="bg-white dark:bg-gray-800 rounded shadow p-6">
            <form @submit.prevent="createGroup">
                <div class="mb-6">
                    <label class="block text-sm font-medium mb-1">Group Name</label>
                    <input v-model="group.name" type="text" required
                        class="w-full p-2 border rounded focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent dark:bg-gray-700" />
                </div>

                <div class="flex justify-end space-x-3">
                    <router-link to="/admin/groups"
                        class="px-4 py-2 border rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                        Cancel
                    </router-link>
                    <button type="submit" :disabled="loading"
                        class="px-4 py-2 bg-[var(--color-primary)] text-white rounded hover:bg-green-800 transition-colors disabled:opacity-50">
                        {{ loading ? 'Creating...' : 'Create Group' }}
                    </button>
                </div>
            </form>
        </div>
    </div>
</template>
