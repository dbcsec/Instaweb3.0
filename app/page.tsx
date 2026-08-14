import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Premium Websites Without the Premium Price",

  description:
    "Launch a professional, conversion-focused business website with Instaweb Agency.",

  alternates: {
    canonical: "/",
  },

  openGraph: {
    title: "Premium Websites Without the Premium Price",
    description:
      "Launch a professional business website with Instaweb Agency.",
    url: "/",
  },
};

export default function HomePage() {
  return (
    <main>
      <section>
        <h1>Premium Websites Without the Premium Price</h1>

        <p>
          Get a professionally designed website built for your business,
          without the traditional agency price tag.
        </p>

        <a href="/pricing">
          Build My Website
        </a>
      </section>

      <section>
        <h2>How It Works</h2>

        <p>
          Tell us about your business. We build your website.
          You approve it. Then we launch.
        </p>
      </section>

      <section>
        <h2>Built for Businesses That Want More Customers</h2>

        {/* Industry cards */}
      </section>
    </main>
  );
}
