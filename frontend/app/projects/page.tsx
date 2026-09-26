import { Suspense } from "react";

import { ProjectsView } from "@/components/projects-view";

export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsView />
    </Suspense>
  );
}
