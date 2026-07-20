"""Маппинг доменных VO ↔ proto (DenseVector/SparseVector/QueryEmbedding)."""

from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.token_count import TokenCount
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)


def to_query_embedding(
    embedding: Embedding, token_count: TokenCount
) -> pb.QueryEmbedding:
    """Строит proto ``QueryEmbedding`` из доменного ``Embedding``."""
    return pb.QueryEmbedding(
        dense=pb.DenseVector(values=list(embedding.dense.values)),
        sparse=pb.SparseVector(
            indices=list(embedding.sparse.indices),
            values=list(embedding.sparse.values),
        ),
        token_count=token_count.value,
    )
