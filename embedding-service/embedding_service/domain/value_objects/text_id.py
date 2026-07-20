"""Value object ``TextId`` — непрозрачный id элемента батча."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import EmptyTextError


@dataclass(frozen=True, slots=True)
class TextId:
    """Идентификатор элемента батча для корреляции и сохранения порядка.

    Значение сохраняется дословно (это ключ корреляции у потребителя),
    отвергается только пустой/пробельный.

    Attributes:
        value: Непрозрачный идентификатор.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise EmptyTextError("Идентификатор не может быть пустым")
