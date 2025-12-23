# Examples

Working examples demonstrating natricine patterns.

## Available Examples

| Example | Description |
|---------|-------------|
| [Chat Application](chat.md) | CQRS with FastAPI, commands, events, dependency injection |

## Running Examples

Each example is a standalone project in the `examples/` directory:

```bash
cd examples/<example-name>
uv sync
uv run python -m <package>.app
```

## Patterns Demonstrated

### Chat Application

- **CQRS**: Separate command and event handling
- **Dependency Injection**: Using `Depends` for injecting services
- **FastAPI Integration**: REST API dispatching commands
- **In-Memory Pub/Sub**: Simple development setup
