import { Suspense } from "react";

import { GraphView } from "@/components/graph-view";

export default function GraphPage() {
  return (
    <Suspense>
      <GraphView />
    </Suspense>
  );
}
