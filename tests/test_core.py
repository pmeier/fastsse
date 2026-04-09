from typing import Annotated

import fastapi
import pydantic
import pytest
import sse_starlette.event

from fastsse import SSE, add_sse_api_route, default_encoder


class SomeModel(pydantic.BaseModel):
    foo: str
    bar: int = pydantic.Field(serialization_alias="BAR")


class TestSSE:
    @pytest.mark.parametrize(
        ("concrete_type", "expected_inner_name"),
        [
            (str, "str"),
            (str | int, "Union[str, int]"),
            (Annotated[str, pydantic.Field(title="my-title")], "my-title"),
            (Annotated[str, pydantic.Field(min_length=3), pydantic.Field(title="my-title")], "my-title"),
            (
                Annotated[str, pydantic.Field(title="my-first-title"), pydantic.Field(title="my-second-title")],
                "my-first-title",
            ),
        ],
    )
    def test_parametrized_name(self, concrete_type, expected_inner_name):
        assert SSE[concrete_type].__name__ == f"SSE[{expected_inner_name}]"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("foo", sse_starlette.JSONServerSentEvent(data="foo")),
        (5, sse_starlette.JSONServerSentEvent(data=5)),
        (SomeModel(foo="foo", bar=5), sse_starlette.JSONServerSentEvent(data={"foo": "foo", "BAR": 5})),
        (SSE(data="foo", event="some-event"), sse_starlette.JSONServerSentEvent(data="foo", event="some-event")),
        (SSE(data=5, id="some-id"), sse_starlette.JSONServerSentEvent(data=5, id="some-id")),
        (
            SSE(data=SomeModel(foo="foo", bar=5), retry=3),
            sse_starlette.JSONServerSentEvent(data={"foo": "foo", "BAR": 5}, retry=3),
        ),
    ],
)
def test_default_encoder(data, expected):
    actual = default_encoder(data)
    assert isinstance(actual, sse_starlette.event.ServerSentEvent)
    assert actual.data == expected.data
    assert actual.event == expected.event
    assert actual.id == expected.id
    assert actual.retry == expected.retry


"""
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
"""


class TestAddSSEAPIRoute:
    @pytest.mark.parametrize("router", [fastapi.FastAPI(), fastapi.APIRouter()])
    def test_smoke(self, router):
        def endpoint():
            yield "foo"

        add_sse_api_route(router, path="", endpoint=endpoint)
