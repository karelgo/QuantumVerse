import pytest

from quantumverse.uris import (
    QvUriError,
    VersionError,
    format_uri,
    parse_uri,
    resolve_version,
)


def test_parse_artifact_forms():
    uri = parse_uri("qv:vqe/h2o-ground-state@1.4.2")
    assert (uri.kind, uri.namespace, uri.name, uri.version) == (
        "artifact", "vqe", "h2o-ground-state", "1.4.2",
    )
    assert parse_uri("vqe/h2o-ground-state").version is None  # scheme optional
    assert parse_uri("QV:VQE/Foo").namespace == "vqe"  # lowered


def test_parse_user_device_capsule():
    assert parse_uri("qv:users/aresearcher").kind == "user"
    dev = parse_uri("qv:device/tudelft/aurora-64")
    assert (dev.kind, dev.namespace, dev.name) == ("device", "tudelft", "aurora-64")
    cap = parse_uri("qv:capsule/9f3ac2")
    assert (cap.kind, cap.name) == ("capsule", "9f3ac2")


@pytest.mark.parametrize("bad", [
    "", "qv:", "qv://host/x", "qv:onlyone", "qv:a/b/c", "qv:users/x/y",
    "qv:users/x@1.0.0", "qv:capsule/xyz", "qv:capsule/9f3ac2@1.0.0",
    "qv:-bad/name", "qv:double--hyphen/name", "qv:ns/name@", "qv:ns/name@1.0.0@2",
    "qv:ns/name@not-a-version",
])
def test_parse_rejects_malformed(bad):
    with pytest.raises(QvUriError):
        parse_uri(bad)


def test_format_round_trip():
    for ref in ["qv:grover/sat-3q@1.0.0", "qv:users/alice", "qv:device/lab/machine",
                "qv:capsule/abcdef"]:
        assert format_uri(parse_uri(ref)) == ref


def test_resolve_version_rules():
    available = ["1.0.0", "1.4.2", "1.4.10", "2.0.0-rc.1", "0.9.0"]
    assert resolve_version("latest", available) == "1.4.10"
    assert resolve_version(None, available) == "1.4.10"
    assert resolve_version("1.4.2", available) == "1.4.2"
    assert resolve_version("1.4", available) == "1.4.10"   # numeric, not lexicographic
    assert resolve_version("1", available) == "1.4.10"
    assert resolve_version("2.0.0-rc.1", available) == "2.0.0-rc.1"  # exact prerelease OK
    with pytest.raises(VersionError):
        resolve_version("2", available)  # only a pre-release exists for 2.x
    with pytest.raises(VersionError):
        resolve_version("3.0.0", available)
    with pytest.raises(VersionError):
        resolve_version("latest", ["1.0.0-alpha"])  # no stable at all
