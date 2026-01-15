<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useAuthStore } from './stores/auth';

const authStore = useAuthStore();
const router = useRouter();

function handleLogout() {
  authStore.logout();
  router.push('/login');
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden bg-slate-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <nav v-if="authStore.isAuthenticated"
      class="bg-white dark:bg-gray-800 shadow p-4 flex justify-between items-center">
      <div class="flex items-center space-x-4">
        <router-link to="/" class="text-xl font-bold">Open-DeepWiki</router-link>
        <router-link to="/" class="hover:text-gold-600">Projects</router-link>
        <router-link v-if="authStore.isAdmin" to="/admin/users" class="hover:text-gold-600">Users</router-link>
        <router-link v-if="authStore.isAdmin" to="/admin/groups" class="hover:text-gold-600">Groups</router-link>
      </div>
      <div class="flex items-center space-x-4">
        <span v-if="authStore.user" class="text-sm border px-2 py-1 rounded bg-gray-100 dark:bg-gray-700">
          {{ authStore.user.role }}
        </span>
        <button @click="handleLogout" class="text-sm text-red-500 hover:text-red-700">Logout</button>
      </div>
    </nav>
    <main class="flex-1 min-h-0 overflow-auto">
      <router-view />
    </main>
  </div>
</template>
