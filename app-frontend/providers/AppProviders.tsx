"use client";

import { useLocale, useTranslations } from "next-intl";
import { ThemeProvider, useTheme } from "next-themes";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import { api, setAccessToken, subscribeToAccessToken, type User } from "@/lib/api";
import { nextThemePreference, type ThemePreference } from "@/lib/theme-preference";

type Lang = "en" | "es";
type Theme = "light" | "dark";
const dictionaries: Record<Lang, Record<string, string>> = { en, es };

type AppState = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Record<string, string>;
  theme: Theme;
  themePreference: ThemePreference;
  toggleTheme: () => void;
  token: string | null;
  authReady: boolean;
  authError: boolean;
  user: User | null;
  login: (token: string) => void;
  logout: () => Promise<void>;
};

const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used within AppProviders");
  return context;
}

export default function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem storageKey="sc_theme">
      <AppStateProvider>{children}</AppStateProvider>
    </ThemeProvider>
  );
}

function AppStateProvider({ children }: { children: ReactNode }) {
  const requestedLocale = useLocale();
  if (requestedLocale !== "en" && requestedLocale !== "es") {
    throw new Error(`Unsupported locale: ${requestedLocale}`);
  }
  const locale: Lang = requestedLocale;
  const translate = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const { resolvedTheme, theme: configuredTheme, setTheme } = useTheme();
  const [token, setToken] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  const t = useMemo(
    () =>
      new Proxy<Record<string, string>>(
        {},
        {
          get: (_target, property) => {
            if (typeof property !== "string") return undefined;
            const message = dictionaries[locale][property];
            if (typeof message !== "string") return undefined;
            const values = Object.fromEntries(
              [...message.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map((match) => [
                match[1],
                match[0],
              ]),
            );
            return translate(property, values);
          },
        },
      ),
    [locale, translate],
  );

  useEffect(() => {
    const unsubscribe = subscribeToAccessToken((nextToken) => {
      setToken(nextToken);
      if (!nextToken) setUser(null);
      else setAuthError(false);
    });
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
    }
    let mounted = true;
    api
      .refresh()
      .catch(() => {
        if (mounted) setAuthError(true);
      })
      .finally(() => {
        if (mounted) setAuthReady(true);
      });
    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

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
    setAccessToken(nextToken);
    setUser(null);
    setAuthReady(true);
    setAuthError(false);
  };

  const logout = async () => {
    await api.logout();
  };

  const themePreference: ThemePreference =
    configuredTheme === "light" || configuredTheme === "dark" ? configuredTheme : "system";

  return (
    <AppContext.Provider
      value={{
        lang: locale,
        setLang: (nextLocale) => router.replace(pathname, { locale: nextLocale }),
        t,
        theme: resolvedTheme === "dark" ? "dark" : "light",
        themePreference,
        toggleTheme: () => setTheme(nextThemePreference(themePreference)),
        token,
        authReady,
        authError,
        user,
        login,
        logout,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
