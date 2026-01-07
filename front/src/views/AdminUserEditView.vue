<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const user = ref<any>({
    email: '',
    firstname: '',
    lastname: '',
    role: 'user',
});
const loading = ref(true);
const error = ref('');

const roles = ['user', 'maintainer', 'admin'];

async function fetchUser() {
    try {
        const response = await fetch(`/api/v1/users/${route.params.id}`, {
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (response.ok) {
            user.value = await response.json();
        } else {
            error.value = 'Failed to fetch user';
        }
    } catch (e) {
        error.value = 'Network error';
    } finally {
        loading.value = false;
    }
}

async function saveUser() {
    try {
        const response = await fetch(`/api/v1/users/${route.params.id}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authStore.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(user.value)
        });
        if (response.ok) {
            router.push('/admin/users');
        } else {
            error.value = 'Failed to update user';
        }
    } catch (e) {
        error.value = 'Network error';
    }
}

onMounted(() => {
    fetchUser();
});
</script>

<template>
    <div class="p-6 max-w-2xl mx-auto">
        <h1 class="text-2xl font-bold mb-6 text-[var(--color-primary)]">Edit User</h1>

        <div v-if="loading" class="text-center py-4">Loading...</div>
        <div v-else-if="error" class="bg-red-100 text-red-700 p-4 rounded mb-4">{{ error }}</div>

        <div v-if="!loading && user" class="bg-white dark:bg-gray-800 rounded shadow p-6">
            <form @submit.prevent="saveUser">
                <div class="mb-4">
                    <label class="block text-sm font-medium mb-1">Email</label>
                    <input v-model="user.email" type="email" disabled
                        class="w-full p-2 border rounded bg-gray-100 dark:bg-gray-700 cursor-not-allowed text-gray-500" />
                </div>

                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div>
                        <label class="block text-sm font-medium mb-1">First Name</label>
                        <input v-model="user.firstname" type="text"
                            class="w-full p-2 border rounded focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent dark:bg-gray-700" />
                    </div>
                    <div>
                        <label class="block text-sm font-medium mb-1">Last Name</label>
                        <input v-model="user.lastname" type="text"
                            class="w-full p-2 border rounded focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent dark:bg-gray-700" />
                    </div>
                </div>

                <div class="mb-6">
                    <label class="block text-sm font-medium mb-1">Role</label>
                    <select v-model="user.role"
                        class="w-full p-2 border rounded focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent dark:bg-gray-700">
                        <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
                    </select>
                </div>

                <div class="flex justify-end space-x-3">
                    <router-link to="/admin/users"
                        class="px-4 py-2 border rounded hover:bg-gray-50 dark:hover:bg-gray-700">
                        Cancel
                    </router-link>
                    <button type="submit"
                        class="px-4 py-2 bg-[var(--color-primary)] text-white rounded hover:bg-green-800 transition-colors">
                        Save Changes
                    </button>
                </div>
            </form>
        </div>
    </div>
</template>
