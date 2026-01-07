<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const group = ref<any>({
    id: 0,
    name: '',
    users: [], // Current members
});
const allUsers = ref<any[]>([]); // For selection
const selectedUserId = ref<number | null>(null);

const loading = ref(true);
const error = ref('');

// Filter out users already in the group
const availableUsers = computed(() => {
    const existingIds = group.value.users.map((u: any) => u.id);
    return allUsers.value.filter(u => !existingIds.includes(u.id));
});

async function fetchGroup() {
    const groupId = route.params.id;

    try {
        // Fetch group
        let res = await fetch(`/api/v1/groups/${groupId}`, {
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });

        // If 404 or method not allowed, fallback to list (temporary hack until backend updated)
        if (!res.ok) {
            const listRes = await fetch(`/api/v1/groups/`, {
                headers: { 'Authorization': `Bearer ${authStore.token}` }
            });
            const groups = await listRes.json();
            const found = groups.find((g: any) => g.id == groupId);
            if (found) {
                group.value = found;
            } else {
                error.value = "Group not found";
            }
        } else {
            group.value = await res.json();
        }

        // Fetch all users for dropdown
        const usersRes = await fetch('/api/v1/users/', {
            headers: { 'Authorization': `Bearer ${authStore.token}` }
        });
        if (usersRes.ok) {
            allUsers.value = await usersRes.json();
        }

    } catch (e) {
        error.value = 'Failed to load data';
        console.error(e);
    } finally {
        loading.value = false;
    }
}

function addUser() {
    if (!selectedUserId.value) return;
    const userToAdd = allUsers.value.find(u => u.id === selectedUserId.value);
    if (userToAdd) {
        group.value.users.push(userToAdd);
        selectedUserId.value = null; // Reset selection
    }
}

function removeUser(userId: number) {
    group.value.users = group.value.users.filter((u: any) => u.id !== userId);
}

async function saveGroup() {
    try {
        const payload = {
            name: group.value.name,
            user_ids: group.value.users.map((u: any) => u.id)
        };

        const response = await fetch(`/api/v1/groups/${route.params.id}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authStore.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            router.push('/admin/groups');
        } else {
            const data = await response.json();
            error.value = data.detail || 'Failed to update group';
        }
    } catch (e) {
        error.value = 'Network error';
    }
}

onMounted(() => {
    fetchGroup();
});
</script>

<template>
    <div class="p-6 max-w-2xl mx-auto">
        <h1 class="text-2xl font-bold mb-6 text-[var(--color-primary)]">Edit Group</h1>

        <div v-if="loading" class="text-center py-4">Loading...</div>
        <div v-else-if="error" class="bg-red-100 text-red-700 p-4 rounded mb-4">{{ error }}</div>

        <div v-if="!loading && group.id" class="bg-white dark:bg-gray-800 rounded shadow p-6">
            <form @submit.prevent="saveGroup">
                <div class="mb-6">
                    <label class="block text-sm font-medium mb-1">Group Name</label>
                    <input v-model="group.name" type="text" required
                        class="w-full p-2 border rounded focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent dark:bg-gray-700" />
                </div>

                <div class="mb-6">
                    <label class="block text-sm font-medium mb-2">Members ({{ group.users.length }})</label>

                    <!-- Add Member -->
                    <div class="flex gap-2 mb-4">
                        <select v-model="selectedUserId" class="flex-1 p-2 border rounded dark:bg-gray-700">
                            <option :value="null" disabled>Select user to add...</option>
                            <option v-for="user in availableUsers" :key="user.id" :value="user.id">
                                {{ user.firstname }} {{ user.lastname }} ({{ user.email }})
                            </option>
                        </select>
                        <button type="button" @click="addUser" :disabled="!selectedUserId"
                            class="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50">
                            Add
                        </button>
                    </div>

                    <!-- Member List -->
                    <div class="border rounded divide-y dark:border-gray-700 dark:divide-gray-700">
                        <div v-if="group.users.length === 0" class="p-4 text-gray-500 text-center text-sm">
                            No members in this group.
                        </div>
                        <div v-for="user in group.users" :key="user.id"
                            class="p-3 flex justify-between items-center bg-gray-50 dark:bg-gray-900">
                            <div>
                                <div class="font-medium">{{ user.firstname }} {{ user.lastname }}</div>
                                <div class="text-xs text-gray-500">{{ user.email }}</div>
                            </div>
                            <button type="button" @click="removeUser(user.id)"
                                class="text-red-600 hover:text-red-800 text-sm">
                                Remove
                            </button>
                        </div>
                    </div>
                </div>

                <div class="flex justify-end space-x-3">
                    <router-link to="/admin/groups"
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
