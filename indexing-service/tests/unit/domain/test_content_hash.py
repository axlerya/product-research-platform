"""Тесты value object ``ContentHash`` (sha256 составного текста)."""

from indexing_service.domain.value_objects.content_hash import ContentHash

# Известный sha256("abc").
_SHA256_ABC = (
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
)


def test_of_is_deterministic():
    assert ContentHash.of("abc") == ContentHash.of("abc")


def test_of_differs_for_different_text():
    assert ContentHash.of("abc") != ContentHash.of("abd")


def test_value_is_hex_sha256():
    hashed = ContentHash.of("abc")
    assert len(hashed.value) == 64
    assert hashed.value == _SHA256_ABC
