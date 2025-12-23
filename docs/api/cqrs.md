# natricine-cqrs

CQRS pattern with command and event buses.

## Installation

```bash
pip install natricine-cqrs
```

## CommandBus

Dispatches commands to handlers. Each command type has exactly one handler.

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

command_bus = CommandBus(
    publisher=publisher,
    subscriber=subscriber,
    marshaler=PydanticMarshaler(),
)

@command_bus.handler
async def handle_create_user(cmd: CreateUser) -> None:
    await db.create_user(cmd.name, cmd.email)

# Dispatch command
await command_bus.send(CreateUser(name="Alice", email="alice@example.com"))

# Process commands (worker)
await command_bus.run()
```

### Constructor

```python
CommandBus(
    publisher: Publisher,
    subscriber: Subscriber,
    marshaler: Marshaler,
    topic: str = "commands",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `publisher` | `Publisher` | required | For sending commands |
| `subscriber` | `Subscriber` | required | For receiving commands |
| `marshaler` | `Marshaler` | required | Serializes/deserializes commands |
| `topic` | `str` | `"commands"` | Topic for command messages |

### Methods

| Method | Description |
|--------|-------------|
| `handler` | Decorator to register command handler |
| `await send(cmd)` | Send command for async processing |
| `await run()` | Start processing commands |
| `await close()` | Stop processing |

## EventBus

Publishes events to multiple handlers. Each event type can have many handlers.

```python
from natricine.cqrs import EventBus, PydanticMarshaler

event_bus = EventBus(
    publisher=publisher,
    subscriber=subscriber,
    marshaler=PydanticMarshaler(),
)

@event_bus.handler
async def send_welcome_email(event: UserCreated) -> None:
    await email.send_welcome(event.email)

@event_bus.handler
async def track_signup(event: UserCreated) -> None:
    await analytics.track("signup", event.user_id)

# Publish event
await event_bus.publish(UserCreated(user_id="123", email="alice@example.com"))

# Process events (worker)
await event_bus.run()
```

### Constructor

```python
EventBus(
    publisher: Publisher,
    subscriber: Subscriber,
    marshaler: Marshaler,
    topic: str = "events",
)
```

### Methods

| Method | Description |
|--------|-------------|
| `handler` | Decorator to register event handler |
| `await publish(event)` | Publish event |
| `await run()` | Start processing events |
| `await close()` | Stop processing |

## CommandRouter / EventRouter

Local routers without pub/sub (in-process only).

```python
from natricine.cqrs import CommandRouter, EventRouter

command_router = CommandRouter(marshaler=PydanticMarshaler())
event_router = EventRouter(marshaler=PydanticMarshaler())

@command_router.handler
async def handle_cmd(cmd: MyCommand) -> None:
    pass

# Execute synchronously (no network)
await command_router.send(MyCommand(...))
```

## Marshaler

Protocol for serializing/deserializing messages.

```python
from natricine.cqrs import Marshaler

class Marshaler(Protocol):
    def marshal(self, obj: object) -> Message: ...
    def unmarshal(self, msg: Message, type_hint: type[T]) -> T: ...
```

## PydanticMarshaler

Default marshaler using Pydantic for JSON serialization.

```python
from natricine.cqrs import PydanticMarshaler

marshaler = PydanticMarshaler()

# Serialize
msg = marshaler.marshal(MyCommand(name="test"))
# msg.payload = b'{"name": "test"}'
# msg.metadata["_type"] = "MyCommand"

# Deserialize
cmd = marshaler.unmarshal(msg, MyCommand)
```

## Depends

Dependency injection for handlers.

```python
from typing import Annotated
from natricine.cqrs import Depends

def get_db() -> Database:
    return Database()

@command_bus.handler
async def handle_create(
    cmd: CreateUser,
    db: Annotated[Database, Depends(get_db)],
) -> None:
    await db.create_user(cmd.name)
```

### Factory Functions

Dependencies can be sync or async:

```python
def get_sync_dep() -> SyncDep:
    return SyncDep()

async def get_async_dep() -> AsyncDep:
    return await AsyncDep.create()
```

### Nested Dependencies

Dependencies can depend on other dependencies:

```python
def get_config() -> Config:
    return Config()

def get_db(config: Annotated[Config, Depends(get_config)]) -> Database:
    return Database(config.db_url)

@command_bus.handler
async def handle(
    cmd: MyCommand,
    db: Annotated[Database, Depends(get_db)],
) -> None:
    pass
```
