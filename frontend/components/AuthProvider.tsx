"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:4000";

type AuthState = {
  authenticated: boolean;
  authRequired: boolean;
  username: string | null;
  role: string | null;
  loading: boolean;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  authenticated: false,
  authRequired: false,
  username: null,
  role: null,
  loading: true,
  logout: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<AuthState, "logout" | "loading">>({
    authenticated: false,
    authRequired: false,
    username: null,
    role: null,
  });
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

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
        }
      } catch {
        // Server unreachable — allow access (dev mode)
      } finally {
        setLoading(false);
      }
    }

    checkAuth();
  }, [pathname, router]);

  async function logout() {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
    } catch {
      // ignore
    }
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

  return (
    <AuthContext.Provider value={{ ...state, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
