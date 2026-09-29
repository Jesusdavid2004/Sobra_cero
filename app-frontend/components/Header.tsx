"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useApp } from "../providers/AppProviders";

export default function Header() {
  const { t, lang, setLang, theme, toggleTheme, token, user, logout } = useApp();
  const router = useRouter();
  const pathname = usePathname();

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-6">
      <Link href="/" className="leading-tight">
        <p className="text-2xl font-black tracking-tight text-emerald-600">{t.title}</p>
        <p className="text-xs uppercase tracking-[0.2em] text-stone-500">{t.eyebrow}</p>
      </Link>
      <nav className="flex flex-wrap items-center gap-2" aria-label="Main">
        <Link
          href="/"
          className={`rounded-full border px-3 py-2 text-sm ${pathname === "/" ? "border-emerald-500 text-emerald-600" : ""}`}
        >
          {t.navHome}
        </Link>
        {token ? (
          <>
            <Link
              href="/shop"
              className={`rounded-full border px-3 py-2 text-sm ${pathname === "/shop" ? "border-emerald-500 text-emerald-600" : ""}`}
            >
              {t.shop}
            </Link>
            <Link
              href="/lots/new"
              className={`rounded-full border px-3 py-2 text-sm ${pathname === "/lots/new" ? "border-emerald-500 text-emerald-600" : ""}`}
            >
              {t.newLot}
            </Link>
            {user?.is_admin ? (
              <Link href="/admin" className="rounded-full border px-3 py-2 text-sm">
                {t.admin}
              </Link>
            ) : null}
            <button onClick={handleLogout} className="rounded-full border px-3 py-2 text-sm">
              {t.logout}
            </button>
          </>
        ) : (
          <Link href="/login" className="rounded-full border px-3 py-2 text-sm">
            {t.login}
          </Link>
        )}
        <button
          aria-label={t.themeLabel}
          onClick={toggleTheme}
          className="rounded-full border px-3 py-2 text-sm"
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
        <button
          onClick={() => setLang(lang === "en" ? "es" : "en")}
          className="rounded-full border px-3 py-2 text-sm"
        >
          {t.language}
        </button>
      </nav>
    </header>
  );
}