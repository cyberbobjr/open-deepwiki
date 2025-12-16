import { createRouter, createWebHistory } from 'vue-router'

import ProjectsView from '../views/ProjectsView.vue'
import ProjectOverviewView from '../views/ProjectOverviewView.vue'
import ConversationView from '../views/ConversationView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'projects', component: ProjectsView },
    { path: '/projects/:project', name: 'project', component: ProjectOverviewView, props: true },
    { path: '/projects/:project/chat', name: 'chat', component: ConversationView, props: true },
  ],
})
