"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Header from "../../components/Header";
import { api, type Lot, type Promotion } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function LotsPage() {
  const { t, lang } = useApp();
  const [lots, setLots] = useState<Lot[]>([]);
  const [promotions, setPromotions] = useState<Record<number, Promotion[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [category, setCategory] = useState("");
  const [businessType, setBusinessType] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .lots({
        category: category || undefined,
        business_type: businessType || undefined,
      })
      .then(async (availableLots) => {
        const promotionEntries = await Promise.all(
          availableLots.map(async (lot) => [lot.id, await api.promos(lot.id)] as const),
        );
        if (!cancelled) {
          setLots(availableLots);
          setPromotions(Object.fromEntries(promotionEntries));
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : t.genericError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [category, businessType, t.genericError]);

  const currency = new Intl.NumberFormat(lang === "es" ? "es-CO" : "en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
  const categoryTranslations: Record<string, string> = {
    produce: t.categoryProduce,
    bakery: t.categoryBakery,
    dairy: t.categoryDairy,
    meat: t.categoryMeat,
    prepared: t.categoryPrepared,
    pantry: t.categoryPantry,
    other: t.categoryOther,
  };

  return (
    <main className="min-h-screen bg-[#f5f3ee] text-[#1f2a1f]">
      <Header />
      <section className="mx-auto max-w-6xl px-6 pb-16 pt-8">
        <div className="mb-8 rounded-[28px] bg-[#bfe09a] px-6 py-8 shadow-[0_7px_0_#3b422c] md:px-10">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#49633b]">
            {t.marketEyebrow}
          </p>
          <h1 className="mt-2 text-3xl font-black md:text-5xl">{t.marketTitle}</h1>
          <p className="mt-3 max-w-2xl text-[#34442d]">{t.marketDescription}</p>
        </div>

        <div className="mb-6 grid gap-3 rounded-2xl border border-[#e3e5dc] bg-white p-4 sm:grid-cols-2">
          <label className="text-sm font-bold">
            <span className="mb-2 block text-stone-600">{t.filterBusinesses}</span>
            <select
              value={businessType}
              onChange={(event) => setBusinessType(event.target.value)}
              className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3"
            >
              <option value="">{t.filterAllBusinesses}</option>
              <option value="restaurant">{t.restaurant}</option>
              <option value="supermarket">{t.supermarket}</option>
            </select>
          </label>
          <label className="text-sm font-bold">
            <span className="mb-2 block text-stone-600">{t.filterCategories}</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3"
            >
              <option value="">{t.filterAllCategories}</option>
              <option value="produce">{t.categoryProduce}</option>
              <option value="bakery">{t.categoryBakery}</option>
              <option value="dairy">{t.categoryDairy}</option>
              <option value="meat">{t.categoryMeat}</option>
              <option value="prepared">{t.categoryPrepared}</option>
              <option value="pantry">{t.categoryPantry}</option>
              <option value="other">{t.categoryOther}</option>
            </select>
          </label>
        </div>

        {error ? (
          <p role="alert" className="rounded-2xl bg-red-50 px-5 py-4 text-red-700">
            {lang === "es"
              ? `No se pudieron cargar los lotes. Verifica que el backend esté iniciado. (${error})`
              : `Could not load food lots. Check that the backend is running. (${error})`}
          </p>
        ) : loading ? (
          <p className="py-8 text-stone-600">{t.marketLoading}</p>
        ) : lots.length === 0 ? (
          <div className="rounded-2xl border border-[#d9dfce] bg-white/80 px-5 py-8 text-center">
            <p className="text-lg font-bold">
              {category || businessType ? t.filterNoResults : t.empty}
            </p>
            <p className="mt-2 text-stone-600">{t.marketEmptyDescription}</p>
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {lots.map((lot) => {
              const currentPrice = (lot.original_price_cents * (100 - lot.discount_percent)) / 100;
              const lotPromotions = promotions[lot.id] ?? [];

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
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-[#627158]">
                      <span className="rounded-full bg-[#f3f5ef] px-3 py-1">
                        {categoryTranslations[lot.category] ?? lot.category}
                      </span>
                      <span className="rounded-full bg-[#f3f5ef] px-3 py-1">
                        {lot.business_type === "restaurant" ? t.restaurant : t.supermarket}
                      </span>
                    </div>
                    <h2 className="mt-4 text-xl font-black">{lot.title}</h2>
                    <p className="mt-2 min-h-10 text-sm text-stone-600">{lot.description}</p>
                    {lotPromotions.length ? (
                      <p className="mt-3 rounded-xl bg-[#f4f7f0] p-3 text-sm italic leading-6 text-[#42533d]">
                        “{lotPromotions[0].text}”
                      </p>
                    ) : null}
                    <div className="mt-4 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-[#426431]">
                        {currency.format(currentPrice / 100)}
                      </span>
                      <span className="text-sm text-stone-400 line-through">
                        {currency.format(lot.original_price_cents / 100)}
                      </span>
                    </div>
                    <Link
                      href={`/lots/${lot.id}`}
                      className="mt-5 block rounded-xl bg-[#33452b] px-4 py-3 text-center font-bold text-white transition hover:bg-[#263820]"
                    >
                      {t.viewAndReserve}
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
