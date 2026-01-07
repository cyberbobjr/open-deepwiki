<template>
    <div class="p-6">
        <div class="flex justify-between items-center mb-4">
            <h1 class="text-2xl font-bold text-[var(--color-primary)]">Group Management</h1>
            <router-link to="/admin/groups/create"
                class="px-4 py-2 bg-[var(--color-primary)] text-white rounded hover:bg-green-800 transition-colors">
                + Create Group
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
                            Name</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Members</th>
                        <th
                            class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                            Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 dark:divide-gray-600">
                    <tr v-for="group in groups" :key="group.id">
                        <td class="px-6 py-4 whitespace-nowrap">{{ group.id }}</td>
                        <td class="px-6 py-4 whitespace-nowrap">{{ group.name }}</td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <span
                                class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                                {{ group.users ? group.users.length : 0 }} users
                            </span>
                        </td>
                        <td class="px-6 py-4 whitespace-nowrap">
                            <router-link :to="{ name: 'admin-group-edit', params: { id: group.id } }"
                                class="text-[var(--color-primary)] hover:text-green-800 mr-2 font-medium">Edit</router-link>
                            <button @click="deleteGroup(group.id)"
                                class="text-red-600 hover:text-red-900">Delete</button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useAuthStore } from '../stores/auth';

const groups = ref<any[]>([]);
const authStore = useAuthStore();

async function fetchGroups() {
    try {
        const response = await fetch('/api/v1/groups/', {
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (response.ok) {
            groups.value = await response.json();
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteGroup(id: number) {
    if (!confirm('Are you sure you want to delete this group?')) return;
    try {
        const response = await fetch(`/api/v1/groups/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (response.ok) {
            fetchGroups(); // Refresh
        } else {
            alert('Failed to delete group');
        }
    } catch (e) {
        alert('Network error');
    }
}

onMounted(() => {
    fetchGroups();
});
</script>
