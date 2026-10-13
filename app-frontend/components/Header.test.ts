import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    },
    theme: "light" as const,
    themePreference: "system" as const,
    toggleTheme: vi.fn(),
    token: null,
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

describe("Header", () => {
  it("exposes language and theme controls", () => {
    render(createElement(Header));

    fireEvent.click(screen.getByRole("button", { name: "Toggle theme" }));
    fireEvent.click(screen.getByRole("button", { name: "Change language: Español" }));

    expect(mockState.value.toggleTheme).toHaveBeenCalledOnce();
    expect(mockState.value.setLang).toHaveBeenCalledWith("es");
  });
});
