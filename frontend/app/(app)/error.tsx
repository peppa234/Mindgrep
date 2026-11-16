"use client";

import { useEffect } from "react";

import { LoadError } from "@/components/load-error";

/** A page of the app threw while rendering. The nav stays, so there is always a way out. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="max-w-xl space-y-4 pt-8">
      <h1 className="text-h2">This page stopped working.</h1>
      <p className="text-mid">The interface hit an error it could not recover from. Your index and your files are untouched.</p>
      <LoadError error={error.message || "Unknown error"} onRetry={reset} />
    </div>
  );
}
