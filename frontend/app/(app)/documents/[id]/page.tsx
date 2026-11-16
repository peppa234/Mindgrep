import { notFound } from "next/navigation";

import { DocumentView } from "@/components/document-view";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <DocumentView id={Number(id)} />;
}
