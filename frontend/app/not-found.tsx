import type { Metadata } from "next";
import Link from "next/link";

import { Nav } from "@/components/nav";
import { GlowButton } from "@/components/visual/glow-button";

export const metadata: Metadata = { title: "Not found · Mindgrep" };

/** Any address that matches no page, and any document or project id that is not a number. */
export default function NotFound() {
  return (
    <>
      <Nav />
      <main id="main" className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">
        <div className="max-w-xl space-y-4 pt-16">
          <h1 className="text-h2">Nothing at this address.</h1>
          <p className="text-mid">
            The link may be mistyped, or it points to a document or project that is no longer in the index.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <GlowButton href="/search">Search your memory</GlowButton>
            <Link href="/" className="btn-ghost h-10 px-5 text-sm">
              Home
            </Link>
          </div>
        </div>
      </main>
    </>
  );
}
