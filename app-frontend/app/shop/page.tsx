"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import Header from "../../components/Header";
import { ApiError, api, type Product, type Shop, type WasteRisk } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function ShopPage() {
  const { t, token, lang, user } = useApp();
  const router = useRouter();
  const [shops, setShops] = useState<Shop[]>([]);
  const [products, setProducts] = useState<Record<number, Product[]>>({});
  const [selectedShopId, setSelectedShopId] = useState("");
  const [risk, setRisk] = useState<WasteRisk[]>([]);
  const [riskError, setRiskError] = useState("");
  const [riskErrorStatus, setRiskErrorStatus] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [riskLoading, setRiskLoading] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [riskRevision, setRiskRevision] = useState(0);
  const [shopForm, setShopForm] = useState({
    name: "",
    description: "",
    latitude: "",
    longitude: "",
    business_type: "restaurant" as "restaurant" | "supermarket",
  });
  const [productForm, setProductForm] = useState({
    shopId: "",
    name: "",
    description: "",
    category: "other",
  });

  const selectedShop = shops.find((shop) => String(shop.id) === selectedShopId) ?? null;
  const formatter = useMemo(
    () => new Intl.NumberFormat(lang === "es" ? "es-CO" : "en-US", { maximumFractionDigits: 1 }),
    [lang],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await api.shops();
      const productEntries = await Promise.all(
        list.map(async (shop) => [shop.id, await api.shopProducts(shop.id)] as const),
      );
      setShops(list);
      setProducts(Object.fromEntries(productEntries));
      setSelectedShopId((current) =>
        list.some((shop) => String(shop.id) === current) ? current : String(list[0]?.id ?? ""),
      );
      setProductForm((current) => ({
        ...current,
        shopId: list.some((shop) => String(shop.id) === current.shopId)
          ? current.shopId
          : String(list[0]?.id ?? ""),
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    } finally {
      setLoading(false);
    }
  }, [t.genericError]);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user?.role === "customer") {
      router.replace("/lots");
      return;
    }
    if (!user) return;
    void load();
  }, [token, user, router, load]);

  useEffect(() => {
    if (!selectedShopId) {
      setRisk([]);
      setRiskError("");
      return;
    }
    let cancelled = false;
    setRiskLoading(true);
    setRiskError("");
    setRiskErrorStatus(null);
    api
      .wasteRisk(Number(selectedShopId), lang)
      .then((results) => {
        if (!cancelled) setRisk(results);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setRisk([]);
          setRiskError(cause instanceof Error ? cause.message : t.genericError);
          setRiskErrorStatus(cause instanceof ApiError ? cause.status : null);
        }
      })
      .finally(() => {
        if (!cancelled) setRiskLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedShopId, lang, riskRevision, t.genericError]);

  const createShop = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      const shop = await api.createShop({
        name: shopForm.name,
        business_type: shopForm.business_type,
        description: shopForm.description,
        latitude: Number(shopForm.latitude || 0),
        longitude: Number(shopForm.longitude || 0),
      });
      setShopForm({
        name: "",
        description: "",
        latitude: "",
        longitude: "",
        business_type: "restaurant",
      });
      setSelectedShopId(String(shop.id));
      setProductForm((current) => ({ ...current, shopId: String(shop.id) }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    }
  };

  const createProduct = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api.createProduct(Number(productForm.shopId), {
        name: productForm.name,
        description: productForm.description,
        category: productForm.category,
      });
      setProductForm((current) => ({ ...current, name: "", description: "" }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    }
  };

  const loadSampleHistory = async () => {
    if (!selectedShopId) return;
    setSampleLoading(true);
    setError("");
    setNotice("");
    try {
      await api.loadSampleSalesHistory(Number(selectedShopId));
      setNotice(t.dashboardSampleLoaded);
      setRiskRevision((revision) => revision + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.dashboardSampleDataError);
    } finally {
      setSampleLoading(false);
    }
  };

  const totalAtRisk = risk.reduce((total, item) => total + item.units_at_risk, 0);
  const averageDailySales = risk.length
    ? risk.reduce((total, item) => total + item.average_daily_sales, 0) / risk.length
    : 0;
  const highRiskLots = risk.filter((item) => item.risk_score >= 70).length;

  return (
    <main className="min-h-screen bg-[#f5f6f1] text-[#1e2b22]">
      <Header />
      <section className="mx-auto max-w-7xl px-5 pb-14 pt-4 md:px-8">
        <div className="relative overflow-hidden rounded-[32px] bg-[#203a2c] px-6 py-8 text-white md:px-10 md:py-10">
          <div
            aria-hidden="true"
            className="absolute -right-16 -top-24 h-72 w-72 rounded-full border-[36px] border-[#a9ce81]/15"
          />
          <div className="relative flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="max-w-2xl">
              <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#c7e5a8]">
                {t.title} / {t.shop}
              </p>
              <h1 className="mt-3 text-3xl font-black tracking-tight md:text-5xl">
                {t.dashboardWelcome}
              </h1>
              <p className="mt-3 max-w-xl leading-7 text-white/75">{t.dashboardDescription}</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/lots"
                className="rounded-full border border-white/25 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10"
              >
                {t.navHome}
              </Link>
              {selectedShopId ? (
                <Link
                  href={`/lots/new?shop=${selectedShopId}`}
                  className="rounded-full bg-[#d1eeac] px-5 py-3 text-sm font-black text-[#203a2c] transition hover:bg-white"
                >
                  + {t.newLot}
                </Link>
              ) : null}
            </div>
          </div>
        </div>

        {error ? (
          <p role="alert" className="mt-5 rounded-2xl bg-red-50 px-5 py-4 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p
            role="status"
            className="mt-5 rounded-2xl bg-[#e8f4db] px-5 py-4 text-sm text-[#365d2f]"
          >
            {notice}
          </p>
        ) : null}

        {loading ? (
          <p className="py-12 text-stone-600">{t.dashboardLoadingRisk}</p>
        ) : (
          <>
            {!shops.length ? (
              <div className="mt-7 rounded-3xl border border-[#e0e5da] bg-white p-6 md:p-8">
                <div className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr]">
                  <div className="self-center">
                    <p className="text-sm font-bold uppercase tracking-[0.15em] text-[#66804f]">
                      {t.title}
                    </p>
                    <h2 className="mt-3 text-3xl font-black">{t.dashboardCreateWorkspace}</h2>
                    <p className="mt-3 leading-7 text-stone-600">
                      {t.dashboardCreateWorkspaceDescription}
                    </p>
                  </div>
                  <ShopForm
                    title={t.dashboardShopSetup}
                    form={shopForm}
                    setForm={setShopForm}
                    onSubmit={createShop}
                    t={t}
                  />
                </div>
              </div>
            ) : (
              <>
                <div className="mt-7 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-xl font-black">{t.dashboardRiskTitle}</h2>
                    <p className="mt-1 text-sm text-stone-600">{t.dashboardRiskDescription}</p>
                  </div>
                  <label className="flex items-center gap-3 text-sm font-bold">
                    <span>{t.dashboardChooseShop}</span>
                    <select
                      value={selectedShopId}
                      onChange={(event) => {
                        setSelectedShopId(event.target.value);
                        setProductForm((current) => ({ ...current, shopId: event.target.value }));
                      }}
                      className="min-w-48 rounded-xl border border-[#d8ded2] bg-white px-4 py-3"
                    >
                      {shops.map((shop) => (
                        <option key={shop.id} value={shop.id}>
                          {shop.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  <MetricCard
                    label={t.dashboardActiveLots}
                    value={formatter.format(risk.length)}
                    icon="↗"
                    accent="mint"
                  />
                  <MetricCard
                    label={t.dashboardAtRiskUnits}
                    value={formatter.format(totalAtRisk)}
                    icon="!"
                    accent={highRiskLots ? "peach" : "mint"}
                    note={highRiskLots ? t.dashboardRiskHigh : t.dashboardRiskLow}
                  />
                  <MetricCard
                    label={t.dashboardAvgSales}
                    value={`${formatter.format(averageDailySales)} / ${t.dashboardDayUnit}`}
                    icon="⌁"
                    accent="lavender"
                  />
                </div>

                <div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_0.8fr]">
                  <section className="rounded-3xl border border-[#e0e5da] bg-white p-5 md:p-7">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#788475]">
                          {selectedShop?.name}
                        </p>
                        <h2 className="mt-1 text-2xl font-black">{t.dashboardRiskTitle}</h2>
                      </div>
                      <span className="rounded-full bg-[#f0f3ec] px-3 py-1.5 text-xs font-bold text-[#5e6959]">
                        {t.dashboardSalesHistory}
                      </span>
                    </div>

                    {riskLoading ? (
                      <p className="py-12 text-center text-stone-600">{t.dashboardLoadingRisk}</p>
                    ) : risk.length ? (
                      <div className="mt-5 space-y-4">
                        {risk.map((item) => {
                          const levelText =
                            item.risk_level === "high"
                              ? t.dashboardRiskHigh
                              : item.risk_level === "medium"
                                ? t.dashboardRiskMedium
                                : t.dashboardRiskLow;
                          const levelStyle =
                            item.risk_level === "high"
                              ? "bg-[#fff0e8] text-[#a84d2c]"
                              : item.risk_level === "medium"
                                ? "bg-[#fff7df] text-[#87620c]"
                                : "bg-[#e8f4db] text-[#42643a]";
                          const barStyle =
                            item.risk_level === "high"
                              ? "bg-[#da754e]"
                              : item.risk_level === "medium"
                                ? "bg-[#d5a83d]"
                                : "bg-[#76a65c]";

                          return (
                            <article
                              key={item.lot_id}
                              className="rounded-2xl border border-[#edf0e9] p-4 md:p-5"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <h3 className="text-lg font-black">{item.product_name}</h3>
                                  <p className="mt-1 text-sm text-stone-600">
                                    {t.dashboardStock}: {formatter.format(item.current_stock)} ·{" "}
                                    {t.dashboardExpiresIn.replace(
                                      "{days}",
                                      String(item.days_remaining),
                                    )}
                                  </p>
                                </div>
                                <span
                                  className={`rounded-full px-3 py-1.5 text-xs font-black ${levelStyle}`}
                                >
                                  {levelText} · {item.risk_score}
                                </span>
                              </div>
                              <div
                                className="mt-4 h-2 overflow-hidden rounded-full bg-[#edf0e9]"
                                role="meter"
                                aria-label={levelText}
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={item.risk_score}
                              >
                                <div
                                  className={`h-full rounded-full transition-all ${barStyle}`}
                                  style={{ width: `${item.risk_score}%` }}
                                />
                              </div>
                              <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm">
                                <span className="font-semibold text-stone-600">
                                  {t.dashboardUnitsAtRisk}
                                </span>
                                <span className="font-black">
                                  {formatter.format(item.units_at_risk)} / {item.current_stock}
                                </span>
                              </div>
                              <div className="mt-4 rounded-xl bg-[#f5f7f2] p-4">
                                <p className="text-xs font-black uppercase tracking-[0.1em] text-[#6c7b62]">
                                  {t.dashboardRecommendation}
                                </p>
                                <p className="mt-1 text-sm leading-6 text-[#3d493c]">
                                  {item.recommendation}
                                </p>
                              </div>
                              <p className="mt-3 text-xs text-stone-500">
                                {t.dashboardDataPoints.replace("{count}", String(item.data_points))}
                              </p>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="mt-5 rounded-2xl bg-[#f6f8f3] px-5 py-8 text-center">
                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e4eddc] text-2xl text-[#557148]">
                          ↗
                        </div>
                        <p
                          className={
                            riskErrorStatus && riskErrorStatus !== 422
                              ? "mt-4 font-bold text-red-700"
                              : "mt-4 font-bold"
                          }
                        >
                          {riskErrorStatus === 422
                            ? t.dashboardNoHistory
                            : riskErrorStatus
                              ? riskError
                              : t.dashboardNoLots}
                        </p>
                        {riskErrorStatus === 422 ? (
                          <button
                            type="button"
                            onClick={loadSampleHistory}
                            disabled={sampleLoading}
                            className="mt-4 rounded-full bg-[#30442a] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#253820] disabled:opacity-60"
                          >
                            {sampleLoading ? t.dashboardLoadingRisk : t.dashboardSampleData}
                          </button>
                        ) : null}
                        {riskErrorStatus === 422 ? (
                          <p className="mx-auto mt-3 max-w-lg text-xs text-stone-500">
                            {t.dashboardSampleNotice}
                          </p>
                        ) : null}
                      </div>
                    )}
                  </section>

                  <aside className="space-y-5">
                    {selectedShop ? (
                      <div className="rounded-3xl border border-[#e0e5da] bg-white p-5 md:p-6">
                        <h2 className="text-lg font-black">{t.dashboardQuickActions}</h2>
                        <button
                          type="button"
                          onClick={loadSampleHistory}
                          disabled={sampleLoading}
                          className="mt-4 w-full rounded-2xl bg-[#e9f1e1] px-4 py-3 text-left text-sm font-bold text-[#385333] transition hover:bg-[#dceacb] disabled:opacity-60"
                        >
                          {sampleLoading ? t.dashboardLoadingRisk : t.dashboardSampleAction}
                        </button>
                        <p className="mt-3 text-xs leading-5 text-stone-500">
                          {t.dashboardSampleNotice}
                        </p>
                        <Link
                          href={`/lots/new?shop=${selectedShop.id}`}
                          className="mt-4 block w-full rounded-2xl bg-[#203a2c] px-4 py-3 text-center text-sm font-bold text-white transition hover:bg-[#2e513d]"
                        >
                          + {t.newLot}
                        </Link>
                      </div>
                    ) : null}

                    <ShopForm
                      title={t.createShop}
                      form={shopForm}
                      setForm={setShopForm}
                      onSubmit={createShop}
                      t={t}
                    />

                    <ProductForm
                      title={t.dashboardProductSetup}
                      form={productForm}
                      setForm={setProductForm}
                      shops={shops}
                      onSubmit={createProduct}
                      t={t}
                    />
                  </aside>
                </div>

                <section className="mt-6 rounded-3xl border border-[#e0e5da] bg-white p-5 md:p-7">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <p className="text-sm font-bold uppercase tracking-[0.12em] text-[#788475]">
                        {t.myShops}
                      </p>
                      <h2 className="mt-1 text-2xl font-black">{selectedShop?.name}</h2>
                    </div>
                    {selectedShop ? (
                      <Link
                        href={`/lots/new?shop=${selectedShop.id}`}
                        className="rounded-full bg-[#203a2c] px-5 py-3 text-sm font-bold text-white hover:bg-[#2e513d]"
                      >
                        + {t.newLot}
                      </Link>
                    ) : null}
                  </div>
                  {selectedShop && products[selectedShop.id]?.length ? (
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {products[selectedShop.id].map((product) => (
                        <article key={product.id} className="rounded-2xl bg-[#f6f8f3] p-4">
                          <p className="font-bold">{product.name}</p>
                          <p className="mt-1 text-sm text-stone-600">{product.description}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-stone-600">{t.dashboardNoProducts}</p>
                  )}
                </section>
              </>
            )}
          </>
        )}
      </section>
    </main>
  );
}

type FormState = {
  name: string;
  description: string;
  latitude: string;
  longitude: string;
  business_type: "restaurant" | "supermarket";
};

function ShopForm({
  title,
  form,
  setForm,
  onSubmit,
  t,
}: {
  title: string;
  form: FormState;
  setForm: (value: FormState) => void;
  onSubmit: (event: React.FormEvent) => void;
  t: Record<string, string>;
}) {
  return (
    <section className="rounded-3xl border border-[#e0e5da] bg-white p-5 md:p-6">
      <h2 className="text-lg font-black">{title}</h2>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <select
          required
          value={form.business_type}
          onChange={(event) =>
            setForm({
              ...form,
              business_type: event.target.value === "supermarket" ? "supermarket" : "restaurant",
            })
          }
          aria-label={t.businessType}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        >
          <option value="restaurant">{t.restaurant}</option>
          <option value="supermarket">{t.supermarket}</option>
        </select>
        <input
          required
          minLength={2}
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          placeholder={t.shopName}
          aria-label={t.shopName}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        />
        <input
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
          placeholder={t.shopDescription}
          aria-label={t.shopDescription}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        />
        <div className="grid grid-cols-2 gap-3">
          <input
            required
            type="number"
            step="any"
            min={-90}
            max={90}
            value={form.latitude}
            onChange={(event) => setForm({ ...form, latitude: event.target.value })}
            placeholder={t.shopLatitude}
            aria-label={t.shopLatitude}
            className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
          />
          <input
            required
            type="number"
            step="any"
            min={-180}
            max={180}
            value={form.longitude}
            onChange={(event) => setForm({ ...form, longitude: event.target.value })}
            placeholder={t.shopLongitude}
            aria-label={t.shopLongitude}
            className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
          />
        </div>
        <button className="w-full rounded-xl bg-[#203a2c] px-4 py-3 text-sm font-bold text-white transition hover:bg-[#2e513d]">
          {t.shopSubmit}
        </button>
      </form>
    </section>
  );
}

function ProductForm({
  title,
  form,
  setForm,
  shops,
  onSubmit,
  t,
}: {
  title: string;
  form: { shopId: string; name: string; description: string; category: string };
  setForm: (value: { shopId: string; name: string; description: string; category: string }) => void;
  shops: Shop[];
  onSubmit: (event: React.FormEvent) => void;
  t: Record<string, string>;
}) {
  return (
    <section className="rounded-3xl border border-[#e0e5da] bg-white p-5 md:p-6">
      <h2 className="text-lg font-black">{title}</h2>
      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        <select
          required
          value={form.shopId}
          onChange={(event) => setForm({ ...form, shopId: event.target.value })}
          aria-label={t.productShop}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        >
          <option value="">{t.lotShop}</option>
          {shops.map((shop) => (
            <option key={shop.id} value={shop.id}>
              {shop.name}
            </option>
          ))}
        </select>
        <input
          required
          minLength={2}
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          placeholder={t.productName}
          aria-label={t.productName}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        />
        <select
          required
          value={form.category}
          onChange={(event) => setForm({ ...form, category: event.target.value })}
          aria-label={t.productCategory}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        >
          <option value="produce">{t.categoryProduce}</option>
          <option value="bakery">{t.categoryBakery}</option>
          <option value="dairy">{t.categoryDairy}</option>
          <option value="meat">{t.categoryMeat}</option>
          <option value="prepared">{t.categoryPrepared}</option>
          <option value="pantry">{t.categoryPantry}</option>
          <option value="other">{t.categoryOther}</option>
        </select>
        <input
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
          placeholder={t.productDescription}
          aria-label={t.productDescription}
          className="w-full rounded-xl border border-[#dfe4da] bg-[#fbfcf9] px-4 py-3 text-sm"
        />
        <button className="w-full rounded-xl border border-[#cfdac6] bg-[#f4f7f1] px-4 py-3 text-sm font-bold text-[#30442a] transition hover:bg-[#e9f1e1]">
          {t.productSubmit}
        </button>
      </form>
    </section>
  );
}

function MetricCard({
  label,
  value,
  icon,
  accent,
  note,
}: {
  label: string;
  value: string;
  icon: string;
  accent: "mint" | "peach" | "lavender";
  note?: string;
}) {
  const accentClass = {
    mint: "bg-[#e8f2df] text-[#45643d]",
    peach: "bg-[#fff0e8] text-[#a84d2c]",
    lavender: "bg-[#efedf8] text-[#5e568d]",
  }[accent];

  return (
    <article className="rounded-3xl border border-[#e0e5da] bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-semibold text-stone-600">{label}</p>
        <span
          className={`flex h-10 w-10 items-center justify-center rounded-2xl text-lg font-black ${accentClass}`}
        >
          {icon}
        </span>
      </div>
      <p className="mt-4 text-3xl font-black tracking-tight">{value}</p>
      {note ? <p className="mt-1 text-xs font-semibold text-stone-500">{note}</p> : null}
    </article>
  );
}
