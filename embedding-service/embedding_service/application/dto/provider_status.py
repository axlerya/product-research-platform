"""DTO ``ProviderStatus`` — результат ``EmbeddingProvider.probe()``."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Статус провайдера для readiness и диагностики.

    Attributes:
        loaded: Загружена ли модель.
        device: Устройство исполнения (``"cpu"`` / ``"cuda:0"``).
        precision: Точность (``"fp32"`` / ``"fp16"`` / ``"bf16"``).
        degraded: Признак деградации (повторные CUDA-ошибки).
        model_key: Строковый ключ модели (== ``EmbeddingModelId.key``).
    """

    loaded: bool
    device: str
    precision: str
    degraded: bool
    model_key: str
