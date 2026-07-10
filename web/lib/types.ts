import type { CircuitResources } from "./circuit";

export type ArtifactKind = "circuit" | "parameters" | "instance";
export type TrustLevel = 0 | 1 | 2;

export interface Owner {
  handle: string;
  display: string;
  kind: "org" | "user";
  bio: string;
  signing_key?: string; // Ed25519 public key, base64 (SPKI/DER)
}

export interface ArtifactMeta {
  owner: string;
  name: string;
  kind: ArtifactKind;
  version: string;
  description: string;
  license: string;
  tags: string[];
  created: string;
  flagship?: boolean;
}

export interface ArtifactSummary extends ArtifactMeta {
  resources: CircuitResources;
  capsuleCount: number;
  maxTrustLevel: TrustLevel | null;
}

export interface TrainedParameters {
  names: string[];
  values: number[];
  observable?: string;
  energy?: number;
  units?: string;
  optimizer?: string;
  iterations?: number;
}

export interface ArtifactDetail extends ArtifactSummary {
  qasm: string;
  parameters: TrainedParameters | null;
  capsules: CapsuleSummary[];
}

export interface CapsuleSummary {
  id: string;
  shortId: string;
  title: string;
  created: string;
  trustLevel: TrustLevel;
  backend: string;
  shots: number;
}

export interface CapsuleIntegrity {
  idVerified: boolean;
  files: { name: string; digest: string; verified: boolean }[];
  signatureValid: boolean | null; // null = unsigned
  signer: string | null;
}

export interface CapsuleDetail extends CapsuleSummary {
  manifest: {
    capsule_version: string;
    id: string;
    created: string;
    title: string;
    authors: { name: string; profile?: string; orcid?: string }[];
    license: string;
    artifacts: Record<string, string>;
    files: Record<string, string>;
    replay_of: string | null;
    doi: string | null;
  };
  device: {
    backend: { provider: string; name: string; version: string };
    captured: string;
    topology?: { num_qubits: number; coupling_map?: number[][] };
    simulator: {
      engine: string;
      method: string;
      noise_model: Record<string, unknown> | null;
    } | null;
  };
  execution: {
    job_ids: string[];
    submitted: string;
    completed: string;
    shots: number;
    counts_raw: Record<string, number>;
    counts_mitigated?: Record<string, number>;
    parameters?: Record<string, unknown>;
  };
  mitigation: { pipeline: { step: string; method: string }[] } | null;
  qasm: string;
  integrity: CapsuleIntegrity;
}
