"""Dependency injection inspired by FastAPI's Depends."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar, get_args, get_origin, get_type_hints

T = TypeVar("T")


@dataclass(frozen=True)
class Depends:
    """Marker for dependency injection in handler signatures.

    Usage with Annotated (preferred):
        async def get_database() -> Database:
            return Database()

        @command_bus.handler
        async def handle_cmd(
            cmd: MyCommand,
            db: Annotated[Database, Depends(get_database)],
        ) -> None:
            await db.save(cmd)
    """

    dependency: Callable[..., Any]


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
