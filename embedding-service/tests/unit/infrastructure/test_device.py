"""Unit-тесты resolve_device / resolve_precision (torch через инъекцию)."""

import pytest

from embedding_service.application.exceptions import ProbeFailed
from embedding_service.infrastructure.embedding.device import (
    resolve_device,
    resolve_precision,
)


class TestResolveDevice:
    def test_cpu_no_torch_import(self) -> None:
        assert resolve_device("cpu") == "cpu"

    def test_auto_with_cuda(self) -> None:
        assert resolve_device("auto", cuda_available=lambda: True) == "cuda"

    def test_auto_without_cuda(self) -> None:
        assert resolve_device("auto", cuda_available=lambda: False) == "cpu"

    def test_cuda_available(self) -> None:
        assert resolve_device("cuda", cuda_available=lambda: True) == "cuda"

    def test_cuda_unavailable_raises(self) -> None:
        with pytest.raises(ProbeFailed):
            resolve_device("cuda", cuda_available=lambda: False)

    def test_unknown_device_raises(self) -> None:
        with pytest.raises(ProbeFailed):
            resolve_device("tpu", cuda_available=lambda: True)


class TestResolvePrecision:
    def test_cpu_forces_fp32(self) -> None:
        assert resolve_precision("fp16", "cpu") == "fp32"

    def test_gpu_fp16(self) -> None:
        assert resolve_precision("fp16", "cuda") == "fp16"

    def test_gpu_fp32(self) -> None:
        assert resolve_precision("fp32", "cuda") == "fp32"

    def test_gpu_bf16_supported(self) -> None:
        assert (
            resolve_precision("bf16", "cuda", bf16_supported=lambda: True)
            == "bf16"
        )

    def test_gpu_bf16_unsupported_downgrades(self) -> None:
        assert (
            resolve_precision("bf16", "cuda", bf16_supported=lambda: False)
            == "fp16"
        )

    def test_gpu_unknown_defaults_fp16(self) -> None:
        assert resolve_precision("weird", "cuda") == "fp16"
