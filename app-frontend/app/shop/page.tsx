"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import Header from "../../components/Header";
import { api, type Product, type Shop } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function ShopPage() {
  const { t, token } = useApp();
  const router = useRouter();
  const [shops, setShops] = useState<Shop[]>([]);
  const [products, setProducts] = useState<Record<number, Product[]>>({});
  const [error, setError] = useState("");
  const [shopForm, setShopForm] = useState({
    name: "",
    description: "",
    latitude: "",
    longitude: "",
  });
  const [productForm, setProductForm] = useState({ shopId: "", name: "", description: "" });

  const load = useCallback(() => {
    api
      .shops()
      .then(async (list) => {
        setShops(list);
        const productMap: Record<number, Product[]> = {};
        for (const shop of list) {
          productMap[shop.id] = await api.shopProducts(shop.id).catch(() => []);
        }
        setProducts(productMap);
      })
      .catch(() => setShops([]));
  }, []);

  useEffect(() => {
    if (!token) router.replace("/login");
    else load();
  }, [token, router, load]);

  const createShop = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api.createShop({
        name: shopForm.name,
        description: shopForm.description,
        latitude: Number(shopForm.latitude || 0),
        longitude: Number(shopForm.longitude || 0),
      });
      setShopForm({ name: "", description: "", latitude: "", longitude: "" });
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    }
  };

  const createProduct = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api.createProduct(Number(productForm.shopId), {
        name: productForm.name,
        description: productForm.description,
      });
      setProductForm({ shopId: productForm.shopId, name: "", description: "" });
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    }
  };

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-6xl px-6 pb-12 pt-8">
        <h1 className="mb-8 text-3xl font-black">{t.shopTitle}</h1>
        {error ? (
          <p className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : null}
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="rounded-3xl border border-stone-200 p-6 dark:border-stone-800">
            <h2 className="mb-4 text-xl font-bold">{t.createShop}</h2>
            <form onSubmit={createShop} className="space-y-3">
              <input
                required
                value={shopForm.name}
                onChange={(e) => setShopForm({ ...shopForm, name: e.target.value })}
                placeholder={t.shopName}
                className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
              />
              <input
                value={shopForm.description}
                onChange={(e) => setShopForm({ ...shopForm, description: e.target.value })}
                placeholder={t.shopDescription}
                className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  required
                  type="number"
                  step="any"
                  value={shopForm.latitude}
                  onChange={(e) => setShopForm({ ...shopForm, latitude: e.target.value })}
                  placeholder={t.shopLatitude}
                  className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
                />
                <input
                  required
                  type="number"
                  step="any"
                  value={shopForm.longitude}
                  onChange={(e) => setShopForm({ ...shopForm, longitude: e.target.value })}
                  placeholder={t.shopLongitude}
                  className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
                />
              </div>
              <button className="w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white hover:bg-emerald-700">
                {t.shopSubmit}
              </button>
            </form>
          </div>

          <div className="rounded-3xl border border-stone-200 p-6 dark:border-stone-800">
            <h2 className="mb-4 text-xl font-bold">{t.createProduct}</h2>
            <form onSubmit={createProduct} className="space-y-3">
              <select
                required
                value={productForm.shopId}
                onChange={(e) => setProductForm({ ...productForm, shopId: e.target.value })}
                className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
              >
                <option value="">{t.lotShop}…</option>
                {shops.map((shop) => (
                  <option key={shop.id} value={shop.id}>
                    {shop.name}
                  </option>
                ))}
              </select>
              <input
                required
                value={productForm.name}
                onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                placeholder={t.productName}
                className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
              />
              <input
                value={productForm.description}
                onChange={(e) => setProductForm({ ...productForm, description: e.target.value })}
                placeholder={t.productDescription}
                className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
              />
              <button className="w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white hover:bg-emerald-700">
                {t.productSubmit}
              </button>
            </form>
          </div>
        </div>

        <h2 className="mb-4 mt-12 text-2xl font-bold">{t.myShops}</h2>
        {shops.length ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {shops.map((shop) => (
              <article
                key={shop.id}
                className="rounded-3xl border border-stone-200 p-6 dark:border-stone-800"
              >
                <h3 className="text-lg font-bold">{shop.name}</h3>
                <p className="mt-1 text-sm text-stone-500">{shop.description}</p>
                <ul className="mt-4 space-y-1 text-sm">
                  {(products[shop.id] ?? []).map((product) => (
                    <li key={product.id}>• {product.name}</li>
                  ))}
                </ul>
                <Link
                  href={`/lots/new?shop=${shop.id}`}
                  className="mt-4 inline-block rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700"
                >
                  {t.newLot}
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <p className="text-stone-500">{t.noShops}</p>
        )}
      </section>
    </main>
  );
}
