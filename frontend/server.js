// Where the Byte API lives. The panel runs on other devices; the owner types the server once.
// Empty = the page's own origin (uvicorn --web on the PC). Run: node --test frontend/tests/server.test.mjs

const KEY = 'byte.server';

export function normalizeServer(input) {
  const raw = String(input || '').trim();
  if (!raw) return '';
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : '';
  } catch {
    return '';
  }
}

export const apiBase = (server, page) => `${server || page.origin}/api/v1`;

export const wsBase = (server, page) => apiBase(server, page).replace(/^http/, 'ws');

// The address is not a secret: localStorage keeps it across tabs and restarts.
export const server = {
  get: () => { try { return localStorage.getItem(KEY) || ''; } catch { return ''; } },
  set: (s) => { try { s ? localStorage.setItem(KEY, s) : localStorage.removeItem(KEY); } catch { /* private mode */ } },
};

export const apiUrl = (path) => apiBase(server.get(), location) + path;
export const wsUrl = (path) => wsBase(server.get(), location) + path;
