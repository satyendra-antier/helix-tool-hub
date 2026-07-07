import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { loadToolRegistry } from "@/lib/registry";
import { ProductSidebar, ProductTopBar } from "@/components/product-shell/sidebar";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions);
  if (!session) {
    redirect("/login");
  }
  const tools = loadToolRegistry();

  return (
    <div className="flex min-h-screen bg-surface-muted/30">
      <ProductSidebar tools={tools} />
      <div className="flex min-w-0 flex-1 flex-col">
        <ProductTopBar tools={tools} />
        <main className="flex-1 p-4 lg:p-6 max-w-7xl w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
