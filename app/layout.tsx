import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://instaweb.agency"),

  title: {
    default: "Instaweb Agency | Premium Websites Without the Premium Price",
    template: "%s | Instaweb Agency",
  },

  description:
    "AI-powered websites for businesses. Get a premium, conversion-focused website without the traditional agency price tag.",

  keywords: [
    "website design",
    "AI website builder",
    "small business websites",
    "website development",
    "business website",
    "Instaweb Agency",
  ],

  alternates: {
    canonical: "https://instaweb.agency",
  },

  openGraph: {
    type: "website",
    url: "https://instaweb.agency",
    siteName: "Instaweb Agency",
    title: "Premium Websites Without the Premium Price",
    description:
      "AI-powered websites designed to help businesses look premium and generate more customers.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Instaweb Agency",
      },
    ],
  },

  twitter: {
    card: "summary_large_image",
    title: "Instaweb Agency",
    description:
      "Premium websites without the premium price.",
    images: ["/og-image.png"],
  },

  robots: {
    index: true,
    follow: true,
  },

  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
