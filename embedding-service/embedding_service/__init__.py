"""embedding-service — единый inference-слой dense+sparse эмбеддингов.

Пакет разбит на четыре слоя Clean Architecture (снаружи-внутрь):
``presentation`` → ``infrastructure`` → ``application`` → ``domain``.
Правило зависимостей — исполняемый инвариант (import-linter + ruff).
"""

__version__ = "0.1.0"
