"use client";

import { useAuth } from "./AuthProvider";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  const { authenticated, username, logout } = useAuth();

  if (!authenticated) return null;

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: "0.75rem",
        padding: "0.5rem 1.5rem",
        borderBottom: "1px solid var(--border-primary)",
        background: "var(--bg-primary)",
      }}
    >
      <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginRight: "auto" }}>
        {username}
      </span>
      <ThemeToggle />
      <button
        onClick={logout}
        style={{
          background: "none",
          border: "1px solid var(--border-primary)",
          borderRadius: "6px",
          padding: "0.375rem 0.75rem",
          cursor: "pointer",
          fontSize: "0.8125rem",
          color: "var(--text-secondary)",
        }}
      >
        Logout
      </button>
    </header>
  );
}
