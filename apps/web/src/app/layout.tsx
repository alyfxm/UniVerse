import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { LanguageProvider } from "@/context/LanguageContext";
import { Navbar } from "@/components/Navbar";

export const metadata: Metadata = {
  title: "UniVerse — Multilingual AI Campus Assistant",
  description:
    "Access university academic regulations, facilities, events, and student services in Bahasa Melayu and English with verified page-level PDF citations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <LanguageProvider>
          <AuthProvider>
            <Navbar />
            {children}
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}

