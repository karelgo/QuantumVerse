import { NextResponse } from "next/server";
import { getCapsule } from "@/lib/registry";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ digest: string }> },
) {
  const { digest } = await params;
  const capsule = getCapsule(digest);
  if (!capsule) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(capsule);
}
