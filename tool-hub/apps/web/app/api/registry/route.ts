import { NextResponse } from "next/server";
import { loadToolRegistry } from "@/lib/registry";

export async function GET() {
  const tools = loadToolRegistry();
  return NextResponse.json({ tools });
}
