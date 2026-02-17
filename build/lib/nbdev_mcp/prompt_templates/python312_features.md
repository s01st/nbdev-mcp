# Python 3.12+ Features

Modern Python features for cleaner, more expressive code.

## Type Parameter Syntax (Generics)

```python
# OLD: verbose generic syntax
from typing import TypeVar, Generic

T = TypeVar('T')
class Container(Generic[T]):
    def __init__(self, item: T) -> None:
        self.item = item

# NEW: inline type parameters
class Container[T]:
    def __init__(self, item: T) -> None:
        self.item = item

# Functions too
def first[T](items: list[T]) -> T:
    return items[0]

# Multiple type params
def zip_map[T, U, V](xs: list[T], ys: list[U], fn: Callable[[T, U], V]) -> list[V]:
    return [fn(x, y) for x, y in zip(xs, ys)]
```

## Type Aliases with `type`

```python
# OLD: confusing assignment
Vector = list[float]  # is this a type or a value?

# NEW: explicit type alias
type Vector = list[float]
type Matrix = list[Vector]
type ArrayLike = np.ndarray | torch.Tensor | list

# Generic type aliases
type Pair[T] = tuple[T, T]
type Callback[T] = Callable[[T], None]
```

## `match/case` Patterns

```python
# Basic dispatch
match get_type(X):
    case 'torch': ...
    case 'numpy': ...

# Structural matching - destructure objects
match event:
    case {'type': 'click', 'x': x, 'y': y}:
        handle_click(x, y)
    case {'type': 'key', 'key': k}:
        handle_key(k)

# Class patterns
match shape:
    case Circle(radius=r):
        return 3.14 * r ** 2
    case Rectangle(width=w, height=h):
        return w * h

# Guard clauses
match value:
    case int(n) if n > 0:
        return "positive"
    case int(n) if n < 0:
        return "negative"
    case _:
        return "zero or non-int"

# OR patterns
match metric:
    case 'euclidean' | 'l2' | 'euc':
        return euclidean_distance(X)
    case 'cosine' | 'cos':
        return cosine_distance(X)
```

## `@override` Decorator

```python
from typing import override

class BaseModel:
    def forward(self, x): ...
    def compute_loss(self, pred, target): ...

class MyModel(BaseModel):
    @override  # Catches typos - errors if parent doesn't have this method
    def forward(self, x):
        return self.layers(x)

    @override
    def compute_los(self, pred, target):  # TYPO! @override catches this
        ...
```

## `Self` Type

```python
from typing import Self

class Builder:
    def set_name(self, name: str) -> Self:
        self.name = name
        return self  # Returns same type, even in subclasses

    def set_value(self, value: int) -> Self:
        self.value = value
        return self

# Chaining works with proper types
builder = Builder().set_name("foo").set_value(42)
```

## Typed `**kwargs` with `Unpack`

```python
from typing import Unpack, TypedDict

class PlotKwargs(TypedDict, total=False):
    figsize: tuple[int, int]
    dpi: int
    title: str

def plot(data, **kwargs: Unpack[PlotKwargs]) -> None:
    # kwargs is now typed - IDE knows valid keys
    figsize = kwargs.get('figsize', (10, 6))
    ...

# Type checker catches invalid kwargs
plot(data, figsize=(10, 6), titel="oops")  # Error: 'titel' not in PlotKwargs
```

## StrEnum (3.11+)

```python
from enum import StrEnum, auto

class Metric(StrEnum):
    EUCLIDEAN = auto()     # value is 'euclidean'
    COSINE = auto()        # value is 'cosine'
    MANHATTAN = auto()     # value is 'manhattan'

# Use directly as string
metric = Metric.EUCLIDEAN
print(f"Using {metric}")  # "Using euclidean"

# Match works naturally
match metric:
    case Metric.EUCLIDEAN: ...
    case Metric.COSINE: ...
```

## F-string Improvements (3.12)

```python
# Nested quotes - no escaping needed
print(f"He said {"hello"}")  # Works in 3.12+

# Multi-line expressions
result = f"""
Summary:
{
    "\n".join(
        f"  - {key}: {value}"
        for key, value in stats.items()
    )
}
"""

# Reuse quotes
f"{'nested "quotes" work'}"  # 3.12+
```

## Exception Groups (3.11+)

```python
# Raise multiple exceptions
def validate_all(data):
    errors = []
    if not data.get('name'):
        errors.append(ValueError("missing name"))
    if not data.get('email'):
        errors.append(ValueError("missing email"))
    if errors:
        raise ExceptionGroup("validation failed", errors)

# Catch specific exceptions from group
try:
    validate_all(data)
except* ValueError as eg:
    for e in eg.exceptions:
        print(f"Validation error: {e}")
except* TypeError as eg:
    ...
```

## `slots=True` in Dataclasses

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float
    # Faster attribute access, less memory, immutable
```

## When to Use These

- **Type parameters**: Any generic class or function
- **`type` aliases**: Complex type definitions
- **`match/case`**: Multi-way dispatch, parsing, state machines
- **`@override`**: All method overrides (catches typos)
- **`Self`**: Builder pattern, fluent interfaces
- **`Unpack`**: Functions with many optional kwargs
- **`StrEnum`**: String constants that need enum benefits
- **`slots=True`**: Data classes used in hot paths
