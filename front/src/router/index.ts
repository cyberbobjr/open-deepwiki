import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import AdminGroupsView from '../views/AdminGroupsView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import ConversationView from '../views/ConversationView.vue'
import LoginView from '../views/LoginView.vue'
import ProjectOverviewView from '../views/ProjectOverviewView.vue'
import ProjectsView from '../views/ProjectsView.vue'
import SetupView from '../views/SetupView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/setup', name: 'setup', component: SetupView },
    {
      path: '/',
      name: 'projects',
      component: ProjectsView,
      meta: { requiresAuth: true }
    },
    {
      path: '/projects/:project',
      name: 'project',
      component: ProjectOverviewView,
      props: true,
      meta: { requiresAuth: true }
    },
    {
      path: '/projects/:project/chat',
      name: 'chat',
      component: ConversationView,
      props: true,
      meta: { requiresAuth: true }
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: AdminUsersView,
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/groups',
      name: 'admin-groups',
      component: AdminGroupsView,
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/groups/create',
      name: 'admin-group-create',
      component: () => import('../views/AdminGroupCreateView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/groups/:id',
      name: 'admin-group-edit',
      component: () => import('../views/AdminGroupEditView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/users/:id',
      name: 'admin-user-edit',
      component: () => import('../views/AdminUserEditView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/users/create',
      name: 'admin-user-create',
      component: () => import('../views/AdminUserCreateView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    }
  ],
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();

  // Attempt to hydrate user if token exists but user is null
  if (authStore.token && !authStore.user) {
    try {
      await authStore.fetchUser();
    } catch (e) {
      // Token invalid
    }
  }

  // Check system status if unknown
  if (authStore.hasUsers === null) {
    await authStore.checkSystemStatus();
  }

  // Redirect logic for Setup
  if (!authStore.hasUsers && to.path !== '/setup') {
    return next('/setup');
  }

  if (authStore.hasUsers && to.path === '/setup') {
    return next('/login');
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login');
  } else if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/'); // Or unauthorized page
  } else {
    next();
  }
});
