from collections.abc import Callable
from typing import Any

import fastapi
import fastapi.types

from ._core import add_sse_api_route


class _APIRouterMixin(fastapi.APIRouter):
    def add_sse_api_route(self, *args: Any, **kwargs: Any) -> None:
        add_sse_api_route(self, *args, **kwargs)

    def sse(
        self, path: str, **kwargs: Any
    ) -> Callable[[fastapi.types.DecoratedCallable], fastapi.types.DecoratedCallable]:
        def decorator(endpoint: fastapi.types.DecoratedCallable) -> fastapi.types.DecoratedCallable:
            self.add_sse_api_route(path, endpoint, **kwargs)
            return endpoint

        return decorator


class APIRouter(_APIRouterMixin):
    pass
