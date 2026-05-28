import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sydney Offshore Pelagic AI Map",
  description: "Local mock-data demo for offshore pelagic habitat suitability around Sydney."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
