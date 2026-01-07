<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const email = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

const authStore = useAuthStore();
const router = useRouter();

async function handleLogin() {
    loading.value = true;
    error.value = '';
    try {
        await authStore.login(email.value, password.value);
        router.push('/');
    } catch (e: any) {
        error.value = e.message;
    } finally {
        loading.value = false;
    }
}
</script>

<template>
    <div class="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
        <div class="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-md w-full max-w-md">
            <h1 class="text-2xl font-bold mb-6 text-center text-gray-900 dark:text-white">Sign In</h1>

            <form @submit.prevent="handleLogin" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
                    <input v-model="email" type="email" required
                        class="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-gold-500" />
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                    <input v-model="password" type="password" required
                        class="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:outline-none focus:ring-2 focus:ring-gold-500" />
                </div>

                <div v-if="error" class="text-red-500 text-sm text-center">
                    {{ error }}
                </div>

                <button type="submit" :disabled="loading"
                    class="w-full bg-gold-600 hover:bg-gold-700 text-white font-bold py-2 px-4 rounded transition disabled:opacity-50">
                    {{ loading ? 'Signing In...' : 'Sign In' }}
                </button>
            </form>
        </div>
    </div>
</template>
