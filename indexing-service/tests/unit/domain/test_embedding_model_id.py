"""Тесты value object ``EmbeddingModelId`` — идентификатор модели."""

import pytest

from indexing_service.domain.exceptions import InvalidModelIdError
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)


def test_key_format():
    model_id = EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="abc123def456",
        pooling="cls",
        normalized=True,
        dim=1024,
    )
    assert model_id.key == "BAAI/bge-m3@abc123def456|pool=cls|norm=1|dim=1024"


def test_key_reflects_not_normalized():
    model_id = EmbeddingModelId("m", "r", "mean", normalized=False, dim=8)
    assert model_id.key == "m@r|pool=mean|norm=0|dim=8"


def test_rejects_non_positive_dim():
    with pytest.raises(InvalidModelIdError):
        EmbeddingModelId("m", "r", "cls", normalized=True, dim=0)


def test_rejects_blank_name():
    with pytest.raises(InvalidModelIdError):
        EmbeddingModelId(" ", "r", "cls", normalized=True, dim=8)


def test_equality():
    left = EmbeddingModelId("m", "r", "cls", normalized=True, dim=8)
    right = EmbeddingModelId("m", "r", "cls", normalized=True, dim=8)
    assert left == right
