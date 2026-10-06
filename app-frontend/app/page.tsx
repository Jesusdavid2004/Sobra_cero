"use client";

import Link from "next/link";

import Header from "../components/Header";
import { useApp } from "../providers/AppProviders";

export default function Home() {
  const { lang } = useApp();
  const isSpanish = lang === "es";

  return (
    <main className="min-h-screen bg-[#f5f3ee] text-[#1f2a1f]">
      <Header />
      <section className="mx-auto max-w-6xl px-6 pb-12 pt-8 md:pt-14">
        <div className="relative overflow-hidden rounded-[36px] bg-[#e9efdc] px-6 py-12 md:px-14 md:py-16">
          <div
            aria-hidden="true"
            className="absolute -right-12 -top-20 h-72 w-72 rounded-full bg-[#c7e49d] opacity-70"
          />
          <div className="relative z-10 max-w-3xl">
            <p className="mb-5 inline-flex rounded-full bg-white/80 px-4 py-2 text-sm font-bold uppercase tracking-[0.16em] text-[#47643a]">
              {isSpanish ? "Menos desperdicio, más aprovechamiento" : "Less waste, more value"}
            </p>
            <h1 className="text-5xl font-black leading-[1.02] tracking-tight md:text-7xl">
              {isSpanish ? (
                <>
                  Rescata comida.
                  <span className="mt-2 block text-[#5a803f]">Ahorra y evita desperdicios.</span>
                </>
              ) : (
                <>
                  Rescue good food.
                  <span className="mt-2 block text-[#5a803f]">Save money. Waste less.</span>
                </>
              )}
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-[#465044] md:text-xl">
              {isSpanish
                ? "SobraCero conecta restaurantes y tiendas con personas que quieren aprovechar alimentos próximos a vencer, en lotes con descuento."
                : "SobraCero connects restaurants and shops with people looking for discounted food lots that are close to their best-before date."}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/lots"
                className="rounded-full bg-[#30442a] px-7 py-4 text-base font-bold text-white shadow-[0_5px_0_#1e2d1a] transition hover:-translate-y-0.5 hover:bg-[#253820]"
              >
                {isSpanish ? "Explorar lotes disponibles" : "Explore available lots"}
              </Link>
              <Link
                href="/login"
                className="rounded-full border-2 border-[#30442a] bg-[#f8f7f0] px-7 py-4 text-base font-bold text-[#30442a] transition hover:bg-white"
              >
                {isSpanish ? "Publicar excedentes" : "List food surplus"}
              </Link>
            </div>
            <p className="mt-5 text-sm text-[#5c6657]">
              {isSpanish ? (
                <>
                  ¿Aún no tienes cuenta?{" "}
                  <Link href="/register" className="font-bold underline underline-offset-4">
                    Regístrate aquí
                  </Link>
                </>
              ) : (
                <>
                  New to SobraCero?{" "}
                  <Link href="/register" className="font-bold underline underline-offset-4">
                    Create an account
                  </Link>
                </>
              )}
            </p>
          </div>
        </div>

        <section className="py-14 md:py-16">
          <div className="max-w-2xl">
            <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#66804f]">
              {isSpanish ? "Así funciona" : "How it works"}
            </p>
            <h2 className="mt-2 text-3xl font-black md:text-4xl">
              {isSpanish
                ? "Un ciclo sencillo para aprovechar más"
                : "A simple way to make more of food"}
            </h2>
          </div>
          <div className="mt-7 grid gap-4 md:grid-cols-3">
            {[
              {
                number: "01",
                title: isSpanish ? "El comercio publica" : "A business lists",
                description: isSpanish
                  ? "Restaurantes y tiendas publican lotes disponibles con su precio, cantidad y fecha de vencimiento."
                  : "Restaurants and shops list available lots with their price, quantity, and expiration date.",
              },
              {
                number: "02",
                title: isSpanish ? "Tú eliges y reservas" : "You choose and reserve",
                description: isSpanish
                  ? "Explora la vitrina, revisa el descuento y reserva la cantidad que necesitas."
                  : "Browse the marketplace, check the discount, and reserve the amount you need.",
              },
              {
                number: "03",
                title: isSpanish ? "La comida se aprovecha" : "Food gets rescued",
                description: isSpanish
                  ? "El comercio reduce sus excedentes y tú accedes a comida a un mejor precio."
                  : "The business reduces surplus while you get good food at a better price.",
              },
            ].map((step) => (
              <article
                key={step.number}
                className="rounded-3xl border border-[#e2e5d9] bg-white/80 p-6"
              >
                <span className="text-sm font-black tracking-widest text-[#78975b]">
                  {step.number}
                </span>
                <h3 className="mt-3 text-xl font-black">{step.title}</h3>
                <p className="mt-2 leading-7 text-[#5b6257]">{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-5 rounded-3xl bg-[#dce9ce] p-7 md:flex-row md:items-center md:justify-between md:p-9">
          <div>
            <h2 className="text-2xl font-black">
              {isSpanish ? "¿Qué hay disponible hoy?" : "What can you rescue today?"}
            </h2>
            <p className="mt-2 text-[#465044]">
              {isSpanish
                ? "Los lotes se cargan desde los comercios y pueden agotarse."
                : "Lots are listed by local businesses and may sell out."}
            </p>
          </div>
          <Link
            href="/lots"
            className="shrink-0 rounded-full bg-[#30442a] px-6 py-3 text-center font-bold text-white transition hover:bg-[#253820]"
          >
            {isSpanish ? "Ir a la vitrina" : "Go to marketplace"}
          </Link>
        </section>
      </section>
    </main>
  );
}
