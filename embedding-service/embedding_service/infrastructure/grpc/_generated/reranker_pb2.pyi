from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RerankDocument(_message.Message):
    __slots__ = ("id", "text")
    ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    id: str
    text: str
    def __init__(self, id: _Optional[str] = ..., text: _Optional[str] = ...) -> None: ...

class RerankRequest(_message.Message):
    __slots__ = ("query", "documents", "top_n", "return_documents")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    DOCUMENTS_FIELD_NUMBER: _ClassVar[int]
    TOP_N_FIELD_NUMBER: _ClassVar[int]
    RETURN_DOCUMENTS_FIELD_NUMBER: _ClassVar[int]
    query: str
    documents: _containers.RepeatedCompositeFieldContainer[RerankDocument]
    top_n: int
    return_documents: bool
    def __init__(self, query: _Optional[str] = ..., documents: _Optional[_Iterable[_Union[RerankDocument, _Mapping]]] = ..., top_n: _Optional[int] = ..., return_documents: _Optional[bool] = ...) -> None: ...

class RankedDocument(_message.Message):
    __slots__ = ("id", "index", "score", "text")
    ID_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    id: str
    index: int
    score: float
    text: str
    def __init__(self, id: _Optional[str] = ..., index: _Optional[int] = ..., score: _Optional[float] = ..., text: _Optional[str] = ...) -> None: ...

class RerankResponse(_message.Message):
    __slots__ = ("results", "model_version")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[RankedDocument]
    model_version: str
    def __init__(self, results: _Optional[_Iterable[_Union[RankedDocument, _Mapping]]] = ..., model_version: _Optional[str] = ...) -> None: ...
