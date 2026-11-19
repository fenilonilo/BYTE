// Where the Byte API lives (config.js). Run: node --test frontend/tests/server.test.mjs

import { SERVER } from './config.js';

export const apiBase = (server, page) => `${server || page.origin}/api/v1`;

export const wsBase = (server, page) => apiBase(server, page).replace(/^http/, 'ws');

export const apiUrl = (path) => apiBase(SERVER, location) + path;
export const wsUrl = (path) => wsBase(SERVER, location) + path;
