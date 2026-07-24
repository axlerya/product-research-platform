from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DenseVector(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, values: _Optional[_Iterable[float]] = ...) -> None: ...

class SparseVector(_message.Message):
    __slots__ = ("indices", "values")
    INDICES_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    indices: _containers.RepeatedScalarFieldContainer[int]
    values: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, indices: _Optional[_Iterable[int]] = ..., values: _Optional[_Iterable[float]] = ...) -> None: ...

class QueryEmbedding(_message.Message):
    __slots__ = ("dense", "sparse", "token_count")
    DENSE_FIELD_NUMBER: _ClassVar[int]
    SPARSE_FIELD_NUMBER: _ClassVar[int]
    TOKEN_COUNT_FIELD_NUMBER: _ClassVar[int]
    dense: DenseVector
    sparse: SparseVector
    token_count: int
    def __init__(self, dense: _Optional[_Union[DenseVector, _Mapping]] = ..., sparse: _Optional[_Union[SparseVector, _Mapping]] = ..., token_count: _Optional[int] = ...) -> None: ...

class EmbedQueryRequest(_message.Message):
    __slots__ = ("text", "request_id")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    text: str
    request_id: str
    def __init__(self, text: _Optional[str] = ..., request_id: _Optional[str] = ...) -> None: ...

class EmbedQueryResponse(_message.Message):
    __slots__ = ("embedding", "model_version", "dim")
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    DIM_FIELD_NUMBER: _ClassVar[int]
    embedding: QueryEmbedding
    model_version: str
    dim: int
    def __init__(self, embedding: _Optional[_Union[QueryEmbedding, _Mapping]] = ..., model_version: _Optional[str] = ..., dim: _Optional[int] = ...) -> None: ...

class EmbedQueriesRequest(_message.Message):
    __slots__ = ("texts", "request_id")
    TEXTS_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    texts: _containers.RepeatedScalarFieldContainer[str]
    request_id: str
    def __init__(self, texts: _Optional[_Iterable[str]] = ..., request_id: _Optional[str] = ...) -> None: ...

class EmbedQueriesResponse(_message.Message):
    __slots__ = ("embeddings", "model_version", "dim")
    EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    DIM_FIELD_NUMBER: _ClassVar[int]
    embeddings: _containers.RepeatedCompositeFieldContainer[QueryEmbedding]
    model_version: str
    dim: int
    def __init__(self, embeddings: _Optional[_Iterable[_Union[QueryEmbedding, _Mapping]]] = ..., model_version: _Optional[str] = ..., dim: _Optional[int] = ...) -> None: ...
