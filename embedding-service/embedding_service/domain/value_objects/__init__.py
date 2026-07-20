"""Доменные value objects embedding-service.

Векторные VO (``DenseVector``, ``SparseVector``, ``EmbeddingModelId``,
``Embedding``) — публичный wire-контракт формы; остальные окружают батч.
"""

from embedding_service.domain.value_objects.batch_result import (
    BatchEmbeddingResult,
)
from embedding_service.domain.value_objects.contract_version import (
    ContractVersion,
)
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
    ItemError,
)
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount

__all__ = [
    "BatchEmbeddingResult",
    "ContractVersion",
    "DenseVector",
    "Embedding",
    "EmbeddingErrorCode",
    "EmbeddingItemResult",
    "EmbeddingKind",
    "EmbeddingLimits",
    "EmbeddingModelId",
    "EmbeddingRequestItem",
    "EmbeddingText",
    "ItemError",
    "SparseVector",
    "TextId",
    "TokenCount",
]
