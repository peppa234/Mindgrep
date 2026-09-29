import { Suspense } from "react";

import { IdeasView } from "@/components/ideas-view";

export default function IdeasPage() {
  return (
    <Suspense>
      <IdeasView />
    </Suspense>
  );
}
