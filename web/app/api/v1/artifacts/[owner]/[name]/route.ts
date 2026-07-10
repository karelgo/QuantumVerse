import { NextResponse } from "next/server";
import { getArtifact } from "@/lib/registry";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ owner: string; name: string }> },
) {
  const { owner, name } = await params;
  const artifact = getArtifact(owner, name);
  if (!artifact) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(artifact);
}
