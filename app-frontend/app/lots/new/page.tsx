"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import Header from "../../../components/Header";
import { api, type Product, type Shop } from "../../../lib/api";
import { compressImage } from "../../../lib/image";
import { useApp } from "../../../providers/AppProviders";

export default function NewLotPage() {
  return (
    <Suspense fallback={<p className="px-6 pt-12">…</p>}>
      <NewLotForm />
    </Suspense>
  );
}

function NewLotForm() {
  const { t, token, lang } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [shops, setShops] = useState<Shop[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [form, setForm] = useState({
    shopId: searchParams.get("shop") ?? "",
    productId: "",
    title: "",
    description: "",
    quantity: "1",
    original_price_cents: "1000",
    discount_percent: "30",
    expires_at: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) router.replace("/login");
    else
      api
        .shops()
        .then(setShops)
        .catch(() => setShops([]));
  }, [token, router]);

  const loadProducts = useCallback((shopId: string) => {
    if (!shopId) {
      setProducts([]);
      return;
    }
    api
      .shopProducts(Number(shopId))
      .then(setProducts)
      .catch(() => setProducts([]));
  }, []);

  useEffect(() => {
    if (form.shopId) loadProducts(form.shopId);
  }, [form.shopId, loadProducts]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const lot = await api.createLot({
        shop_id: Number(form.shopId),
        product_id: Number(form.productId),
        title: form.title,
        description: form.description,
        quantity: Number(form.quantity),
        original_price_cents: Number(form.original_price_cents),
        discount_percent: Number(form.discount_percent),
        expires_at: form.expires_at,
      });
      if (file) {
        const compressed = await compressImage(file);
        await api.uploadImage(lot.id, compressed);
      }
      setMessage(t.lotCreated);
      router.push(`/lots/${lot.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-2xl px-6 pb-12 pt-8">
        <h1 className="mb-8 text-3xl font-black">{t.lotTitle}</h1>
        {message ? (
          <p className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </p>
        ) : null}
        {error ? (
          <p className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : null}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="shop" className="mb-1 block text-sm font-semibold">
              {t.lotShop}
            </label>
            <select
              id="shop"
              required
              value={form.shopId}
              onChange={(e) => {
                setForm({ ...form, shopId: e.target.value, productId: "" });
              }}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            >
              <option value="">{t.lotShop}…</option>
              {shops.map((shop) => (
                <option key={shop.id} value={shop.id}>
                  {shop.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="product" className="mb-1 block text-sm font-semibold">
              {t.lotProduct}
            </label>
            <select
              id="product"
              required
              value={form.productId}
              onChange={(e) => setForm({ ...form, productId: e.target.value })}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            >
              <option value="">{t.lotProduct}…</option>
              {products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))}
            </select>
          </div>
          <input
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder={t.lotName}
            className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
          />
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder={t.lotDescription}
            rows={3}
            className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
          />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <input
              required
              type="number"
              min={1}
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              placeholder={t.lotQuantity}
              aria-label={t.lotQuantity}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
            <input
              required
              type="number"
              min={0}
              value={form.original_price_cents}
              onChange={(e) => setForm({ ...form, original_price_cents: e.target.value })}
              placeholder={t.lotPrice}
              aria-label={t.lotPrice}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
            <input
              required
              type="number"
              min={0}
              max={100}
              value={form.discount_percent}
              onChange={(e) => setForm({ ...form, discount_percent: e.target.value })}
              placeholder={t.lotDiscount}
              aria-label={t.lotDiscount}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
            <input
              required
              type="datetime-local"
              value={form.expires_at}
              onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
              aria-label={t.lotExpires}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
          </div>
          <div>
            <label htmlFor="image" className="mb-1 block text-sm font-semibold">
              {t.lotImage}
            </label>
            <input
              id="image"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
            <p className="mt-1 text-xs text-stone-500">{t.lotTakePhoto}</p>
          </div>
          <button
            type="submit"
            disabled={busy || !form.shopId || !form.productId || !lang}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {t.lotSubmit}
          </button>
        </form>
      </section>
    </main>
  );
}
