import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware(req) {
    const role = req.nextauth.token?.role;
    const path = req.nextUrl.pathname;

    if (path.startsWith("/admin") && role !== "admin") {
      return NextResponse.redirect(new URL("/dashboard", req.url));
    }

    if (
      (path.startsWith("/studio") || path === "/integrations") &&
      role === "viewer"
    ) {
      return NextResponse.redirect(new URL("/dashboard", req.url));
    }
  },
  {
    callbacks: {
      authorized: ({ token, req }) => {
        const path = req.nextUrl.pathname;
        const publicPaths = ["/", "/methodology", "/login"];
        if (publicPaths.some((p) => path === p || path.startsWith("/api/auth"))) {
          return true;
        }
        return !!token;
      },
    },
  }
);

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/studio/:path*",
    "/tools/:path*",
    "/integrations/:path*",
    "/analytics/:path*",
    "/settings/:path*",
    "/admin/:path*",
    "/api/hub/:path*",
    "/api/modules/:path*",
  ],
};
