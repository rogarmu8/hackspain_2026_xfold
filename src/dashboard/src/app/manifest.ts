import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "XFold · Centro de control",
    short_name: "XFold",
    description:
      "Monitor de la celda OpenArm: prensa, pliegue ninja y tolva a bolsa",
    lang: "es",
    start_url: "/",
    display: "standalone",
    background_color: "#FAF6EC",
    theme_color: "#FAF6EC",
    icons: [
      { src: "/brand/xfold-app-icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/brand/xfold-app-icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/brand/xfold-app-icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
