import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HomePage from "../app/page";

const createResponse = (data: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );

describe("Settings AI toggle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("disables AI summaries toggle when Ollama is unreachable", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/llm/health")) {
        return createResponse({ reachable: false });
      }
      return createResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<HomePage />);

    const [settingsButton] = screen.getAllByRole("button", { name: /Settings/i });
    fireEvent.click(settingsButton);

    const toggle = await screen.findByRole("checkbox", { name: /Enable AI summaries/i });
    await waitFor(() => {
      expect(toggle).toBeDisabled();
    });
  });

  it("enables AI summaries toggle when Ollama is reachable", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/llm/health")) {
        return createResponse({ reachable: true });
      }
      return createResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<HomePage />);

    const [settingsButton] = screen.getAllByRole("button", { name: /Settings/i });
    fireEvent.click(settingsButton);

    await screen.findByText(/Connected/i);
    const toggle = await screen.findByRole("checkbox", { name: /Enable AI summaries/i });
    await waitFor(() => {
      expect(toggle).not.toBeDisabled();
    });
  });
});
