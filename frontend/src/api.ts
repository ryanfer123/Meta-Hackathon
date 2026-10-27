import type { ChainEntry, Health, Run } from './types';
export async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) { let message = `Request failed (${response.status})`; try { message = (await response.json()).detail ?? message; } catch { /* static host */ } throw new Error(message); }
  return response.json() as Promise<T>;
}
export const getHealth = () => json<Health>('/api/health').catch(() => ({ replay_mode: true, live_configured: false, glimmer_configured: false }));
export const loadSample = (name: string) => json<Run>(`${import.meta.env.BASE_URL}samples/${name}.json`);
export function download(name: string, value: string, type = 'application/json') { const url = URL.createObjectURL(new Blob([value], { type })); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function sorted(value: unknown): unknown { if (Array.isArray(value)) return value.map(sorted); if (value !== null && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => [k, sorted(v)])); return value; }
export async function verifyChain(chain: ChainEntry[], expectedRoot: string): Promise<boolean> {
  let previous = '0'.repeat(64);
  for (const entry of chain) {
    const payload = { event: entry.event, evidence_sha256: entry.evidence_sha256, prev_hash: entry.prev_hash };
    if (entry.prev_hash !== previous || JSON.stringify(sorted(JSON.parse(entry.canonical_entry))) !== JSON.stringify(sorted(payload))) return false;
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(entry.canonical_entry));
    const hash = [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== entry.hash) return false;
    previous = hash;
  }
  return previous === expectedRoot;
}
