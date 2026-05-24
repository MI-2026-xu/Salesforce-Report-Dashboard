import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("Authorization") ?? "";
  const res  = await fetch(`${BACKEND}/auth/sf-status`, {
    headers: { Authorization: auth },
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
