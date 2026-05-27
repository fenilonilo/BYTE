import type { ProjectItem, ProjectsState } from '../lib/types'

export const projectsState = $state<ProjectsState>({
  items:   [],
  loading: false,
})

export async function fetchProjects(): Promise<void> {
  projectsState.loading = true
  try {
    const res = await fetch('/api/v1/projects')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    projectsState.items = await res.json() as ProjectItem[]
  } catch {
    // Keep stale data on error — silent fail
  } finally {
    projectsState.loading = false
  }
}

/** Start polling every 30s. Returns a cleanup function. */
export function startPolling(): () => void {
  fetchProjects()
  const id = setInterval(fetchProjects, 30_000)
  return () => clearInterval(id)
}
