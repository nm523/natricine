"""MkDocs macros for dynamic content."""

import tomllib
from pathlib import Path


def define_env(env):
    """Define variables and macros for MkDocs."""
    # Read version from natricine package
    pyproject_path = Path(__file__).parent.parent / "packages/natricine/pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    env.variables["natricine_version"] = data["project"]["version"]
