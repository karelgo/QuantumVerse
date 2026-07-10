import { NextResponse } from "next/server";
import { getOwner } from "@/lib/registry";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ handle: string }> },
) {
  const { handle } = await params;
  const owner = getOwner(handle);
  if (!owner) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(owner);
}
