"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Header from "../components/Header";
import { api, type Lot } from "../lib/api";
import { useApp } from "../providers/AppProviders";

export default function Home() {
  const { t, token } = useApp();
  const [lots, setLots] = useState<Lot[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const loadLots = () => {
    api
      .lots()
      .then(setLots)
      .catch(() => setLots([]));
  };

  useEffect(loadLots, []);

  const reserve = async (lotId: number) => {
    if (!token) return;
    setBusy(lotId);
    setMessage("");
    try {
      await api.reserve(lotId, 1);
      setMessage(t.detailReserved);
      loadLots();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.genericError);
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-6xl px-6 pb-12 pt-12">
        <div className="max-w-2xl">
          <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-orange-600">
            {t.eyebrow}
          </p>
          <h1 className="text-5xl font-black leading-tight md:text-7xl">{t.subtitle}</h1>
        </div>
        {message ? (
          <p className="mt-6 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </p>
        ) : null}
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {lots.length ? (
            lots.map((lot) => (
              <article
                key={lot.id}
                className="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900"
              >
                {lot.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={lot.image_url}
                    alt={lot.title}
                    className="mb-4 h-40 w-full rounded-2xl object-cover"
                  />
                ) : null}
                <div className="mb-4 flex items-start justify-between">
                  <span className="rounded-full bg-orange-100 px-3 py-1 text-xs font-bold text-orange-700">
                    {lot.discount_percent}% {t.discount}
                  </span>
                  <span className="text-sm text-stone-500">
                    {lot.quantity} {t.available}
                  </span>
                </div>
                <h2 className="text-xl font-bold">{lot.title}</h2>
                <p className="mt-2 min-h-12 text-sm text-stone-500">{lot.description}</p>
                <div className="mt-6 flex gap-2">
                  <Link
                    href={`/lots/${lot.id}`}
                    className="flex-1 rounded-xl border border-stone-300 px-4 py-3 text-center font-bold transition hover:border-emerald-500"
                  >
                    {t.viewDetail}
                  </Link>
                  {token ? (
                    <button
                      onClick={() => reserve(lot.id)}
                      disabled={busy === lot.id || lot.quantity === 0}
                      className="flex-1 rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {busy === lot.id ? "…" : t.reserve}
                    </button>
                  ) : null}
                </div>
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
