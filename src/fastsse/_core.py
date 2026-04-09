from __future__ import annotations

__all__ = [
    "SSE",
    "AsyncDataStream",
    "AsyncSSEStream",
    "Data",
    "Encoder",
    "EventStream",
    "Response",
    "SyncDataStream",
    "SyncSSEStream",
    "add_sse_api_route",
    "default_encoder",
]


import inspect
import typing
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable, Mapping
from typing import Any, Generic, TypeVar, cast

import fastapi
import fastapi.openapi.utils
import pydantic
import pydantic.fields
import sse_starlette
import starlette.background
import starlette.concurrency

T = TypeVar("T")


class SSE(pydantic.BaseModel, Generic[T]):
    data: T
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    @classmethod
    def model_parametrized_name(cls, params: tuple[type[Any], ...]) -> str:
        if len(params) == 1 and typing.get_origin(params[0]) is typing.Annotated:
            for arg in typing.get_args(params[0]):
                if isinstance(arg, pydantic.fields.FieldInfo) and arg.title is not None:
                    return f"{cls.__name__}[{arg.title}]"

        return super().model_parametrized_name(params)


Data = Any
SyncDataStream = Iterable[Data]
AsyncDataStream = AsyncIterable[Data]
SyncSSEStream = Iterable[SSE[Data]]
AsyncSSEStream = AsyncIterable[SSE[Data]]
EventStream = SyncDataStream | AsyncDataStream | SyncSSEStream | AsyncSSEStream

Encoder = Callable[[Data | SSE[Data]], sse_starlette.sse.Content]


def default_encoder(data: Data | SSE[Data]) -> sse_starlette.event.JSONServerSentEvent:
    sse = data if isinstance(data, SSE) else SSE(data=data)
    return sse_starlette.event.JSONServerSentEvent(**sse.model_dump(mode="json", exclude_none=True, by_alias=True))


class Response(sse_starlette.EventSourceResponse):
    def __init__(
        self,
        content: EventStream,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str = "text/event-stream",
        background: starlette.background.BackgroundTask | None = None,
        encoder: Encoder = default_encoder,
    ) -> None:
        if not isinstance(content, AsyncIterable):
            content = starlette.concurrency.iterate_in_threadpool(content)

        async def content_stream(
            data_stream: AsyncDataStream | AsyncSSEStream,
        ) -> AsyncIterator[sse_starlette.sse.Content]:
            async for data in data_stream:
                yield encoder(data)

        super().__init__(
            content=content_stream(content),
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


def _detect_response_model(endpoint: Callable) -> type:
    return_type = typing.get_type_hints(endpoint, include_extras=True).get("return")
    if return_type is None:
        if inspect.isgeneratorfunction(endpoint) or inspect.isasyncgenfunction(endpoint):
            return SSE[Any]

        raise Exception

    origin = typing.get_origin(return_type)
    if not (isinstance(origin, type) and issubclass(origin, (Iterable, AsyncIterable))):
        raise Exception

    args = typing.get_args(return_type)
    assert len(args) == 1
    return cast(type, args[0])


def _get_response_schema(response_model: type[SSE]) -> dict[str, Any]:
    model_field = fastapi.openapi.utils.ModelField(
        field_info=pydantic.fields.FieldInfo(annotation=response_model),
        name=response_model.__name__,
        mode="serialization",
    )
    field_mapping, _ = fastapi.openapi.utils.get_definitions(
        fields=[model_field],
        model_name_map=fastapi.openapi.utils.get_model_name_map({response_model}),
    )
    return field_mapping[(model_field, model_field.mode)]


def add_sse_api_route(
    router: fastapi.FastAPI | fastapi.APIRouter,
    /,
    path: str,
    endpoint: Callable[..., Any],
    *,
    response_model: Any = None,
    status_code: int = fastapi.status.HTTP_200_OK,
    responses: dict[int | str, dict[str, Any]] | None = None,
    **kwargs: Any,
) -> None:
    if isinstance(router, fastapi.FastAPI):
        router = router.router

    if response_model is None:
        response_model = _detect_response_model(endpoint)
    if not (isinstance(response_model, type) and not issubclass(response_model, SSE)):
        response_model = SSE[response_model]

    if responses is None:
        responses = {}
    responses[status_code] = {"content": {"text/event-stream": {"schema": _get_response_schema(response_model)}}}

    router.add_api_route(
        path,
        endpoint,
        response_class=Response,
        response_model=response_model,
        responses=responses,
        status_code=status_code,
        **kwargs,
    )
