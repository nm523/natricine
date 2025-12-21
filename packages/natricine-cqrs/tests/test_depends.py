"""Tests for dependency injection."""

from typing import Annotated

import pytest

from natricine_cqrs import Depends
from natricine_cqrs.depends import call_with_deps, resolve_dependencies

pytestmark = pytest.mark.anyio

DEP_VALUE_42 = 42
DEP_VALUE_10 = 10
DEP_VALUE_20 = 20
RESULT_15 = 15
RESULT_21 = 21


class TestDepends:
    async def test_resolve_simple_dependency(self) -> None:
        def get_value() -> int:
            return DEP_VALUE_42

        async def handler(x: Annotated[int, Depends(get_value)]) -> int:
            return x

        resolved = await resolve_dependencies(handler, {})
        assert resolved["x"] == DEP_VALUE_42

    async def test_resolve_async_dependency(self) -> None:
        async def get_value() -> str:
            return "async_value"

        async def handler(x: Annotated[str, Depends(get_value)]) -> str:
            return x

        resolved = await resolve_dependencies(handler, {})
        assert resolved["x"] == "async_value"

    async def test_resolve_nested_dependencies(self) -> None:
        def get_base() -> int:
            return DEP_VALUE_10

        def get_derived(base: Annotated[int, Depends(get_base)]) -> int:
            return base * 2

        async def handler(value: Annotated[int, Depends(get_derived)]) -> int:
            return value

        resolved = await resolve_dependencies(handler, {})
        assert resolved["value"] == DEP_VALUE_20

    async def test_provided_args_not_resolved(self) -> None:
        def get_value() -> int:
            return DEP_VALUE_42

        async def handler(cmd: str, x: Annotated[int, Depends(get_value)]) -> None:
            pass

        resolved = await resolve_dependencies(handler, {"cmd": "my_command"})
        assert resolved["cmd"] == "my_command"
        assert resolved["x"] == DEP_VALUE_42


class TestCallWithDeps:
    async def test_call_sync_function(self) -> None:
        def get_dep() -> int:
            return 5

        def add(a: int, b: Annotated[int, Depends(get_dep)]) -> int:
            return a + b

        result = await call_with_deps(add, {"a": 10})
        assert result == RESULT_15

    async def test_call_async_function(self) -> None:
        async def get_dep() -> int:
            return 7

        async def multiply(a: int, b: Annotated[int, Depends(get_dep)]) -> int:
            return a * b

        result = await call_with_deps(multiply, {"a": 3})
        assert result == RESULT_21

    async def test_call_with_multiple_deps(self) -> None:
        def get_x() -> int:
            return 2

        def get_y() -> int:
            return 3

        async def compute(
            a: int,
            x: Annotated[int, Depends(get_x)],
            y: Annotated[int, Depends(get_y)],
        ) -> int:
            return a + x + y

        result = await call_with_deps(compute, {"a": 10})
        assert result == RESULT_15
