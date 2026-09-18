import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DashboardProvider } from "@/lib/dashboard-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "XFOLD · Centro de control",
  description:
    "Monitor de la celda OpenArm: prensa, pliegue ninja y tolva a bolsa",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-canvas text-ink">
        <DashboardProvider>{children}</DashboardProvider>
      </body>
    </html>
  );
}
