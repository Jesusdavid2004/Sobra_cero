"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Header from "../../../components/Header";
import { api, type Lot, type Promotion } from "../../../lib/api";
import { useApp } from "../../../providers/AppProviders";

export default function LotDetailPage() {
  const { t, token, lang } = useApp();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const lotId = Number(params?.id);
  const [lot, setLot] = useState<Lot | null>(null);
  const [promos, setPromos] = useState<Promotion[]>([]);
  const [quantity, setQuantity] = useState("1");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [lotData, promosData] = await Promise.all([api.lot(lotId), api.promos(lotId)]);
      setLot(lotData);
      setPromos(promosData);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    }
  };

  useEffect(() => {
    if (lotId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotId]);

  const reserve = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) {
      router.push("/login");
      return;
    }
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await api.reserve(lotId, Number(quantity));
      setMessage(t.detailReserved);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await api.generatePromos(lotId, lang);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    } finally {
      setBusy(false);
    }
  };

  if (!lot) {
    return (
      <main className="min-h-screen">
        <Header />
        <p className="px-6 pt-12 text-stone-500">{error || "…"}</p>
      </main>
    );
  }

  const finalPrice = (lot.original_price_cents * (100 - lot.discount_percent)) / 100;

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-3xl px-6 pb-12 pt-8">
        {lot.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={lot.image_url}
            alt={lot.title}
            className="mb-6 h-64 w-full rounded-3xl object-cover"
          />
        ) : null}
        <h1 className="text-4xl font-black">{lot.title}</h1>
        <p className="mt-2 text-stone-500">{lot.description}</p>
        <div className="mt-6 flex flex-wrap gap-3 text-sm">
          <span className="rounded-full bg-orange-100 px-3 py-1 font-bold text-orange-700">
            {lot.discount_percent}% {t.discount}
          </span>
          <span className="rounded-full bg-stone-100 px-3 py-1 dark:bg-stone-800">
            {lot.quantity} {t.detailQuantity}
          </span>
          <span className="rounded-full bg-stone-100 px-3 py-1 dark:bg-stone-800">
            {t.detailExpires}:{" "}
            {new Date(lot.expires_at).toLocaleString(lang === "es" ? "es-CO" : "en-US")}
          </span>
        </div>
        <p className="mt-4 text-2xl font-bold text-emerald-600">
          ${(finalPrice / 100).toFixed(2)}
          <span className="ml-2 text-base font-normal text-stone-400 line-through">
            ${(lot.original_price_cents / 100).toFixed(2)}
          </span>
        </p>

        {message ? (
          <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : null}

        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <form
            onSubmit={reserve}
            className="rounded-3xl border border-stone-200 p-6 dark:border-stone-800"
          >
            <h2 className="mb-4 text-xl font-bold">{t.reserve}</h2>
            <label htmlFor="quantity" className="mb-1 block text-sm font-semibold">
              {t.detailReserveQuantity}
            </label>
            <input
              id="quantity"
              type="number"
              min={1}
              max={lot.quantity}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
            <button
              type="submit"
              disabled={busy || lot.quantity === 0}
              className="mt-4 w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {t.detailReserveSubmit}
            </button>
          </form>

          <div className="rounded-3xl border border-stone-200 p-6 dark:border-stone-800">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold">{t.detailPromos}</h2>
              {token ? (
                <button
                  onClick={generate}
                  disabled={busy}
                  className="rounded-xl bg-orange-500 px-3 py-2 text-sm font-bold text-white hover:bg-orange-600 disabled:opacity-50"
                >
                  {t.detailGeneratePromos}
                </button>
              ) : null}
            </div>
            {promos.length ? (
              <ul className="mt-4 space-y-3">
                {promos.map((promo) => (
                  <li
                    key={promo.id}
                    className="rounded-xl bg-stone-100 p-4 text-sm dark:bg-stone-800"
                  >
                    <p className="font-semibold text-orange-600">{promo.variant}</p>
                    <p className="mt-1">{promo.text}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-stone-500">{t.detailNoPromos}</p>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
