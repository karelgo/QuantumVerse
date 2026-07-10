// Hub API, v1 shape. Served from the Phase-0 filesystem registry today;
// the FastAPI service serves the identical contract in Phase 1 (point
// QV_API_URL at it and this route becomes redundant).

import { NextRequest, NextResponse } from "next/server";
import { searchArtifacts } from "@/lib/registry";

export function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q") ?? "";
  return NextResponse.json(searchArtifacts(q));
}
