# natricine-conformance

Conformance test suite for pub/sub implementations.

## Installation

```bash
pip install natricine-conformance
```

## Usage

### 1. Create a fixture

```python
# conftest.py
import pytest
from myimpl import MyPubSub

@pytest.fixture
async def pubsub():
    async with MyPubSub() as ps:
        yield ps
```

### 2. Inherit test classes

```python
# test_mypubsub_conformance.py
from natricine.conformance import PubSubConformance

class TestMyPubSubCore(PubSubConformance.Core):
    pass

class TestMyPubSubFanOut(PubSubConformance.FanOut):
    pass

class TestMyPubSubAcknowledgment(PubSubConformance.Acknowledgment):
    pass

class TestMyPubSubLifecycle(PubSubConformance.Lifecycle):
    pass

class TestMyPubSubRobustness(PubSubConformance.Robustness):
    pass
```

### 3. Run tests

```bash
pytest test_mypubsub_conformance.py -v
```

## Test Categories

| Category | Tests |
|----------|-------|
| **Core** | Publish, subscribe, payload/metadata/uuid preservation |
| **FanOut** | Multiple subscribers receive all messages |
| **Acknowledgment** | ack(), nack(), double-ack raises |
| **Lifecycle** | Context manager, async iterator protocol |
| **Robustness** | Concurrent publishers, high message volume |

## Skipping Tests

Some implementations have different semantics:

```python
class TestSQSFanOut(PubSubConformance.FanOut):
    # SQS has competing consumers, not fan-out
    @pytest.mark.skip(reason="SQS distributes, not broadcasts")
    async def test_multiple_subscribers_receive_message(self, pubsub):
        pass
```

## Adapter Pattern

If your implementation doesn't match the combined Publisher+Subscriber interface:

```python
class MyPubSubAdapter:
    def __init__(self, publisher, subscriber):
        self._pub = publisher
        self._sub = subscriber

    async def publish(self, topic, *messages):
        await self._pub.publish(topic, *messages)

    def subscribe(self, topic):
        return self._sub.subscribe(topic)

    async def close(self):
        await self._pub.close()
        await self._sub.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

@pytest.fixture
async def pubsub():
    async with MyPubSubAdapter(MyPublisher(), MySubscriber()) as ps:
        yield ps
```
