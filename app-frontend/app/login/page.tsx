"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import Header from "../../components/Header";
import { api } from "../../lib/api";
import { useApp } from "../../providers/AppProviders";

export default function LoginPage() {
  const { t, login } = useApp();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { access_token } = await api.login(email, password);
      login(access_token);
      router.push("/shop");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t.genericError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen">
      <Header />
      <section className="mx-auto max-w-md px-6 pb-12 pt-12">
        <h1 className="mb-6 text-3xl font-black">{t.loginTitle}</h1>
        {error ? (
          <p className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : null}
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-semibold">
              {t.authEmail}
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-semibold">
              {t.authPassword}
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-xl border border-stone-300 px-4 py-3 dark:border-stone-700 dark:bg-stone-900"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {t.loginSubmit}
          </button>
        </form>
        <p className="mt-6 text-sm text-stone-500">
          {t.loginNoAccount}{" "}
          <Link href="/register" className="font-semibold text-emerald-600">
            {t.loginLinkRegister}
          </Link>
        </p>
      </section>
    </main>
  );
}
