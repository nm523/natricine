"""Dependency injection inspired by FastAPI's Depends."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import (
    Annotated,
    Any,
    Generic,
    ParamSpec,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

import anyio

P = ParamSpec("P")
R = TypeVar("R")
T_co = TypeVar("T_co", covariant=True)


@dataclass(frozen=True)
class Depends(Generic[T_co]):
    """Marker for dependency injection in handler signatures.

    Generic over the return type of the dependency function, enabling
    type checkers to verify that the dependency returns the expected type.

    Usage with Annotated (preferred):
        async def get_database() -> Database:
            return Database()

        @command_bus.handler
        async def handle_cmd(
            cmd: MyCommand,
            db: Annotated[Database, Depends(get_database)],
        ) -> None:
            await db.save(cmd)

    The type parameter is inferred from the dependency function's return type,
    allowing type checkers to verify consistency with the Annotated type.
    """

    dependency: Callable[..., T_co | Awaitable[T_co]]


def _get_depends_from_annotation(annotation: Any) -> Depends | None:
    """Extract Depends from an Annotated type hint."""
    if get_origin(annotation) is Annotated:
        for arg in get_args(annotation)[1:]:
            if isinstance(arg, Depends):
                return arg
    return None


async def resolve_dependencies(
    func: Callable[..., Any],
    provided: dict[str, Any],
) -> dict[str, Any]:
    """Resolve Depends parameters in a function signature.

    Supports both:
    - Annotated[T, Depends(...)] (preferred)
    - param: T = Depends(...) (legacy, but works at runtime)

    Args:
        func: The function whose signature to inspect.
        provided: Already-provided arguments (e.g., the command/event).

    Returns:
        Dict of resolved parameter names to values.
    """
    sig = inspect.signature(func)
    resolved: dict[str, Any] = dict(provided)

    # Get type hints for Annotated support
    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}

    for name, param in sig.parameters.items():
        if name in resolved:
            continue

        # Check for Annotated[T, Depends(...)]
        depends: Depends | None = None
        if name in hints:
            depends = _get_depends_from_annotation(hints[name])

        # Fall back to default value pattern
        if depends is None and isinstance(param.default, Depends):
            depends = param.default

        if depends is not None:
            dep_func = depends.dependency
            # Recursively resolve dependencies of the dependency
            nested = await resolve_dependencies(dep_func, {})

            if asyncio.iscoroutinefunction(dep_func):
                result = await dep_func(**nested)
            else:
                # Run sync dependencies in threadpool to avoid blocking
                result = await anyio.to_thread.run_sync(  # type: ignore[unresolved-attribute]
                    partial(dep_func, **nested)
                )

            resolved[name] = result

    return resolved


@overload
async def call_with_deps(
    func: Callable[P, Awaitable[R]],
    provided: dict[str, Any],
) -> R: ...


@overload
async def call_with_deps(
    func: Callable[P, R],
    provided: dict[str, Any],
) -> R: ...


async def call_with_deps(
    func: Callable[P, R] | Callable[P, Awaitable[R]],
    provided: dict[str, Any],
) -> R:
    """Call a function, resolving any Depends parameters.

    Sync functions are dispatched to a threadpool to avoid blocking
    the event loop, similar to FastAPI's behavior.

    Args:
        func: The function to call (sync or async).
        provided: Already-provided arguments.

    Returns:
        The result of calling the function.
    """
    resolved = await resolve_dependencies(func, provided)

    if asyncio.iscoroutinefunction(func):
        async_func = cast(Callable[P, Awaitable[R]], func)
        return await async_func(**resolved)

    # Run sync functions in threadpool to avoid blocking event loop
    sync_func = cast(Callable[P, R], func)
    return await anyio.to_thread.run_sync(  # type: ignore[unresolved-attribute]
        partial(sync_func, **resolved)
    )
