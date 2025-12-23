# natricine TODO

## In Progress

### natricine-redisstream
- [x] Update tests to use testcontainers for Redis
- [x] Fix PLR2004 magic number lint errors in tests
- [x] Add package to root pyproject.toml dependencies

## Design Issues

### Sync Handler Support
- [x] Support sync handlers like FastAPI does (dispatch to threadpool)
- [x] `call_with_deps` now uses `anyio.to_thread.run_sync()` for sync handlers/dependencies
- [x] CommandBus and EventBus support both sync and async handlers via overloads

### Command Handler Registration Sequencing
- [x] Added `CommandRouter` and `EventRouter` for deferred handler registration
- [x] `bus.include_router(router, prefix="...")` to include handlers
- [x] Per-inclusion topic prefix support
- [ ] Router-level middleware (deferred - needs design thought)

### Depends Type Annotation
- [x] Fixed - now using `Annotated[T, Depends(...)]` pattern like FastAPI
- [x] Depends is now generic `Depends[T_co]` for proper type inference
- [x] `call_with_deps` uses ParamSpec with overloads for proper typing
- [x] Fix `examples/chat` to use the new pattern

## Completed

### Namespace Packaging
- [x] Migrated to `natricine.cqrs`, `natricine.pubsub`, `natricine.router`, `natricine.redisstream`
- [x] Using PEP 420 implicit namespace packages with uv_build

### Conformance Testing
- [x] Created `natricine-conformance` package with categorized test suite
- [x] Categories: Core, FanOut, Acknowledgment, Lifecycle, Robustness
- [x] Runners for InMemoryPubSub and RedisStream
- [x] `make conformance` command for easy testing

### Middleware
- [x] Enhanced `retry` middleware with jitter, exception filtering, `PermanentError`, `on_retry` callback
- [x] Added `dead_letter_queue` middleware for failed message handling

### Chat Example
- [x] The chat example should be consolidated into a package structure so it is more coherent
- [x] The FastAPI handlers should inject the event bus / command bus using FastAPI's depends
- [ ] The chat example should import / install the `natricine` meta-package instead of specific lower level namespace packages

### natricine-aws
- [x] SQS Publisher/Subscriber with aioboto3
- [x] SNS Publisher/Subscriber
- [x] Conformance tests with localstack/testcontainers
- [ ] SNS+SQS fan-out pattern (SNS topic → SQS queue subscription)

### natricine-otel
- [x] TracingMiddleware for Router (CONSUMER spans)
- [x] TracingPublisher decorator (PRODUCER spans)
- [x] W3C trace context propagation via message metadata
- [x] Metrics middleware (message counts, latencies)

## Documentation

- [ ] Add README.md to each package directory
- [ ] Track project/package order in main README

## Future Work

### New Packages
- [ ] `natricine-sql` - SQL-based pub/sub (like watermill-sql)
  - Decision needed: Can SQLite be in the same package or does it need `natricine-sqlite` separate?
  - Consider: async drivers (asyncpg, aiosqlite), connection pooling, polling strategies
