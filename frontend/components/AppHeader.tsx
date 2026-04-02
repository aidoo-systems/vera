"use client";

import { useAuth } from "./AuthProvider";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  const { authenticated, username, logout } = useAuth();

  if (!authenticated) return null;

  return (
    <header className="header">
      <div className="header-left">
        <a href="/" className="logo">VERA</a>
        <span className="header-divider">/</span>
        <span className="header-title">Documents</span>
      </div>
      <div className="header-right">
        <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          {username}
        </span>
        <ThemeToggle />
        <button onClick={logout} className="btn btn-ghost" style={{ fontSize: "0.8125rem" }}>
          Sign out
        </button>
      </div>
    </header>
  );
}
