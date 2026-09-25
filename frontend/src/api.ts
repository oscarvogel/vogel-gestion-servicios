export const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

export function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}
