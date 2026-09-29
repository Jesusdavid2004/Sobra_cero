import type { Metadata } from "next";

import AppProviders from "../providers/AppProviders";
import "./globals.css";

export const metadata: Metadata = {
  title: "SobraCero",
  description: "Save good food from waste",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
