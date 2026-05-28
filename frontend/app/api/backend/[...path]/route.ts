import { NextRequest, NextResponse } from "next/server";

const BACKEND_BASE = process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000/api";

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  const path = params.path.join("/");
  const upstream = new URL(`${BACKEND_BASE}/${path}`);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.set(key, value));

  try {
    const response = await fetch(upstream.toString(), { cache: "no-store" });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Backend proxy could not reach the local FastAPI server.",
        backend: BACKEND_BASE,
      },
      { status: 502 },
    );
  }
}
