import type { Metadata } from "next";

import AppProviders from "../providers/AppProviders";
import "./globals.css";

export const metadata: Metadata = {
  title: "SobraCero",
  description:
    "Rescata excedentes de comida, encuentra lotes con descuento y ayuda a reducir el desperdicio.",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
