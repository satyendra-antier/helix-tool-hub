import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { fetchModule, getModuleApiBase } from "@/lib/module-api";
import { getToolBySlug } from "@/lib/registry";

export async function GET(
  req: NextRequest,
  { params }: { params: { slug: string; path: string[] } }
) {
  return proxy(req, params);
}

export async function POST(
  req: NextRequest,
  { params }: { params: { slug: string; path: string[] } }
) {
  return proxy(req, params);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { slug: string; path: string[] } }
) {
  return proxy(req, params);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { slug: string; path: string[] } }
) {
  return proxy(req, params);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { slug: string; path: string[] } }
) {
  return proxy(req, params);
}

async function proxy(
  req: NextRequest,
  params: { slug: string; path: string[] }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const manifest = getToolBySlug(params.slug);
  if (!manifest) {
    return NextResponse.json({ error: "Module not found" }, { status: 404 });
  }

  const path = params.path?.join("/") || "";
  const search = req.nextUrl.search;
  const url = `${getModuleApiBase(params.slug)}/${path}${search}`;

  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const serviceKey = process.env.HUB_SERVICE_KEY;
  if (serviceKey) headers.set("X-Hub-Service-Key", serviceKey);

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  try {
    const res = await fetch(url, init);
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") || "application/json" },
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Proxy error" },
      { status: 502 }
    );
  }
}
