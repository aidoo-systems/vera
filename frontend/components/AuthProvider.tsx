"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { LICENSE_BLOCKED_EVENT, type LicenseBlockedDetail } from "../lib/api";
import { LicenseExpiredScreen, LicenseSoftBanner } from "./LicenseScreen";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:4000";

/** How often to poll /api/license/status while the app is open (ms). */
const LICENSE_POLL_INTERVAL_MS = 60_000;

export type EnforcementLevel = "grace" | "licensed" | "warning" | "soft" | "hard";

type AuthState = {
  authenticated: boolean;
  authRequired: boolean;
  username: string | null;
  role: string | null;
  loading: boolean;
  csrfToken: string | null;
  enforcement: EnforcementLevel | null;
  daysUntilExpiry: number | null;
  refreshCsrfToken: () => Promise<string | null>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  authenticated: false,
  authRequired: false,
  username: null,
  role: null,
  loading: true,
  csrfToken: null,
  enforcement: null,
  daysUntilExpiry: null,
  refreshCsrfToken: async () => null,
  logout: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<AuthState, "logout" | "loading" | "csrfToken" | "refreshCsrfToken" | "enforcement" | "daysUntilExpiry">>({
    authenticated: false,
    authRequired: false,
    username: null,
    role: null,
  });
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [enforcement, setEnforcement] = useState<EnforcementLevel | null>(null);
  const [daysUntilExpiry, setDaysUntilExpiry] = useState<number | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchCsrfToken(): Promise<string | null> {
    try {
      const resp = await fetch(`${API_BASE}/api/csrf-token`, { credentials: "include" });
      if (resp.ok) {
        const data = await resp.json();
        setCsrfToken(data.csrf_token);
        return data.csrf_token;
      }
    } catch {
      // ignore
    }
    return null;
  }

  async function fetchLicenseStatus(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/api/license/status`, { credentials: "include" });
      if (resp.ok) {
        const data = await resp.json();
        const level = (data.enforcement_level ?? null) as EnforcementLevel | null;
        if (level) setEnforcement(level);
        if (typeof data.days_until_expiry === "number") {
          setDaysUntilExpiry(data.days_until_expiry);
        }
      }
    } catch {
      // ignore — license status is best-effort, don't block the UI
    }
  }

  useEffect(() => {
    async function checkAuth() {
      try {
        const resp = await fetch(`${API_BASE}/api/auth/status`, { credentials: "include" });
        if (resp.ok) {
          const data = await resp.json();
          setState({
            authenticated: data.authenticated,
            authRequired: data.auth_required,
            username: data.username || null,
            role: data.role || null,
          });

          if (data.auth_required && !data.authenticated && pathname !== "/login") {
            router.replace("/login");
          }

          if (data.authenticated) {
            await fetchCsrfToken();
            // Fire-and-forget; license state populates as soon as Hub responds.
            void fetchLicenseStatus();
          }
        }
      } catch {
        // Server unreachable — allow access (dev mode)
      } finally {
        setLoading(false);
      }
    }

    checkAuth();
  }, [pathname, router]);

  // Poll license status while authenticated so the UI transitions *into* an
  // expired state without waiting for the next user-triggered call to fail.
  useEffect(() => {
    if (!state.authenticated) return;
    pollIntervalRef.current = setInterval(() => {
      void fetchLicenseStatus();
    }, LICENSE_POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [state.authenticated]);

  // Listen for license-blocked events dispatched by `apiFetch` in `lib/api.ts`.
  // Every fetch call that should be license-aware goes through apiFetch, which
  // fires this custom event on any 402 response. That lets the UI transition
  // *into* an expired state the moment a call fails, without waiting for the
  // poll interval to catch up.
  useEffect(() => {
    if (typeof window === "undefined") return;

    function handleBlocked(event: Event) {
      const detail = (event as CustomEvent<LicenseBlockedDetail>).detail;
      if (!detail) return;
      setEnforcement(detail.enforcement);
    }
    window.addEventListener(LICENSE_BLOCKED_EVENT, handleBlocked);
    return () => {
      window.removeEventListener(LICENSE_BLOCKED_EVENT, handleBlocked);
    };
  }, []);

  async function logout() {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
    } catch {
      // ignore
    }
    setCsrfToken(null);
    setEnforcement(null);
    setDaysUntilExpiry(null);
    setState({ authenticated: false, authRequired: true, username: null, role: null });
    router.replace("/login");
  }

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div className="page-loader active"><div className="page-loader-bar"></div></div>
      </div>
    );
  }

  // If auth required and not authenticated and not on login page, don't render children
  if (state.authRequired && !state.authenticated && pathname !== "/login") {
    return null;
  }

  // Hard enforcement — full-screen lockdown. Login page is exempt so the user
  // can still sign out / sign in with different credentials.
  if (state.authenticated && enforcement === "hard" && pathname !== "/login") {
    return (
      <AuthContext.Provider
        value={{ ...state, loading, csrfToken, enforcement, daysUntilExpiry, refreshCsrfToken: fetchCsrfToken, logout }}
      >
        <LicenseExpiredScreen onLogout={logout} />
      </AuthContext.Provider>
    );
  }

  return (
    <AuthContext.Provider
      value={{ ...state, loading, csrfToken, enforcement, daysUntilExpiry, refreshCsrfToken: fetchCsrfToken, logout }}
    >
      {state.authenticated && enforcement === "soft" && (
        <LicenseSoftBanner daysRemaining={daysUntilExpiry} />
      )}
      {children}
    </AuthContext.Provider>
  );
}
