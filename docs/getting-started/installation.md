# Installation

## Core Package

Install the meta-package which includes pubsub, router, and CQRS:

```bash
pip install natricine
```

Or with uv:

```bash
uv add natricine
```

## Backends

Install backends separately based on your needs:

=== "Redis Streams"

    ```bash
    pip install natricine-redisstream
    ```

=== "AWS SQS/SNS"

    ```bash
    pip install natricine-aws
    ```

=== "SQL (Postgres/SQLite)"

    ```bash
    # PostgreSQL
    pip install natricine-sql[postgres]

    # SQLite (dev/testing)
    pip install natricine-sql[sqlite]
    ```

## Observability

For OpenTelemetry tracing and metrics:

```bash
pip install natricine-otel
```

## With Pydantic

For CQRS with Pydantic model marshaling:

```bash
pip install natricine[pydantic]
```

## Development

For development with all backends:

```bash
pip install natricine[pydantic]
pip install natricine-redisstream
pip install natricine-aws
pip install natricine-sql[postgres,sqlite]
pip install natricine-otel
```

## Requirements

- Python 3.11+
- anyio 4.0+
