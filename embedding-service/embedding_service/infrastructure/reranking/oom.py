"""OOM-guard reranker: обобщённый split-retry при CUDA OOM.

Чистая функция; в отличие от embedding-варианта обобщена по типу элемента
(``I``) — элемент батча reranker — это пара ``[query, doc]``, а не строка.
Тип OOM-исключения инъектируется, поэтому логика тестируется без torch.
"""

from collections.abc import Callable, Sequence


def split_retry[I, T](
    encode: Callable[[list[I]], list[T]],
    batch: Sequence[I],
    *,
    oom_types: tuple[type[BaseException], ...],
    on_oom: Callable[[], None],
    min_split: int = 1,
) -> list[T]:
    """Кодирует батч, при OOM дробит пополам (порядок сохранён).

    Args:
        encode: Кодирующая функция (блокирующая), результат — список по входу.
        batch: Элементы батча (для reranker — пары ``[query, doc]``).
        oom_types: Типы OOM-исключений (пустой кортеж → без обработки OOM).
        on_oom: Колбэк очистки кэша аллокатора (``empty_cache``).
        min_split: Минимальный размер, ниже которого OOM пробрасывается.

    Returns:
        Результаты в порядке входа (конкатенация половин при дроблении).

    Raises:
        BaseException: Исходный OOM, если он повторяется на батче ``<=
            min_split``.
    """
    items = list(batch)
    try:
        return encode(items)
    except oom_types:
        on_oom()
        if len(items) <= min_split:
            raise
        mid = len(items) // 2
        left = split_retry(
            encode,
            items[:mid],
            oom_types=oom_types,
            on_oom=on_oom,
            min_split=min_split,
        )
        right = split_retry(
            encode,
            items[mid:],
            oom_types=oom_types,
            on_oom=on_oom,
            min_split=min_split,
        )
        return left + right
