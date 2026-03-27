// Expose API base URL from Vite build-time environment.
// Set VITE_API during build (or in .env) to override the default.
export const API = import.meta.env.VITE_API || 'http://localhost:8000'
