import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";

// Mock next/navigation before importing the component
const mockReplace = vi.fn();
const mockPathname = vi.fn(() => "/");
const mockRouter = { replace: mockReplace };

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  usePathname: () => mockPathname(),
}));

// Import after mock setup
import { AuthProvider, useAuth } from "../AuthProvider";

// Helper to consume the auth context in tests
function AuthConsumer() {
  const { authenticated, username, role, csrfToken, authRequired, loading, logout } = useAuth();
  return (
    <div>
      <span data-testid="authenticated">{String(authenticated)}</span>
      <span data-testid="username">{username ?? "null"}</span>
      <span data-testid="role">{role ?? "null"}</span>
      <span data-testid="csrf">{csrfToken ?? "null"}</span>
      <span data-testid="auth-required">{String(authRequired)}</span>
      <span data-testid="loading">{String(loading)}</span>
      <button data-testid="logout-btn" onClick={logout}>
        Logout
      </button>
    </div>
  );
}

function mockFetchResponses(authResponse: object, csrfResponse?: object) {
  (global.fetch as Mock).mockImplementation((url: string) => {
    if (url.includes("/api/auth/status")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(authResponse) });
    }
    if (url.includes("/api/csrf-token")) {
      if (csrfResponse) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(csrfResponse) });
      }
      return Promise.resolve({ ok: false });
    }
    if (url.includes("/api/auth/logout")) {
      return Promise.resolve({ ok: true });
    }
    return Promise.resolve({ ok: false });
  });
}

describe("AuthProvider", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
    mockReplace.mockClear();
    mockPathname.mockReturnValue("/");
  });

  it("shows loader while checking auth status", async () => {
    // fetch never resolves — component stays in loading state
    (global.fetch as Mock).mockReturnValue(new Promise(() => {}));

    const { container } = render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    // The loader div should be present, not the consumer
    expect(container.querySelector(".page-loader")).toBeTruthy();
    expect(screen.queryByTestId("authenticated")).toBeNull();
  });

  it("renders children when authenticated", async () => {
    mockFetchResponses(
      { authenticated: true, auth_required: true, username: "alice", role: "admin" },
      { csrf_token: "tok123" },
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    expect(screen.getByTestId("username")).toHaveTextContent("alice");
    expect(screen.getByTestId("role")).toHaveTextContent("admin");
    expect(screen.getByTestId("csrf")).toHaveTextContent("tok123");
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects to /login when auth required and not authenticated", async () => {
    mockFetchResponses({ authenticated: false, auth_required: true, username: null, role: null });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/login");
    });

    // Children should not render when auth required + unauthenticated + not on /login
    expect(screen.queryByTestId("authenticated")).toBeNull();
  });

  it("does not redirect when already on /login page", async () => {
    mockPathname.mockReturnValue("/login");
    mockFetchResponses({ authenticated: false, auth_required: true, username: null, role: null });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    });

    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("renders children when auth is not required", async () => {
    mockFetchResponses({ authenticated: false, auth_required: false, username: null, role: null });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    });

    expect(screen.getByTestId("auth-required")).toHaveTextContent("false");
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("handles network errors gracefully and still renders children", async () => {
    (global.fetch as Mock).mockRejectedValue(new Error("Network error"));

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    // Defaults remain — authRequired=false so children render
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });

  it("handles non-ok auth response gracefully", async () => {
    (global.fetch as Mock).mockResolvedValue({ ok: false });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("auth-required")).toHaveTextContent("false");
  });

  it("does not fetch CSRF token when not authenticated", async () => {
    mockFetchResponses({ authenticated: false, auth_required: false, username: null, role: null });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading")).toHaveTextContent("false");
    });

    const fetchCalls = (global.fetch as Mock).mock.calls;
    const csrfCalls = fetchCalls.filter(([url]: [string]) => url.includes("/api/csrf-token"));
    expect(csrfCalls).toHaveLength(0);
  });

  it("fetches CSRF token when authenticated", async () => {
    mockFetchResponses(
      { authenticated: true, auth_required: true, username: "alice", role: "admin" },
      { csrf_token: "tok-abc" },
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("csrf")).toHaveTextContent("tok-abc");
    });

    const fetchCalls = (global.fetch as Mock).mock.calls;
    const csrfCalls = fetchCalls.filter(([url]: [string]) => url.includes("/api/csrf-token"));
    expect(csrfCalls).toHaveLength(1);
  });

  it("provides a working logout function", async () => {
    mockFetchResponses(
      { authenticated: true, auth_required: true, username: "alice", role: "admin" },
      { csrf_token: "tok123" },
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("logout-btn"));
    });

    // After logout, state becomes authRequired=true + authenticated=false + pathname="/"
    // so the component renders null (guard on line 111). Verify the redirect was called
    // and the logout endpoint was hit.
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/login");
    });

    const fetchCalls = (global.fetch as Mock).mock.calls;
    const logoutCalls = fetchCalls.filter(([url]: [string]) => url.includes("/api/auth/logout"));
    expect(logoutCalls).toHaveLength(1);

    // Children are hidden because the auth guard renders null
    expect(screen.queryByTestId("authenticated")).toBeNull();
  });

  it("logout handles fetch errors gracefully", async () => {
    mockFetchResponses(
      { authenticated: true, auth_required: true, username: "alice", role: "admin" },
      { csrf_token: "tok123" },
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    // Make logout fetch fail
    (global.fetch as Mock).mockRejectedValue(new Error("Network error"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("logout-btn"));
    });

    // Even with a network error, logout resets state and redirects
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/login");
    });

    // Children hidden by auth guard (authRequired=true, authenticated=false, pathname="/")
    expect(screen.queryByTestId("authenticated")).toBeNull();
  });

  it("passes credentials: include to auth status and CSRF fetch calls", async () => {
    mockFetchResponses(
      { authenticated: true, auth_required: true, username: "alice", role: "admin" },
      { csrf_token: "tok123" },
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    const fetchCalls = (global.fetch as Mock).mock.calls;
    for (const [, options] of fetchCalls) {
      expect(options?.credentials).toBe("include");
    }
  });

  it("provides null username and role when server returns empty strings", async () => {
    mockFetchResponses({ authenticated: true, auth_required: true, username: "", role: "" }, { csrf_token: "tok" });

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    });

    // Empty strings get coerced to null via `|| null`
    expect(screen.getByTestId("username")).toHaveTextContent("null");
    expect(screen.getByTestId("role")).toHaveTextContent("null");
  });
});

describe("useAuth outside provider", () => {
  it("returns default context values when used outside AuthProvider", () => {
    function Bare() {
      const { authenticated, username, loading } = useAuth();
      return (
        <div>
          <span data-testid="auth">{String(authenticated)}</span>
          <span data-testid="user">{username ?? "null"}</span>
          <span data-testid="load">{String(loading)}</span>
        </div>
      );
    }

    render(<Bare />);
    expect(screen.getByTestId("auth")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("null");
    expect(screen.getByTestId("load")).toHaveTextContent("true");
  });
});
