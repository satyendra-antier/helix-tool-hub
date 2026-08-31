import { notFound } from "next/navigation";
import { getToolBySlug } from "@/lib/registry";

export const dynamic = "force-dynamic";

/** Panel UI is hosted by ToolsKeepAlive in the tools layout so it survives tool switches. */
export default function ToolPage({ params }: { params: { slug: string } }) {
  const manifest = getToolBySlug(params.slug);
  if (!manifest) notFound();
  return null;
}
