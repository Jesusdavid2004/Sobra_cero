"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { api, getToken, type User } from "../lib/api";

type Lang = "en" | "es";
type Theme = "light" | "dark";

const translations: Record<Lang, Record<string, string>> = { en, es };

type AppState = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Record<string, string>;
  theme: Theme;
  toggleTheme: () => void;
  token: string | null;
  user: User | null;
  login: (token: string) => void;
  logout: () => void;
};

const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used within AppProviders");
  return context;
}

export default function AppProviders({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("en");
  const [theme, setTheme] = useState<Theme>("light");
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [preferencesReady, setPreferencesReady] = useState(false);

  useEffect(() => {
    const storedLang = window.localStorage.getItem("sc_locale");
    const savedLang =
      storedLang === "en" || storedLang === "es"
        ? storedLang
        : navigator.language.toLowerCase().startsWith("es")
          ? "es"
          : "en";
    const storedTheme = window.localStorage.getItem("sc_theme");
    const legacyTheme = window.localStorage.getItem("theme");
    const savedTheme =
      storedTheme === "dark" || storedTheme === "light"
        ? storedTheme
        : legacyTheme === "dark" || legacyTheme === "light"
          ? legacyTheme
          : window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
    setLang(savedLang);
    setTheme(savedTheme);
    setToken(getToken());
    setPreferencesReady(true);
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
    }
  }, []);

  useEffect(() => {
    if (!preferencesReady) return;
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("sc_theme", theme);
  }, [preferencesReady, theme]);

  useEffect(() => {
    if (!preferencesReady) return;
    document.documentElement.lang = lang;
    window.localStorage.setItem("sc_locale", lang);
  }, [lang, preferencesReady]);

  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, [token]);

  const login = (nextToken: string) => {
    window.localStorage.setItem("token", nextToken);
    setToken(nextToken);
  };

  const logout = () => {
    window.localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AppContext.Provider
      value={{
        lang,
        setLang,
        t: translations[lang],
        theme,
        toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark"),
        token,
        user,
        login,
        logout,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
