/** Format cents as ¥X.XX */
export function fmtAmount(cents: number): string {
  return `¥${(Math.abs(cents) / 100).toFixed(2)}`;
}

/** Format cents as short string: ¥1.2k */
export function fmtAmountShort(cents: number): string {
  const yuan = Math.abs(cents) / 100;
  if (yuan >= 10000) return `¥${(yuan / 10000).toFixed(1)}万`;
  if (yuan >= 1000) return `¥${(yuan / 1000).toFixed(1)}k`;
  return `¥${yuan.toFixed(2)}`;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function fmtDateFull(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ');
}

export function fmtPct(pct: number | undefined): string {
  return pct !== undefined ? `${(pct * 100).toFixed(0)}%` : '—';
}

/** YYYY-MM → { start: 'YYYY-MM-01', end: 'YYYY-MM-DD' } */
export function monthRange(ym: string): { start: string; end: string } {
  const [y, m] = ym.split('-').map(Number);
  const last = new Date(y, m, 0).getDate();
  return {
    start: `${ym}-01`,
    end: `${ym}-${String(last).padStart(2, '0')}`,
  };
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Simple SHA-256 via SubtleCrypto (available in Hermes / JSC via polyfill) */
export async function sha256(text: string): Promise<string> {
  // React Native doesn't have SubtleCrypto; use djb2 as lightweight hash for dedup
  let hash = 5381;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) + hash) ^ text.charCodeAt(i);
    hash = hash >>> 0; // unsigned
  }
  return hash.toString(16).padStart(8, '0');
}

export async function fileHash(content: string): Promise<string> {
  // Use length + first 512 + last 512 chars as fingerprint (fast, good enough for dedup)
  const sig = `${content.length}|${content.slice(0, 512)}|${content.slice(-512)}`;
  return sha256(sig);
}
