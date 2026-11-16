import { notFound } from "next/navigation";

import { ProjectView } from "@/components/project-view";

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <ProjectView id={Number(id)} />;
}
