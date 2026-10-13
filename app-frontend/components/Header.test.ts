import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockState = vi.hoisted(() => ({
  navigate: vi.fn(),
  value: {
    lang: "en" as const,
    setLang: vi.fn(),
    t: {
      title: "SobraCero",
      eyebrow: "Rescue today's food",
      mainNavigation: "Main navigation",
      navHome: "Home",
      themeLabel: "Toggle theme",
      themeMode: "Theme: {mode}",
      themeSystem: "system",
      themeDark: "dark",
      themeLight: "light",
      changeLanguage: "Change language",
      language: "Español",
      login: "Log in",
      logout: "Log out",
      genericError: "Something went wrong",
    },
    theme: "light" as const,
    themePreference: "system" as const,
    toggleTheme: vi.fn(),
    token: null as string | null,
    authReady: true,
    authError: false,
    user: null,
    login: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock("@/providers/AppProviders", () => ({
  useApp: () => mockState.value,
}));

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) =>
    createElement("a", { href }, children),
  usePathname: () => "/",
  useRouter: () => ({ push: mockState.navigate }),
}));

import Header from "./Header";

afterEach(() => cleanup());
beforeEach(() => vi.clearAllMocks());

describe("Header", () => {
  it("exposes language and theme controls", () => {
    render(createElement(Header));

    fireEvent.click(screen.getByRole("button", { name: "Toggle theme" }));
    fireEvent.click(screen.getByRole("button", { name: "Change language: Español" }));

    expect(mockState.value.toggleTheme).toHaveBeenCalledOnce();
    expect(mockState.value.setLang).toHaveBeenCalledWith("es");
  });

  it("logs out on the server before navigating away", async () => {
    mockState.value.token = "access-token";
    mockState.value.logout = vi.fn().mockResolvedValue(undefined);
    mockState.value.t.logout = "Log out";
    render(createElement(Header));

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(mockState.navigate).toHaveBeenCalledWith("/"));
    expect(mockState.value.logout).toHaveBeenCalledOnce();
  });

  it("shows an error when server logout fails", async () => {
    mockState.value.token = "access-token";
    mockState.value.logout = vi.fn().mockRejectedValue(new Error("network error"));
    mockState.value.t.logout = "Log out";
    mockState.navigate.mockClear();
    render(createElement(Header));

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(mockState.navigate).not.toHaveBeenCalled();
  });
});
