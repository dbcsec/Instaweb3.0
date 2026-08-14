import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = "https://instaweb.agency";

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/admin/",
          "/api/",
          "/dashboard/",
          "/checkout/",
          "/preview/",
        ],
      },
    ],

    sitemap: `${baseUrl}/sitemap.xml`,
  };
}
