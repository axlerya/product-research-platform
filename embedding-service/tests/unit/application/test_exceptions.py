"""Unit-тесты прикладных исключений и мостов из домена.

Иерархия ApplicationError → PermanentError/TransientError задаёт ось
«park vs retry»; to_application_error/to_item_error переводят домен.
"""

import pytest

from embedding_service.application.exceptions import (
    ApplicationError,
    InferenceError,
    InferenceOverloadedError,
    InferenceTimeoutError,
    ModelNotReadyError,
    PermanentError,
    ProbeFailed,
    TransientError,
    ValidationError,
    to_application_error,
    to_item_error,
)
from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    EmptyBatchError,
    EmptyTextError,
    InvalidModelIdError,
    InvalidVectorError,
    RequestTooLargeError,
    TextTooLongError,
    TokensExceededError,
)
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "exc_type",
        [ValidationError, ProbeFailed],
    )
    def test_permanent_subclasses(self, exc_type: type) -> None:
        assert issubclass(exc_type, PermanentError)
        assert issubclass(exc_type, ApplicationError)
        assert not issubclass(exc_type, TransientError)

    @pytest.mark.parametrize(
        "exc_type",
        [
            InferenceError,
            InferenceTimeoutError,
            InferenceOverloadedError,
            ModelNotReadyError,
        ],
    )
    def test_transient_subclasses(self, exc_type: type) -> None:
        assert issubclass(exc_type, TransientError)
        assert issubclass(exc_type, ApplicationError)
        assert not issubclass(exc_type, PermanentError)

    def test_validation_carries_domain_type(self) -> None:
        err = ValidationError("пусто", domain_type="EmptyTextError")
        assert err.domain_type == "EmptyTextError"
        assert str(err) == "пусто"

    def test_validation_domain_type_optional(self) -> None:
        assert ValidationError("x").domain_type is None

    def test_overloaded_carries_queue_depth(self) -> None:
        err = InferenceOverloadedError(queue_depth=257)
        assert err.queue_depth == 257


class TestToApplicationError:
    @pytest.mark.parametrize(
        "domain_exc",
        [
            EmptyTextError("пусто"),
            TextTooLongError("длинно"),
            TokensExceededError("токены"),
            EmptyBatchError("нет элементов"),
            BatchTooLargeError("много"),
            RequestTooLargeError("байты"),
        ],
    )
    def test_input_validation_maps_to_validation_error(
        self, domain_exc: Exception
    ) -> None:
        app_exc = to_application_error(domain_exc)
        assert isinstance(app_exc, ValidationError)
        assert app_exc.domain_type == type(domain_exc).__name__

    @pytest.mark.parametrize(
        "domain_exc",
        [InvalidVectorError("форма"), InvalidModelIdError("id")],
    )
    def test_form_defect_maps_to_inference_error(
        self, domain_exc: Exception
    ) -> None:
        app_exc = to_application_error(domain_exc)
        assert isinstance(app_exc, InferenceError)
        assert not isinstance(app_exc, ValidationError)


class TestToItemError:
    @pytest.mark.parametrize(
        ("domain_exc", "code"),
        [
            (EmptyTextError("x"), EmbeddingErrorCode.EMPTY_TEXT),
            (TextTooLongError("x"), EmbeddingErrorCode.TEXT_TOO_LONG),
            (TokensExceededError("x"), EmbeddingErrorCode.TOKENS_EXCEEDED),
        ],
    )
    def test_known_codes(
        self, domain_exc: Exception, code: EmbeddingErrorCode
    ) -> None:
        item = to_item_error(domain_exc)
        assert item.code is code
        assert item.message == str(domain_exc)

    def test_unknown_defaults_to_inference_failed(self) -> None:
        item = to_item_error(InvalidVectorError("форма"))
        assert item.code is EmbeddingErrorCode.INFERENCE_FAILED
