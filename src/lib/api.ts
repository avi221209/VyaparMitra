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

export const BACKEND_URL_KEY = 'vyaparmitra_backend_url';

export function getBackendBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const customUrl = localStorage.getItem(BACKEND_URL_KEY);
    if (customUrl && customUrl.trim()) {
      return customUrl.trim().replace(/\/$/, '');
    }
  }
  const envUrl = (
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.VITE_API_URL ||
    import.meta.env.VITE_BACKEND_URL
  ) as string | undefined;
  if (envUrl && envUrl.trim()) {
    return envUrl.trim().replace(/\/$/, '');
  }
  return '';
}

export function setBackendBaseUrl(url: string): void {
  if (typeof window !== 'undefined') {
    const cleaned = url.trim().replace(/\/$/, '');
    if (!cleaned) {
      localStorage.removeItem(BACKEND_URL_KEY);
    } else {
      localStorage.setItem(BACKEND_URL_KEY, cleaned);
    }
    window.dispatchEvent(new CustomEvent('backend-url-changed', { detail: cleaned }));
  }
}

export function isBackendConfigured(): boolean {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return true;
    }
  }
  return !!getBackendBaseUrl();
}

export function getApiUrl(path: string): string {
  let cleanPath = path;
  if (cleanPath.startsWith('/api/') && !cleanPath.startsWith('/api/v1/')) {
    cleanPath = cleanPath.replace('/api/', '/api/v1/');
  }
  const apiBase = getBackendBaseUrl();
  if (apiBase && cleanPath.startsWith('/')) {
    return `${apiBase}${cleanPath}`;
  }
  return cleanPath;
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

  const finalUrl = getApiUrl(url);

  try {
    const response = await fetch(finalUrl, {
      ...options,
      headers,
    });

    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      let errorDetail = `Request failed with status ${response.status}`;
      try {
        if (contentType.includes('application/json')) {
          const errJson = await response.json();
          if (errJson && errJson.detail) {
            errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
          }
        } else {
          const errText = await response.text();
          if (errText && errText.length < 200 && !errText.includes('<!DOCTYPE') && !errText.includes('<!doctype')) {
            errorDetail = errText;
          }
        }
      } catch {
        // ignore
      }

      // Detect static host (e.g. Netlify) returning 404 for an API route because backend URL is not configured
      const isStaticHost404 =
        response.status === 404 &&
        (!getBackendBaseUrl() ||
          contentType.includes('text/html') ||
          (typeof window !== 'undefined' && window.location.hostname.endsWith('netlify.app')));

      if (isStaticHost404) {
        errorDetail = `Backend service is not connected. Please enter your Render backend URL (e.g. https://your-service.onrender.com) in Settings or the connection box.`;
      }

      const error = new Error(errorDetail) as any;
      error.status = response.status;
      if (isStaticHost404) {
        error.isUnreachable = true;
      }
      throw error;
    }

    // Check if a static host like Netlify returned index.html for a 200 OK
    if (contentType.includes('text/html')) {
      const text = await response.text();
      if (text.trim().startsWith('<') || text.includes('<!DOCTYPE') || text.includes('<!doctype')) {
        const error = new Error(
          `Static host served index.html instead of API data. Please set your Render backend URL below or configure VITE_API_BASE_URL.`
        ) as any;
        error.status = 502;
        error.isHtmlFallback = true;
        throw error;
      }
      try {
        return JSON.parse(text);
      } catch {
        throw new Error(`Invalid response format from '${finalUrl}'`);
      }
    }

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('backend-reachable'));
    }

    try {
      return await response.json();
    } catch (parseErr: any) {
      if (parseErr.message?.includes('Unexpected token') || parseErr.message?.includes('JSON')) {
        const error = new Error(
          `Invalid JSON response from '${finalUrl}'. The host returned an HTML document instead of API data. Please configure your Render Backend URL.`
        ) as any;
        error.status = 502;
        error.isHtmlFallback = true;
        throw error;
      }
      throw parseErr;
    }
  } catch (err: any) {
    if (typeof window !== 'undefined') {
      if (
        err.name === 'TypeError' ||
        err.message?.includes('fetch') ||
        !err.status ||
        err.isHtmlFallback ||
        err.isUnreachable
      ) {
        window.dispatchEvent(new CustomEvent('backend-unreachable'));
      }
    }
    throw err;
  }
}
