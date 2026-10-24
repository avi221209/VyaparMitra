/**
 * Core API Client for VyaparMitra
 * Automatically attaches X-Role and handles errors.
 */

export type DemoRole = 'planner' | 'warehouse' | 'reviewer';

export const CURRENT_ROLE_KEY = 'vyaparmitra_role';
export const DENSITY_KEY = 'vyaparmitra_density';
export const HORIZON_KEY = 'vyaparmitra_horizon';

export function getStoredRole(): DemoRole {
  const r = localStorage.getItem(CURRENT_ROLE_KEY);
  if (r === 'warehouse' || r === 'reviewer' || r === 'planner') return r;
  return 'planner';
}

export function setStoredRole(role: DemoRole): void {
  localStorage.setItem(CURRENT_ROLE_KEY, role);
}

export async function apiFetch<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const role = getStoredRole();
  const headers = new Headers(options.headers || {});
  if (!headers.has('X-Role')) {
    headers.set('X-Role', role);
  }
  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorDetail = `Request failed with status ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson && errJson.detail) {
          errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
        }
      } catch {
        // ignore
      }
      const error = new Error(errorDetail) as any;
      error.status = response.status;
      throw error;
    }

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('backend-reachable'));
    }

    return response.json();
  } catch (err: any) {
    if (typeof window !== 'undefined') {
      if (err.name === 'TypeError' || err.message?.includes('fetch') || !err.status) {
        window.dispatchEvent(new CustomEvent('backend-unreachable'));
      }
    }
    throw err;
  }
}
