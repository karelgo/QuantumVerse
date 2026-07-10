"""Federation (RFC-0007): sync one registry's public objects into another.

Because every object is content-addressed, sync is a transfer plus a replay:
fetch bytes from the source, hand them to the destination's ordinary write
operations, and let the destination *re-derive* everything downstream — cards,
capsule validity, certificate verdicts, leaderboard scores. A peer can offer
objects; it can never dictate a result. Deduplication is free (identical
digests / capsule ids / artifact versions are skipped), so sync is idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from ._schema import schema_errors
from .registry import Registry, RegistryError, get_registry
from .uris import parse_uri

__all__ = ["FederationError", "SyncReport", "sync"]


class FederationError(ValueError):
    """Raised when a catalog is malformed or a sync cannot proceed."""


@dataclass
class SyncReport:
    """Counts of what a sync transferred vs. skipped (already present)."""

    artifacts_synced: int = 0
    artifacts_skipped: int = 0
    capsules_synced: int = 0
    capsules_skipped: int = 0
    devices_synced: int = 0
    devices_skipped: int = 0
    certificates_submitted: int = 0
    boards_synced: int = 0
    boards_skipped: int = 0
    entries_submitted: int = 0
    warnings: list = field(default_factory=list)

    def summary(self) -> str:
        return (
            "sync complete:\n"
            f"  artifacts:    {self.artifacts_synced} synced, {self.artifacts_skipped} already present\n"
            f"  capsules:     {self.capsules_synced} synced, {self.capsules_skipped} already present\n"
            f"  devices:      {self.devices_synced} synced, {self.devices_skipped} already present\n"
            f"  certificates: {self.certificates_submitted} re-derived\n"
            f"  boards:       {self.boards_synced} synced, {self.boards_skipped} already present\n"
            f"  entries:      {self.entries_submitted} re-scored"
            + (f"\n  warnings:     {len(self.warnings)}" if self.warnings else "")
        )


def _has_capsule(dest: Registry, capsule_id: str) -> bool:
    try:
        dest.get_capsule(capsule_id)
        return True
    except RegistryError:
        return False


def _has_artifact_version(dest: Registry, namespace: str, name: str, version: str) -> bool:
    try:
        return version in dest.get_artifact(namespace, name).get("versions", [])
    except RegistryError:
        return False


def _has_device(dest: Registry, namespace: str, name: str) -> bool:
    try:
        dest.get_device(namespace, name)
        return True
    except RegistryError:
        return False


def _has_board(dest: Registry, name: str) -> bool:
    try:
        dest.get_board(name)
        return True
    except RegistryError:
        return False


def sync(
    source: Union[str, Registry],
    dest: Optional[Union[str, Registry]] = None,
) -> SyncReport:
    """Pull *source*'s public catalog into *dest* (RFC-0007).

    *source* is another registry (a URL or a Registry); *dest* defaults to the
    ambient registry (``QV_REGISTRY_URL`` or the local store). Ordering matters:
    devices are registered before capsules so calibration snapshots auto-link,
    and capsules land before certificates and leaderboard entries that
    reference them.
    """
    src = get_registry(source)
    dst = get_registry(dest)
    if src is dst:
        raise FederationError("source and destination registries are the same")

    catalog = src.catalog()
    errors = schema_errors("federation-catalog", catalog)
    if errors:
        raise FederationError(
            "source catalog is malformed:\n  " + "\n  ".join(errors)
        )

    report = SyncReport()

    # 1. Devices first — so a capsule's calibration snapshot links on arrival.
    for device in catalog["devices"]:
        uri = parse_uri(device["ref"])
        if _has_device(dst, uri.namespace, uri.name):
            report.devices_skipped += 1
        else:
            dst.register_device(uri.namespace, uri.name, device["record"])
            report.devices_synced += 1

    # 2. Artifacts, version by version (published versions are immutable).
    for artifact in catalog["artifacts"]:
        ns, name = artifact["namespace"], artifact["name"]
        for version in artifact["versions"]:
            if _has_artifact_version(dst, ns, name, version):
                report.artifacts_skipped += 1
                continue
            try:
                resolved, files = src.artifact_files(ns, name, version)
                dst.create_artifact(ns, name, artifact["type"])
                dst.publish_version(ns, name, version, files, card_fields=resolved.get("card"))
                report.artifacts_synced += 1
            except RegistryError as exc:
                report.warnings.append(f"artifact {ns}/{name}@{version}: {exc}")

    # 3. Capsules — re-validated and content-addressed, so ids match exactly.
    for capsule_id in catalog["capsules"]:
        if _has_capsule(dst, capsule_id):
            report.capsules_skipped += 1
            continue
        _id, files = src.capsule_files(capsule_id)
        try:
            dst.push_capsule(files)
            report.capsules_synced += 1
        except RegistryError as exc:
            report.warnings.append(f"capsule {capsule_id[:20]}…: {exc}")

    # 4. Certificates — replay the capsule-id lists; the destination recomputes.
    for device in catalog["devices"]:
        uri = parse_uri(device["ref"])
        for capsule_ids in device["certificates"]:
            try:
                dst.submit_certificate(uri.namespace, uri.name, capsule_ids)
                report.certificates_submitted += 1
            except RegistryError as exc:
                report.warnings.append(f"certificate for {device['ref']}: {exc}")

    # 5. Boards + entries — the destination re-scores every entry.
    for board in catalog["boards"]:
        definition = board["definition"]
        if _has_board(dst, definition["name"]):
            report.boards_skipped += 1
        else:
            try:
                dst.create_board(definition)
                report.boards_synced += 1
            except RegistryError as exc:
                report.warnings.append(f"board {definition['name']}: {exc}")
                continue
        for capsule_id in board["entries"]:
            try:
                dst.submit_entry(definition["name"], capsule_id)
                report.entries_submitted += 1
            except RegistryError as exc:
                report.warnings.append(
                    f"entry {capsule_id[:20]}… on {definition['name']}: {exc}"
                )

    return report
