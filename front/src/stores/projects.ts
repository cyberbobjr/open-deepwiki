import { defineStore } from 'pinia'

import { deleteProject, listProjectsDetails, type DeleteProjectResponse, type ProjectInfo } from '../api/openDeepWiki'

export const useProjectsStore = defineStore('projects', {
  state: () => ({
    projects: [] as ProjectInfo[],
    loading: false,
    error: '' as string,
    deletingProject: '' as string,
  }),
  actions: {
    async refresh(): Promise<void> {
      this.loading = true
      this.error = ''
      try {
        this.projects = await listProjectsDetails()
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        this.projects = []
      } finally {
        this.loading = false
      }
    },

    async removeProject(project: string): Promise<DeleteProjectResponse | null> {
      const p = project.trim()
      if (!p) return null

      this.deletingProject = p
      this.error = ''
      try {
        const res = await deleteProject(p)
        await this.refresh()
        return res
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
        return null
      } finally {
        this.deletingProject = ''
      }
    },
  },
})
