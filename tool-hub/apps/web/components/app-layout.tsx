import { cn } from "@tool-hub/ui";

export function AppLayout({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8", className)}>
      {children}
    </div>
  );
}
