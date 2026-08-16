import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "API Broker — Self-Correcting API Broker",
  description: "Observability and control interface for the self-correcting API broker.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
