import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Follow The Money — AusPol Transparency",
  description:
    "Australian political donations, expenditure, and voting records in one place.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">
        <header className="border-b border-gray-200 px-6 py-4">
          <a href="/" className="text-lg font-semibold tracking-tight">
            Follow The Money
          </a>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
