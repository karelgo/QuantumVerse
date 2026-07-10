from quantumverse.canonical import canonical_bytes, digest_bytes, digest_json, is_digest


def test_canonical_is_key_order_independent():
    assert canonical_bytes({"b": 1, "a": [2, 3]}) == canonical_bytes({"a": [2, 3], "b": 1})


def test_canonical_has_no_insignificant_whitespace():
    assert canonical_bytes({"a": 1, "b": "x"}) == b'{"a":1,"b":"x"}'


def test_digest_shape_and_predicate():
    d = digest_bytes(b"hello")
    assert d.startswith("sha256:") and len(d) == 7 + 64
    assert is_digest(d)
    assert not is_digest(d.upper())
    assert not is_digest("sha256:zz")
    assert not is_digest("md5:" + "0" * 64)


def test_digest_json_equals_digest_of_canonical_bytes():
    obj = {"z": 1.5, "a": None, "nested": {"k": [1, 2]}}
    assert digest_json(obj) == digest_bytes(canonical_bytes(obj))
