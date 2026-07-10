// The seam between the frontend and the Hub. When QV_API_URL is set the
// pages read from a running Hub API (the FastAPI service from the
// implementation plan); otherwise they read the local filesystem registry
// directly — same shapes either way, so swapping backends touches no page.

import * as registry from "./registry";
import type {
  ArtifactDetail,
  ArtifactSummary,
  CapsuleDetail,
  Owner,
} from "./types";

const HUB = process.env.QV_API_URL?.replace(/\/$/, "");

async function hub<T>(route: string): Promise<T | null> {
  const res = await fetch(`${HUB}${route}`, { next: { revalidate: 60 } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Hub API ${res.status} on ${route}`);
  return (await res.json()) as T;
}

export async function listArtifacts(): Promise<ArtifactSummary[]> {
  if (HUB) return (await hub<ArtifactSummary[]>("/v1/artifacts")) ?? [];
  return registry.listArtifacts();
}

export async function searchArtifacts(q: string): Promise<ArtifactSummary[]> {
  if (HUB) {
    return (
      (await hub<ArtifactSummary[]>(`/v1/artifacts?q=${encodeURIComponent(q)}`)) ?? []
    );
  }
  return registry.searchArtifacts(q);
}

export async function getArtifact(
  owner: string,
  name: string,
): Promise<ArtifactDetail | null> {
  if (HUB) return hub<ArtifactDetail>(`/v1/artifacts/${owner}/${name}`);
  return registry.getArtifact(owner, name);
}

export async function getOwner(handle: string): Promise<Owner | null> {
  if (HUB) return hub<Owner>(`/v1/owners/${handle}`);
  return registry.getOwner(handle);
}

export async function getCapsule(id: string): Promise<CapsuleDetail | null> {
  if (HUB) return hub<CapsuleDetail>(`/v1/capsules/${id}`);
  return registry.getCapsule(id);
}
