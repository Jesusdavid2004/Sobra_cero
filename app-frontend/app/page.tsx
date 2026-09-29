"use client";
import { useEffect, useState } from "react";
import en from "../i18n/en.json";
import es from "../i18n/es.json";

type Lot = {
  id: number;
  title: string;
  description: string;
  quantity: number;
  original_price_cents: number;
  discount_percent: number;
  expires_at: string;
};
const translations = { en, es };

export default function Home() {
  const [language, setLanguage] = useState<"en" | "es">("en");
  const [dark, setDark] = useState(false);
  const [lots, setLots] = useState<Lot[]>([]);
  const t = translations[language];
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/lots`)
      .then((response) => (response.ok ? response.json() : []))
      .then(setLots)
      .catch(() => setLots([]));
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div>
          <p className="text-2xl font-black tracking-tight text-emerald-600">{t.title}</p>
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">{t.eyebrow}</p>
        </div>
        <nav className="flex gap-2">
          <button
            aria-label={t.themeLabel}
            onClick={() => setDark(!dark)}
            className="rounded-full border px-3 py-2 text-sm"
          >
            {dark ? "☀" : "☾"}
          </button>
          <button
            onClick={() => setLanguage(language === "en" ? "es" : "en")}
            className="rounded-full border px-3 py-2 text-sm"
          >
            {t.language}
          </button>
        </nav>
      </header>
      <section className="mx-auto max-w-6xl px-6 pb-12 pt-12">
        <div className="max-w-2xl">
          <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-orange-600">
            {t.eyebrow}
          </p>
          <h1 className="text-5xl font-black leading-tight md:text-7xl">{t.subtitle}</h1>
        </div>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {lots.length ? (
            lots.map((lot) => (
              <article
                key={lot.id}
                className="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900"
              >
                <div className="mb-8 flex items-start justify-between">
                  <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-bold text-orange-700">
                    {lot.discount_percent}% {t.discount}
                  </span>
                  <span className="text-sm text-stone-500">
                    {lot.quantity} {t.available}
                  </span>
                </div>
                <h2 className="text-xl font-bold">{lot.title}</h2>
                <p className="mt-2 min-h-12 text-sm text-stone-500">{lot.description}</p>
                <button className="mt-6 w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white transition hover:bg-emerald-700">
                  {t.reserve}
                </button>
              </article>
            ))
          ) : (
            <p className="text-stone-500">{t.empty}</p>
          )}
        </div>
      </section>
    </main>
  );
}
