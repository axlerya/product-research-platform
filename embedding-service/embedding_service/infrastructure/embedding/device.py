"""Разрешение устройства и точности инференса.

``torch`` импортируется лениво только когда нужен GPU-запрос; проверки CUDA
инъектируются (``cuda_available``/``bf16_supported``) для тестируемости.
"""

from collections.abc import Callable

from embedding_service.application.exceptions import ProbeFailed

CudaCheck = Callable[[], bool]


def resolve_device(
    setting: str, *, cuda_available: CudaCheck | None = None
) -> str:
    """Возвращает финальную строку устройства для загрузчика модели.

    Args:
        setting: ``"auto"`` | ``"cpu"`` | ``"cuda"``.
        cuda_available: Проверка доступности CUDA (для тестов); по умолчанию
            ленивый ``torch.cuda.is_available``.

    Returns:
        ``"cpu"`` или ``"cuda"``.

    Raises:
        ProbeFailed: Если запрошен ``cuda`` при недоступной CUDA или задано
            неизвестное устройство (permanent — readiness не поднимется).
    """
    if setting == "cpu":
        return "cpu"
    available = cuda_available or _cuda_available
    if setting == "auto":
        return "cuda" if available() else "cpu"
    if setting == "cuda":
        if not available():
            raise ProbeFailed("EMBEDDING_DEVICE=cuda, но CUDA недоступна")
        return "cuda"
    raise ProbeFailed(f"неизвестное устройство: {setting}")


def resolve_precision(
    setting: str,
    device: str,
    *,
    bf16_supported: CudaCheck | None = None,
) -> str:
    """Выбирает эффективную точность под устройство/архитектуру.

    На CPU fp16/bf16 не поддержаны/медленны → всегда ``fp32``. На GPU: ``bf16``
    только на Ampere+ (иначе откат на ``fp16``); ``fp16``/``fp32`` — как задано;
    прочее — дефолт ``fp16``.
    """
    if device == "cpu":
        return "fp32"
    if setting == "bf16":
        supported = bf16_supported or _bf16_supported
        return "bf16" if supported() else "fp16"
    if setting in ("fp16", "fp32"):
        return setting
    return "fp16"


def _cuda_available() -> bool:  # pragma: no cover - требует torch/GPU
    import torch

    return torch.cuda.is_available()


def _bf16_supported() -> bool:  # pragma: no cover - требует torch/GPU
    import torch

    return torch.cuda.is_bf16_supported()
