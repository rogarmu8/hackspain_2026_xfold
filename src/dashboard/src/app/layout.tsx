import type { Metadata, Viewport } from "next";
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

const TITLE = "XFold · Control room";
const DESCRIPTION =
  "OpenArm cell monitor: press, ninja fold, and bag chute";
const OG_IMAGE = "/brand/xfold-og.png";

export const viewport: Viewport = {
  themeColor: "#FAF6EC",
};

export const metadata: Metadata = {
  title: {
    default: TITLE,
    template: "%s · XFold",
  },
  description: DESCRIPTION,
  applicationName: "XFold",
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    siteName: "XFold",
    locale: "en_US",
    type: "website",
    images: [{ url: OG_IMAGE, width: 1200, height: 630, alt: "XFOLD" }],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: [OG_IMAGE],
  },
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
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-canvas text-ink">
        <DashboardProvider>{children}</DashboardProvider>
      </body>
    </html>
  );
}
