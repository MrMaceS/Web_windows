"""tests/test_security.py — hash_password/verify_password: форматы и подделанные хеши."""

from security import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong password", stored)


def test_hash_is_salted_differently_each_time():
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_verify_rejects_malformed_hash_missing_parts():
    assert verify_password("anything", "not-a-real-hash") is False


def test_verify_rejects_wrong_algorithm_prefix():
    stored = hash_password("x").replace("pbkdf2_sha256", "md5", 1)
    assert verify_password("x", stored) is False


def test_verify_rejects_non_hex_salt_or_digest():
    assert verify_password("x", "pbkdf2_sha256$260000$zz$zz") is False


def test_verify_rejects_non_integer_iterations():
    assert verify_password("x", "pbkdf2_sha256$notanumber$aa$bb") is False
