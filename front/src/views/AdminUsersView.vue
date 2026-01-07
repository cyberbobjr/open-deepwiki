<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useAuthStore } from '../stores/auth';

const users = ref<any[]>([]);
const authStore = useAuthStore();

async function fetchUsers() {
    try {
        const response = await fetch('/api/v1/users/', {
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (response.ok) {
            users.value = await response.json();
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteUser(id: number) {
    if (!confirm('Are you sure you want to delete this user?')) return;
    try {
        const response = await fetch(`/api/v1/users/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (response.ok) {
            fetchUsers(); // Refresh list
        } else {
            alert('Failed to delete user');
        }
    } catch (e) {
        alert('Network error');
    }
}

onMounted(() => {
    fetchUsers();
});
</script>

<template>
    <div class="p-6">
        <div class="flex justify-between items-center mb-4">
            <h1 class="text-2xl font-bold text-[var(--color-primary)]">User Management</h1>
            <router-link to="/admin/users/create"
                class="px-4 py-2 bg-[var(--color-primary)] text-white rounded hover:bg-green-800 transition-colors">
                + Create User
            </router-link>
        </div>
        <div class="bg-white dark:bg-gray-800 rounded shadow overflow-hidden">
            <table class="min-w-full">
                <thead class="bg-gray-50 dark:bg-gray-700">
                    <tr>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            ID</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Email</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Name</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Role</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 dark:divide-gray-600">
                    <tr v-for="user in users" :key="user.id">
                        <td class="px-6 py-4 whitespace-nowrap">{{ user.id }}</td>
                        <td class="px-6 py-4 whitespace-nowrap">{{ user.email }}</td>
                        <td class="px-6 py-4 whitespace-nowrap">{{ user.firstname }} {{ user.lastname }}</td>
                        <td class="px-6 py-4 whitespace-nowrap bg-blue-100 text-center">{{ user.role }}
                        </td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <router-link :to="{ name: 'admin-user-edit', params: { id: user.id } }"
                                class="text-[var(--color-primary)] hover:text-green-800 mr-2 font-medium">Edit</router-link>
                            <button @click="deleteUser(user.id)" class="text-red-600 hover:text-red-900">Delete</button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</template>
