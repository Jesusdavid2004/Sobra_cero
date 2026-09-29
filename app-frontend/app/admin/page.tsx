"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Header from "../../components/Header";
import { api, type Forecast, type Report, type Shop } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function AdminPage() {
  const { t, token } = useApp();
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [shops, setShops] = useState<Shop[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    api
      .report()
      .then(setReport)
      .catch((cause) => setError(cause instanceof Error ? cause.message : t.genericError));
    api
      .shops()
      .then(async (list) => {
        setShops(list);
        if (list.length) setForecast(await api.forecast(list[0].id).catch(() => null));
      })
      .catch(() => setShops([]));
  }, [token, router, t.genericError]);

  const rows = report
    ? [
        { label: t.adminUsers, value: report.users },
        { label: t.adminShops, value: report.shops },
        { label: t.adminLots, value: report.lots },
        { label: t.adminReservations, value: report.reservations },
        { label: t.adminDonations, value: report.donations },
      ]
    : [];

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-4xl px-6 pb-12 pt-8">
        <h1 className="mb-8 text-3xl font-black">{t.adminTitle}</h1>
        {error ? (
          <p className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : null}
        <h2 className="mb-4 text-xl font-bold">{t.adminReport}</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {rows.map((row) => (
            <div
              key={row.label}
              className="rounded-3xl border border-stone-200 p-5 text-center dark:border-stone-800"
            >
              <p className="text-3xl font-black text-emerald-600">{row.value}</p>
              <p className="mt-1 text-xs uppercase tracking-wide text-stone-500">{row.label}</p>
            </div>
          ))}
        </div>
        <h2 className="mb-4 mt-10 text-xl font-bold">{t.adminForecast}</h2>
        {forecast ? (
          <ul className="space-y-2">
            {forecast.series.map((point) => (
              <li
                key={point.day}
                className="flex items-center gap-3 rounded-xl bg-stone-100 p-3 dark:bg-stone-800"
              >
                <span className="w-24 text-sm font-semibold">
                  {t.adminDay} {point.day}
                </span>
                <div className="h-4 flex-1 rounded-full bg-stone-200 dark:bg-stone-700">
                  <div
                    className="h-4 rounded-full bg-emerald-500"
                    style={{ width: `${Math.min(100, point.predicted_lots * 20)}%` }}
                  />
                </div>
                <span className="w-10 text-right text-sm font-bold">{point.predicted_lots}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-stone-500">{shops.length ? t.noShops : t.noShops}</p>
        )}
      </section>
    </main>
  );
}
