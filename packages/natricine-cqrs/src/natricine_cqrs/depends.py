"""Dependency injection inspired by FastAPI's Depends."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Depends:
    """Marker for dependency injection in handler signatures.

    Usage:
        async def get_database() -> Database:
            return Database()

        @command_bus.handler
        async def handle_cmd(cmd: MyCommand, db: Database = Depends(get_database)):
            await db.save(cmd)
    """

    dependency: Callable[..., Any]


async def resolve_dependencies(
    func: Callable[..., Any],
    provided: dict[str, Any],
) -> dict[str, Any]:
    """Resolve Depends parameters in a function signature.

    Args:
        func: The function whose signature to inspect.
        provided: Already-provided arguments (e.g., the command/event).

    Returns:
        Dict of resolved parameter names to values.
    """
    sig = inspect.signature(func)
    resolved: dict[str, Any] = dict(provided)

    for name, param in sig.parameters.items():
        if name in resolved:
            continue

        if isinstance(param.default, Depends):
            dep_func = param.default.dependency
            # Recursively resolve dependencies of the dependency
            nested = await resolve_dependencies(dep_func, {})
            result = dep_func(**nested)

            if inspect.isawaitable(result):
                result = await result

            resolved[name] = result

    return resolved


async def call_with_deps(
    func: Callable[..., T | Awaitable[T]],
    provided: dict[str, Any],
) -> T:
    """Call a function, resolving any Depends parameters.

    Args:
        func: The function to call.
        provided: Already-provided arguments.

    Returns:
        The result of calling the function.
    """
    resolved = await resolve_dependencies(func, provided)
    result = func(**resolved)

    if inspect.isawaitable(result):
        return await result  # type: ignore[return-value]

    return result  # type: ignore[return-value]
