import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

export const useAuthStore = defineStore('auth', () => {
    const user = ref<any>(null);
    const token = ref<string | null>(localStorage.getItem('token'));
    const hasUsers = ref<boolean | null>(null);
    // const router = useRouter();

    const isAuthenticated = computed(() => !!token.value);
    const isAdmin = computed(() => user.value?.role === 'admin');
    const isMaintainer = computed(() => ['admin', 'maintainer'].includes(user.value?.role));

    async function login(email: string, password: string) {
        const formData = new FormData();
        formData.append('username', email); // OAuth2 expects username
        formData.append('password', password);

        try {
            const response = await fetch('/api/v1/auth/token', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Login failed');
            }

            const data = await response.json();
            token.value = data.access_token;
            localStorage.setItem('token', data.access_token);

            // Set basic user info from login response if available, or fetch /users/me
            user.value = {
                role: data.role,
                name: data.name,
                email: email
            };

            return true;
        } catch (error) {
            console.error(error);
            throw error;
        }
    }

    function logout() {
        token.value = null;
        user.value = null;
        localStorage.removeItem('token');
        // router.push('/login'); // Expect component to handle redirect or use router here if possible
        window.location.href = '/login';
    }

    async function fetchUser() {
        if (!token.value) return;
        try {
            const response = await fetch('/api/v1/users/me', {
                headers: {
                    'Authorization': `Bearer ${token.value}`
                }
            });
            if (response.ok) {
                user.value = await response.json();
            } else {
                logout();
            }
        } catch (error) {
            logout();
        }
    }

    async function checkSystemStatus() {
        try {
            const response = await fetch('/api/v1/users/has-users');
            const data = await response.json();
            hasUsers.value = data.exists;
            return data.exists;
        } catch (error) {
            console.error('Failed to check system status:', error);
            return true; // Default to true (safe) on error to avoid sticking in setup loop
        }
    }

    async function setupAdmin(userData: any) {
        try {
            const response = await fetch('/api/v1/users/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(userData),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Setup failed');
            }

            // After setup, automatically log in
            await login(userData.email, userData.password);
            hasUsers.value = true;
            return true;
        } catch (error) {
            throw error;
        }
    }

    return {
        user,
        token,
        isAuthenticated,
        isAdmin,
        isMaintainer,
        login,
        logout,
        fetchUser,
        checkSystemStatus,
        setupAdmin,
        hasUsers
    };
});
