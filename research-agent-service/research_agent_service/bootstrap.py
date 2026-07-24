"""Composition root — сборка адаптеров и use cases (вне юнит-покрытия).

Проводка слоёв: инфраструктурные клиенты (gRPC/Qdrant/Redis/catalog/LLM) →
прикладные сервисы и оркестратор → use cases → контейнер API. Клиенты
создаются лениво (без подключения); строить контейнер нужно в рамках
работающего event loop (для gRPC aio-каналов).
"""

import grpc
import httpx
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis, from_url
from sqlalchemy import text

from research_agent_service.application.services.price_analysis import (
    PriceAnalysisService,
)
from research_agent_service.application.services.product_catalog_rag import (
    ProductCatalogRagService,
)
from research_agent_service.application.services.source_validation import (
    SourceValidator,
)
from research_agent_service.application.services.web_search import (
    WebSearchService,
)
from research_agent_service.application.use_cases.answer_query import (
    AnswerQueryUseCase,
)
from research_agent_service.application.use_cases.read_queries import (
    GetQueryUseCase,
    ListQueriesUseCase,
)
from research_agent_service.application.use_cases.submit_feedback import (
    SubmitFeedbackUseCase,
)
from research_agent_service.infrastructure.agent.executor import ToolExecutor
from research_agent_service.infrastructure.agent.llm import build_chat_model
from research_agent_service.infrastructure.agent.orchestrator import (
    LangGraphOrchestrator,
)
from research_agent_service.infrastructure.catalog.rest_client import (
    HttpCatalogClient,
)
from research_agent_service.infrastructure.config import Settings
from research_agent_service.infrastructure.db.engine import (
    build_engine,
    build_session_factory,
)
from research_agent_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from research_agent_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc,
    reranker_pb2_grpc,
)
from research_agent_service.infrastructure.grpc.embedding_client import (
    GrpcEmbeddingClient,
)
from research_agent_service.infrastructure.grpc.reranker_client import (
    GrpcRerankerClient,
)
from research_agent_service.infrastructure.observability.metrics import (
    MetricsRecorder,
)
from research_agent_service.infrastructure.qdrant.vector_search import (
    QdrantVectorSearch,
)
from research_agent_service.infrastructure.redis.cache import RedisCache
from research_agent_service.infrastructure.redis.rate_limiter import (
    RedisTokenBucket,
)
from research_agent_service.infrastructure.services.clock import SystemClock
from research_agent_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)
from research_agent_service.infrastructure.websearch.sanitizer import (
    HtmlContentSanitizer,
)
from research_agent_service.infrastructure.websearch.serper import (
    SerperWebSearch,
)
from research_agent_service.infrastructure.websearch.tavily import (
    TavilyWebSearch,
)
from research_agent_service.presentation.api.services import ApiServices


def _build_web_provider(
    settings: Settings, client: httpx.AsyncClient
) -> WebSearchService:
    if settings.web_search_provider == "serper":
        provider = SerperWebSearch(
            client=client, api_key=settings.web_search_api_key
        )
    else:
        provider = TavilyWebSearch(
            client=client, api_key=settings.web_search_api_key
        )
    return WebSearchService(provider=provider, sanitizer=HtmlContentSanitizer())


class Container:
    """Владелец ресурсов и собранных use cases."""

    def __init__(self, settings: Settings) -> None:
        self._embedding_channel = grpc.aio.insecure_channel(
            settings.embedding_grpc_target
        )
        self._reranker_channel = grpc.aio.insecure_channel(
            settings.reranker_grpc_target
        )
        self._redis: Redis = from_url(settings.redis_url)
        self._qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        self._catalog_http = httpx.AsyncClient(
            base_url=settings.catalog_base_url
        )
        self._web_http = httpx.AsyncClient()
        self._engine = build_engine(settings.database_url)

        clock = SystemClock()
        ids = Uuid7Generator()
        embedding = GrpcEmbeddingClient(
            stub=embedding_pb2_grpc.EmbeddingServiceStub(
                self._embedding_channel
            )
        )
        reranker = GrpcRerankerClient(
            stub=reranker_pb2_grpc.RerankerServiceStub(self._reranker_channel)
        )
        catalog = HttpCatalogClient(client=self._catalog_http)
        rag = ProductCatalogRagService(
            embedding=embedding,
            vector_search=QdrantVectorSearch(
                client=self._qdrant, collection=settings.qdrant_collection
            ),
            reranker=reranker,
            catalog=catalog,
            clock=clock,
        )
        executor = ToolExecutor(
            rag=rag,
            price=PriceAnalysisService(catalog=catalog),
            web=_build_web_provider(settings, self._web_http),
            clock=clock,
            id_generator=ids,
        )
        orchestrator = LangGraphOrchestrator(
            model=build_chat_model(settings.llm),
            executor=executor,
            id_generator=ids,
        )

        uow = SqlAlchemyUnitOfWork(
            session_factory=build_session_factory(self._engine)
        )
        self.api_services = ApiServices(
            answer_query=AnswerQueryUseCase(
                uow=uow,
                orchestrator=orchestrator,
                rate_limiter=RedisTokenBucket(client=self._redis),
                source_validator=SourceValidator(),
                id_generator=ids,
                clock=clock,
                model=settings.llm.model,
                cache=RedisCache(client=self._redis),
            ),
            submit_feedback=SubmitFeedbackUseCase(
                uow=uow, id_generator=ids, clock=clock
            ),
            list_queries=ListQueriesUseCase(uow=uow),
            get_query=GetQueryUseCase(uow=uow),
            readiness=self._readiness,
            metrics=MetricsRecorder.create(model=settings.llm.model),
        )

    async def _readiness(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await self._redis.ping()
        except Exception:
            return False
        return True

    async def aclose(self) -> None:
        """Закрывает каналы и клиенты."""
        await self._embedding_channel.close()
        await self._reranker_channel.close()
        await self._redis.aclose()
        await self._qdrant.close()
        await self._catalog_http.aclose()
        await self._web_http.aclose()
        await self._engine.dispose()


def build_container(settings: Settings) -> Container:
    """Собирает контейнер зависимостей из настроек."""
    return Container(settings)
