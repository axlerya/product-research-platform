"""Unit-тесты разрешения устройства/точности reranker (изолированный модуль)."""

import pytest

from embedding_service.application.exceptions import ProbeFailed
from embedding_service.infrastructure.reranking.device import (
    resolve_device,
    resolve_precision,
)


class TestResolveDevice:
    def test_cpu_explicit(self) -> None:
        assert resolve_device("cpu") == "cpu"

    def test_auto_prefers_cuda_when_available(self) -> None:
        assert resolve_device("auto", cuda_available=lambda: True) == "cuda"

    def test_auto_falls_back_to_cpu(self) -> None:
        assert resolve_device("auto", cuda_available=lambda: False) == "cpu"

    def test_cuda_ok_when_available(self) -> None:
        assert resolve_device("cuda", cuda_available=lambda: True) == "cuda"

    def test_cuda_unavailable_raises(self) -> None:
        with pytest.raises(ProbeFailed):
            resolve_device("cuda", cuda_available=lambda: False)

    def test_unknown_device_raises(self) -> None:
        with pytest.raises(ProbeFailed):
            resolve_device("tpu")


class TestResolvePrecision:
    def test_cpu_forces_fp32(self) -> None:
        assert resolve_precision("bf16", "cpu") == "fp32"

    def test_bf16_supported(self) -> None:
        assert (
            resolve_precision("bf16", "cuda", bf16_supported=lambda: True)
            == "bf16"
        )

    def test_bf16_unsupported_falls_back(self) -> None:
        assert (
            resolve_precision("bf16", "cuda", bf16_supported=lambda: False)
            == "fp16"
        )

    @pytest.mark.parametrize("precision", ["fp16", "fp32"])
    def test_passthrough(self, precision: str) -> None:
        assert resolve_precision(precision, "cuda") == precision

    def test_unknown_defaults_fp16(self) -> None:
        assert resolve_precision("int8", "cuda") == "fp16"
