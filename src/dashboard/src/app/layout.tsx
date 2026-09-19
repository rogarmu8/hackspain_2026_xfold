import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { DashboardProvider } from "@/lib/dashboard-context";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: {
    default: "XFold · Centro de control",
    template: "%s · XFold",
  },
  description:
    "Monitor de la celda OpenArm: prensa, pliegue ninja y tolva a bolsa",
  applicationName: "XFold",
  icons: {
    icon: [
      { url: "/brand/xfold-favicon.svg", type: "image/svg+xml" },
      { url: "/brand/xfold-app-icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/brand/xfold-app-icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/brand/xfold-app-icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/brand/xfold-app-icon-180.png", sizes: "180x180" }],
    shortcut: ["/brand/xfold-favicon.svg"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es"
      className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-canvas text-ink">
        <DashboardProvider>{children}</DashboardProvider>
      </body>
    </html>
  );
}
