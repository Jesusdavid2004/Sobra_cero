"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Header from "../../components/Header";
import { api, type Lot } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function LotsPage() {
  const { t, lang } = useApp();
  const [lots, setLots] = useState<Lot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .lots()
      .then(setLots)
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : t.genericError);
      })
      .finally(() => setLoading(false));
  }, [t.genericError]);

  return (
    <main className="min-h-screen bg-[#f5f3ee] text-[#1f2a1f]">
      <Header />
      <section className="mx-auto max-w-6xl px-6 pb-16 pt-8">
        <div className="mb-8 rounded-[28px] bg-[#bfe09a] px-6 py-8 shadow-[0_7px_0_#3b422c] md:px-10">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#49633b]">
            {lang === "es" ? "Rescata algo rico hoy" : "Rescue something delicious today"}
          </p>
          <h1 className="mt-2 text-3xl font-black md:text-5xl">
            {lang === "es" ? "Comida buena, precio especial" : "Good food, special prices"}
          </h1>
          <p className="mt-3 max-w-2xl text-[#34442d]">
            {lang === "es"
              ? "Explora los lotes disponibles cerca de ti y reserva tus favoritos antes de que se agoten."
              : "Browse available food lots and reserve your favorites before they are gone."}
          </p>
        </div>

        {error ? (
          <p role="alert" className="rounded-2xl bg-red-50 px-5 py-4 text-red-700">
            {lang === "es"
              ? `No se pudieron cargar los lotes. Verifica que el backend esté iniciado. (${error})`
              : `Could not load food lots. Check that the backend is running. (${error})`}
          </p>
        ) : loading ? (
          <p className="py-8 text-stone-600">
            {lang === "es" ? "Cargando comida disponible..." : "Loading available food..."}
          </p>
        ) : lots.length === 0 ? (
          <div className="rounded-2xl border border-[#d9dfce] bg-white/80 px-5 py-8 text-center">
            <p className="text-lg font-bold">{t.empty}</p>
            <p className="mt-2 text-stone-600">
              {lang === "es"
                ? "Vuelve pronto; las tiendas agregan nuevos lotes durante el día."
                : "Check back soon; shops add new lots throughout the day."}
            </p>
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {lots.map((lot) => {
              const currentPrice = (lot.original_price_cents * (100 - lot.discount_percent)) / 100;

              return (
                <article
                  key={lot.id}
                  className="overflow-hidden rounded-[26px] border border-[#e3e5dc] bg-white shadow-[0_12px_30px_rgba(42,55,32,0.08)]"
                >
                  {lot.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={lot.image_url} alt={lot.title} className="h-52 w-full object-cover" />
                  ) : (
                    <div
                      aria-hidden="true"
                      className="flex h-52 items-center justify-center bg-[#eaf2df] text-6xl"
                    >
                      🥬
                    </div>
                  )}
                  <div className="p-5">
                    <div className="flex items-center justify-between gap-3">
                      <span className="rounded-full bg-[#eaf4dd] px-3 py-1 text-sm font-bold text-[#426431]">
                        {lot.discount_percent}% {t.discount}
                      </span>
                      <span className="text-sm text-stone-600">
                        {lot.quantity} {t.available}
                      </span>
                    </div>
                    <h2 className="mt-4 text-xl font-black">{lot.title}</h2>
                    <p className="mt-2 min-h-10 text-sm text-stone-600">{lot.description}</p>
                    <div className="mt-4 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-[#426431]">
                        ${(currentPrice / 100).toFixed(2)}
                      </span>
                      <span className="text-sm text-stone-400 line-through">
                        ${(lot.original_price_cents / 100).toFixed(2)}
                      </span>
                    </div>
                    <Link
                      href={`/lots/${lot.id}`}
                      className="mt-5 block rounded-xl bg-[#33452b] px-4 py-3 text-center font-bold text-white transition hover:bg-[#263820]"
                    >
                      {lang === "es" ? "Ver y reservar" : "View and reserve"}
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
