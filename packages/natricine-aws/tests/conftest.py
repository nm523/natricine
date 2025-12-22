"""Test fixtures for natricine-aws."""

import aioboto3
import pytest

try:
    import docker
    from testcontainers.localstack import LocalStackContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    docker = None  # type: ignore[assignment]
    TESTCONTAINERS_AVAILABLE = False
    LocalStackContainer = None  # type: ignore[misc, assignment]


def docker_available() -> bool:
    """Check if Docker is available."""
    if not TESTCONTAINERS_AVAILABLE or docker is None:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def localstack():
    """Start localstack container for the test session."""
    if not docker_available():
        pytest.skip("Docker not available")

    with LocalStackContainer(image="localstack/localstack:latest") as container:
        container.with_services("sqs", "sns")
        yield container


@pytest.fixture
def endpoint_url(localstack: LocalStackContainer) -> str:
    """Get the localstack endpoint URL."""
    return localstack.get_url()


@pytest.fixture
def session() -> aioboto3.Session:
    """Create an aioboto3 session."""
    return aioboto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
