/**
 * Central API helpers.
 *
 * `apiFetch` is a thin wrapper around `fetch` that:
 *   - prepends the API base URL (so call sites can pass `/documents/...`)
 *   - always sends credentials
 *   - dispatches a `vera:license-blocked` custom event on a 402 response
 *     so AuthProvider can surface the license screen
 *
 * Existing call sites in `app/page.tsx` still use raw `fetch(...)`; AuthProvider
 * also installs a global `window.fetch` wrapper as a safety net so those calls
 * benefit from 402 handling without being rewritten.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:4000";

export const LICENSE_BLOCKED_EVENT = "vera:license-blocked";

export type LicenseBlockedDetail = {
  /** "soft" or "hard" — inferred from the 402 response body if available */
  enforcement: "soft" | "hard";
  message?: string;
};

/** Dispatch a license-blocked event. Safe to call from any fetch wrapper. */
export function notifyLicenseBlocked(detail: LicenseBlockedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<LicenseBlockedDetail>(LICENSE_BLOCKED_EVENT, { detail }));
}

/** Parse a 402 response body to decide soft vs hard. Best-effort; defaults to "hard". */
export async function inferEnforcementFrom402(response: Response): Promise<"soft" | "hard"> {
  try {
    const clone = response.clone();
    const data = await clone.json();
    const detail = typeof data?.detail === "string" ? data.detail.toLowerCase() : "";
    if (detail.includes("read-only")) return "soft";
  } catch {
    // body already consumed or not JSON — fall through
  }
  return "hard";
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, { credentials: "include", ...init });
  if (response.status === 402) {
    const enforcement = await inferEnforcementFrom402(response);
    notifyLicenseBlocked({ enforcement });
  }
  return response;
}
