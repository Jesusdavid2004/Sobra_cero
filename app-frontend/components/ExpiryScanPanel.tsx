"use client";

import { useEffect, useState } from "react";

import { api, type ExpiryScanSuggestion } from "@/lib/api";
import { useApp } from "@/providers/AppProviders";

type ExpiryScanPanelProps = {
  lotId: number;
  shopId: number;
  hasImage: boolean;
  onConfirmed: () => void;
};

export default function ExpiryScanPanel({
  lotId,
  shopId,
  hasImage,
  onConfirmed,
}: ExpiryScanPanelProps) {
  const { t, lang, token, authReady, user } = useApp();
  const [suggestions, setSuggestions] = useState<ExpiryScanSuggestion[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!authReady || !token || (!user?.is_admin && user?.role !== "business")) return;

    let active = true;
    setLoading(true);
    void api
      .shops()
      .then(async (shops) => {
        if (!active || (!user?.is_admin && !shops.some((shop) => shop.id === shopId))) return;
        setCanManage(true);
        const scans = await api.expiryScans(lotId);
        if (active) setSuggestions(scans);
      })
      .catch(() => {
        if (active) setError(t.genericError);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authReady, token, user, shopId, lotId, t.genericError]);

  const scan = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const suggestion = await api.scanExpiryDate(lotId, lang);
      setSuggestions((current) => [suggestion, ...current]);
    } catch {
      setError(t.detailExpiryActionError);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (suggestionId: number, decision: "confirm" | "reject") => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated =
        decision === "confirm"
          ? await api.confirmExpiryScan(lotId, suggestionId)
          : await api.rejectExpiryScan(lotId, suggestionId);
      setSuggestions((current) =>
        current.map((suggestion) => (suggestion.id === suggestionId ? updated : suggestion)),
      );
      if (decision === "confirm") {
        setMessage(t.detailExpiryConfirmed);
        onConfirmed();
      } else {
        setMessage(t.detailExpiryRejected);
      }
    } catch {
      setError(t.detailExpiryActionError);
    } finally {
      setBusy(false);
    }
  };

  if (!canManage && !loading) return null;

  const dateFormatter = new Intl.DateTimeFormat(lang === "es" ? "es-CO" : "en-US", {
    dateStyle: "medium",
    timeZone: "UTC",
  });
  const statusLabel = (status: ExpiryScanSuggestion["status"]) => {
    const labels = {
      awaiting_confirmation: t.detailExpiryAwaitingConfirmation,
      confirmed: t.detailExpiryStatusConfirmed,
      rejected: t.detailExpiryStatusRejected,
      unreadable: t.detailExpiryUnreadable,
    };
    return labels[status];
  };

  return (
    <section
      className="mt-8 rounded-3xl border border-stone-200 p-6 dark:border-stone-800"
      aria-busy={loading || busy}
    >
      <h2 className="text-xl font-bold">{t.detailExpiryScans}</h2>
      <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">{t.detailExpiryDisclaimer}</p>
      {loading ? <p className="mt-4 text-sm text-stone-500">{t.detailExpiryLoading}</p> : null}
      {canManage ? (
        <>
          <button
            type="button"
            onClick={scan}
            disabled={busy || !hasImage}
            className="mt-4 rounded-xl bg-emerald-700 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            {busy ? t.detailExpiryScanning : t.detailExpiryScan}
          </button>
          {!hasImage ? (
            <p className="mt-2 text-sm text-stone-500">{t.detailExpiryNeedsImage}</p>
          ) : null}
          {message ? (
            <p
              className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
              role="status"
            >
              {message}
            </p>
          ) : null}
          {error ? (
            <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
              {error}
            </p>
          ) : null}
          {suggestions.length ? (
            <ul className="mt-5 space-y-3">
              {suggestions.map((suggestion) => (
                <li key={suggestion.id} className="rounded-2xl bg-stone-100 p-4 dark:bg-stone-800">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">
                      {suggestion.expires_on
                        ? dateFormatter.format(new Date(`${suggestion.expires_on}T00:00:00Z`))
                        : t.detailExpiryNoDate}
                    </span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs font-bold dark:bg-stone-900">
                      {statusLabel(suggestion.status)}
                    </span>
                  </div>
                  {suggestion.printed_date ? (
                    <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
                      {t.detailExpiryPrintedDate}: {suggestion.printed_date}
                    </p>
                  ) : null}
                  <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">
                    {t.detailExpiryConfidence.replace(
                      "{percent}",
                      new Intl.NumberFormat(lang, {
                        style: "percent",
                        maximumFractionDigits: 0,
                      }).format(suggestion.confidence),
                    )}
                  </p>
                  {suggestion.status === "awaiting_confirmation" && suggestion.expires_on ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void decide(suggestion.id, "confirm")}
                        disabled={busy}
                        className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
                      >
                        {t.detailExpiryConfirm}
                      </button>
                      <button
                        type="button"
                        onClick={() => void decide(suggestion.id, "reject")}
                        disabled={busy}
                        className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-bold disabled:opacity-50 dark:border-stone-600"
                      >
                        {t.detailExpiryReject}
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : !loading ? (
            <p className="mt-4 text-sm text-stone-500">{t.detailExpiryNoScans}</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
