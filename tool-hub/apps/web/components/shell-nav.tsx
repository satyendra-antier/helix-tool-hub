import { loadToolRegistry } from "@/lib/registry";
import { ShellNavClient } from "./shell-nav-client";

export function ShellNav() {
  const tools = loadToolRegistry().map((t) => ({
    id: t.id,
    name: t.name,
    route: t.route,
  }));
  return <ShellNavClient tools={tools} />;
}
