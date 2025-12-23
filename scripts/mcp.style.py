#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Style Guide MCP server - teaches agents the core coding principles:
- Mathematica-style single-responsibility functions
- Multi-dispatch pattern (3-level hierarchy)
- Composability over monoliths
- REUSE as the #1 priority

Role: Provides resources, tools, and prompts to guide agents toward
writing clean, reusable, composable code instead of 200-line monoliths.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import textwrap
from typing import Any

from mcp.server.fastmcp import FastMCP
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

__version__ = "0.1.0"

# ----------------------------- logging (stderr) ------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("mcp.style_guide")

# ----------------------------- helpers --------------------------------------
def _console(width: int = 100) -> Console:
    """Create a Rich Console for capturing formatted text (never prints to stdout)."""
    return Console(file=io.StringIO(), force_terminal=True, width=width, record=True)


def _export_console(c: Console) -> str:
    """Export the recorded console output as text (with rich formatting)."""
    return c.export_text(clear=False)


def _render_panel(title: str, body: str, meta: dict[str, Any] | None = None) -> str:
    """Render a result panel with optional meta table."""
    c = _console()
    c.print(Panel.fit(Text(title, style="bold"), title="Style Guide MCP"))
    c.print(Markdown(body))
    if meta:
        t = Table(title="Context", expand=False)
        t.add_column("Key")
        t.add_column("Value")
        for k, v in meta.items():
            t.add_row(str(k), str(v))
        c.print(t)
    return _export_console(c)


# ----------------------------- reference text -------------------------------
PHILOSOPHY = textwrap.dedent(
    """
    **Mathematica-style**: Every function does ONE thing. Name says what it does. No side effects.

    **REUSE EVERYTHING**: Before writing code, check if it already exists. If you're writing 200 lines, you're probably reimplementing something.

    **Compose, don't monolith**: Build complex behavior from small, reusable pieces.
    """
).strip()

REUSE_MANDATE = textwrap.dedent(
    """
    ## Before Writing ANY Code

    1. **Search the codebase** - Does this function already exist?
    2. **Search dependencies** - Does sklearn/torch/scipy already do this?
    3. **Extract, don't duplicate** - If similar logic exists, refactor it into a shared helper

    ## The 5-Line Rule

    If you see 5+ lines of logic that could be reused:
    - **Extract it** into a standalone function
    - **Expose configuration** via parameters
    - **Call it** from both places
    """
).strip()

FIVE_LINE_EXAMPLE = textwrap.dedent(
    """
    ```python
    # BAD: Logic buried and duplicated, not configurable
    class ModelA:
        def forward(self, x):
            mean = x.mean(dim=0)
            std = x.std(dim=0)
            x = (x - mean) / (std + 1e-8)
            return self.layers(x)

    class ModelB:
        def forward(self, x):
            mean = x.mean(dim=0)
            std = x.std(dim=0)
            x = (x - mean) / (std + 1e-8)  # what if I need different eps?
            return self.other_layers(x)

    # GOOD: Extract, expose config, reuse
    def normalize(x, *, eps=1e-8, dim=0):
        return (x - x.mean(dim=dim)) / (x.std(dim=dim) + eps)

    class ModelA:
        def forward(self, x):
            return self.layers(normalize(x))

    class ModelB:
        def forward(self, x):
            return self.other_layers(normalize(x, eps=1e-6, dim=1))
    ```
    """
).strip()

MULTI_DISPATCH_HIERARCHY = textwrap.dedent(
    r"""
    ```
    distance(X, metric='euclidean')          <- Super function (dispatches on metric)
        |
        +-> euclidean_distance(X)            <- Metric-specific (dispatches on type)
        |       +-> euclidean_distance_numpy(X)
        |       +-> euclidean_distance_torch(X)
        |       +-> euclidean_distance_sparse(X)
        |
        +-> cosine_distance(X)
        |       +-> cosine_distance_numpy(X)
        |       +-> cosine_distance_torch(X)
        |       +-> cosine_distance_sparse(X)
        |
        +-> manhattan_distance(X)
                +-> ...
    ```
    """
).strip()

DISPATCH_LEVEL_1 = textwrap.dedent(
    """
    ## Level 1: Type-Specific Implementations

    Simple, focused. One type, one job. No dispatch logic.

    ```python
    def euclidean_distance_numpy(X, Y=None, *, squared=False):
        \"\"\"NumPy dense arrays only.\"\"\"
        return sklearn_euclidean(X, Y, squared=squared)

    def euclidean_distance_torch(X, Y=None, *, squared=False):
        \"\"\"PyTorch dense tensors only.\"\"\"
        D = torch.cdist(X, Y if Y is not None else X)
        return D.pow(2) if squared else D

    def euclidean_distance_sparse(X, Y=None, *, squared=False):
        \"\"\"Scipy sparse matrices only.\"\"\"
        return sparse_euclidean(X, Y, squared=squared)
    ```
    """
).strip()

DISPATCH_LEVEL_2 = textwrap.dedent(
    """
    ## Level 2: Metric-Specific Dispatcher

    Dispatches on input type. This is the public API for a specific metric.

    ```python
    def euclidean_distance(X, Y=None, *, squared=False):
        \"\"\"Euclidean distance - works with any array type.\"\"\"
        match get_type(X):
            case 'torch':  return euclidean_distance_torch(X, Y, squared=squared)
            case 'sparse': return euclidean_distance_sparse(X, Y, squared=squared)
            case _:        return euclidean_distance_numpy(X, Y, squared=squared)
    ```
    """
).strip()

DISPATCH_LEVEL_3 = textwrap.dedent(
    """
    ## Level 3: Super Function

    Dispatches on metric parameter. Ultimate convenience API.

    ```python
    def distance(X, Y=None, *, metric='euclidean', **kwargs):
        \"\"\"Pairwise distance - any metric, any type.\"\"\"
        match metric:
            case 'euclidean' | 'l2':   return euclidean_distance(X, Y, **kwargs)
            case 'cosine':             return cosine_distance(X, Y, **kwargs)
            case 'manhattan' | 'l1':   return manhattan_distance(X, Y, **kwargs)
            case _:                    raise ValueError(f"Unknown metric: {metric}")
    ```
    """
).strip()

DISPATCH_WHY = textwrap.dedent(
    """
    ## Why This Pattern

    - **User picks their level**: `distance(X, metric='cosine')` or `cosine_distance(X)` or `cosine_distance_torch(X)`
    - **Type implementations are simple**: No type-checking boilerplate, just the algorithm
    - **Easy to extend**: Add a metric? Add one function + one case. Add a type? Add implementations + cases.
    - **Each level is testable**: Test types independently, test metrics independently
    """
).strip()

COMPOSABILITY = textwrap.dedent(
    """
    ## Build Up, Don't Out

    ```python
    # BAD: One giant function
    def phate_embedding(X, k=15, t=5, n_components=2, metric='euclidean', ...):
        # 200 lines doing everything
        ...

    # GOOD: Compose from primitives
    def phate_embedding(X, *, k=15, t=5, n_components=2, metric='euclidean'):
        D = distance(X, metric=metric)                # reused
        A = knn_affinity(D, k=k)                      # reused
        P = normalize(A, mode='row')                  # reused
        P_t = matrix_power(P, t)                      # reused
        return embed(P_t, n_components=n_components)  # reused
    ```

    ## Each Primitive is Useful Alone

    ```python
    # These all work independently - users can mix and match
    D = distance(X, metric='cosine')    # just distances
    A = knn_affinity(D, k=10)           # just affinity
    P = normalize(A, mode='symmetric')  # just normalization
    coords = embed(P, n_components=3)   # just embedding
    ```
    """
).strip()

EXAMPLE_DIFFUSION = textwrap.dedent(
    """
    ## Diffusion UNet (Reuse HuggingFace)

    ```python
    # BAD: Implementing UNet from scratch (500+ lines)
    class MyUNet(nn.Module):
        def __init__(self):
            # ... 100 lines of conv blocks, attention, etc.

    # GOOD: Reuse diffusers, compose what you need
    from diffusers import UNet2DModel, UNet2DConditionModel
    from diffusers.models.attention import Attention

    class DiffusionModel(nn.Module):
        \"\"\"Thin wrapper - reuse everything, customize only what's needed.\"\"\"

        def __init__(self, *, in_channels=3, out_channels=3, layers_per_block=2):
            super().__init__()
            # Reuse the entire UNet - don't reimplement
            self.unet = UNet2DModel(
                in_channels=in_channels,
                out_channels=out_channels,
                layers_per_block=layers_per_block,
                block_out_channels=(128, 256, 512, 512),
                down_block_types=("DownBlock2D",) * 4,
                up_block_types=("UpBlock2D",) * 4,
            )

        def forward(self, x, t):
            return self.unet(x, t).sample

    # Need conditioning? Don't rewrite - use the conditional variant
    class ConditionalDiffusion(nn.Module):
        def __init__(self, *, cross_attention_dim=768):
            super().__init__()
            self.unet = UNet2DConditionModel(
                cross_attention_dim=cross_attention_dim,
                # ... config
            )

        def forward(self, x, t, encoder_hidden_states):
            return self.unet(x, t, encoder_hidden_states=encoder_hidden_states).sample
    ```
    """
).strip()

EXAMPLE_TRANSFORMERS = textwrap.dedent(
    """
    ## Transformers (Reuse HuggingFace)

    ```python
    # BAD: Implementing attention from scratch
    class MyAttention(nn.Module):
        def __init__(self, dim, heads=8):
            # ... 50 lines

    # GOOD: Reuse transformers
    from transformers import AutoModel, AutoTokenizer
    from transformers.models.bert.modeling_bert import BertSelfAttention

    class TextEncoder(nn.Module):
        \"\"\"Reuse pretrained transformer, add minimal custom head.\"\"\"

        def __init__(self, model_name='bert-base-uncased', *, output_dim=256):
            super().__init__()
            self.backbone = AutoModel.from_pretrained(model_name)
            self.head = nn.Linear(self.backbone.config.hidden_size, output_dim)

        def forward(self, input_ids, attention_mask=None):
            outputs = self.backbone(input_ids, attention_mask=attention_mask)
            return self.head(outputs.last_hidden_state[:, 0])  # CLS token

    # Need just attention? Import the component
    class CrossAttentionBlock(nn.Module):
        def __init__(self, dim, context_dim, *, heads=8):
            super().__init__()
            # Reuse existing attention implementation
            from diffusers.models.attention import CrossAttention
            self.attn = CrossAttention(query_dim=dim, cross_attention_dim=context_dim, heads=heads)

        def forward(self, x, context):
            return self.attn(x, encoder_hidden_states=context)
    ```
    """
).strip()

EXAMPLE_SKLEARN_PIPELINE = textwrap.dedent(
    """
    ## sklearn Pipeline

    ```python
    # BAD: Manual preprocessing in one function
    def preprocess_and_classify(X, y):
        # impute
        X = np.where(np.isnan(X), np.nanmean(X, axis=0), X)
        # scale
        X = (X - X.mean(0)) / X.std(0)
        # pca
        pca = PCA(n_components=50)
        X = pca.fit_transform(X)
        # classify
        clf = RandomForestClassifier()
        clf.fit(X, y)
        return clf, pca  # now you have to track both...

    # GOOD: Compose with Pipeline - each step is reusable
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.ensemble import RandomForestClassifier

    def build_classifier_pipeline(*, n_components=50, n_estimators=100):
        \"\"\"Each step is a reusable, testable component.\"\"\"
        return Pipeline([
            ('impute', SimpleImputer(strategy='mean')),
            ('scale', StandardScaler()),
            ('reduce', PCA(n_components=n_components)),
            ('classify', RandomForestClassifier(n_estimators=n_estimators)),
        ])

    # Use it
    pipe = build_classifier_pipeline(n_components=30)
    pipe.fit(X_train, y_train)
    predictions = pipe.predict(X_test)

    # Swap components easily
    pipe.set_params(classify=GradientBoostingClassifier())

    # Access intermediate steps
    scaled_X = pipe[:2].transform(X_test)  # just impute + scale
    ```
    """
).strip()

EXAMPLE_LIGHTNING = textwrap.dedent(
    """
    ## PyTorch Lightning

    ```python
    # BAD: Training loop from scratch (100+ lines)
    def train(model, train_loader, val_loader, epochs, lr):
        optimizer = Adam(model.parameters(), lr=lr)
        for epoch in range(epochs):
            # ... 50 lines of training/validation logic

    # GOOD: Lightning handles the boilerplate
    import lightning as L
    from lightning.pytorch.callbacks import ModelCheckpoint, EarlyStopping
    from lightning.pytorch.loggers import TensorBoardLogger

    class Learner(L.LightningModule):
        \"\"\"Minimal: define model, loss, step logic. Lightning handles the rest.\"\"\"

        def __init__(self, model, *, lr=1e-3, loss_fn=None):
            super().__init__()
            self.save_hyperparameters(ignore=['model', 'loss_fn'])
            self.model = model
            self.loss_fn = loss_fn or nn.CrossEntropyLoss()

        def forward(self, x):
            return self.model(x)

        def _shared_step(self, batch, stage):
            x, y = batch
            logits = self(x)
            loss = self.loss_fn(logits, y)
            self.log(f'{stage}_loss', loss, prog_bar=True)
            return loss

        def training_step(self, batch, batch_idx):
            return self._shared_step(batch, 'train')

        def validation_step(self, batch, batch_idx):
            return self._shared_step(batch, 'val')

        def configure_optimizers(self):
            return torch.optim.AdamW(self.parameters(), lr=self.hparams.lr)

    # Reusable trainer factory
    def build_trainer(*, max_epochs=100, accelerator='auto', log_dir='logs'):
        return L.Trainer(
            max_epochs=max_epochs,
            accelerator=accelerator,
            callbacks=[
                ModelCheckpoint(monitor='val_loss', mode='min', save_top_k=3),
                EarlyStopping(monitor='val_loss', patience=10),
            ],
            logger=TensorBoardLogger(log_dir),
        )
    ```
    """
).strip()

EXAMPLE_FULL_PIPELINE = textwrap.dedent(
    """
    ## Full Pipeline (Compose Everything)

    ```python
    # Combine sklearn preprocessing with PyTorch model via skorch
    from skorch import NeuralNetClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    # Reuse sklearn preprocessing
    preprocessor = Pipeline([
        ('impute', SimpleImputer()),
        ('scale', StandardScaler()),
    ])

    # Wrap PyTorch in sklearn interface
    net = NeuralNetClassifier(
        MyModel,
        module__in_dim=784,
        module__hidden_dim=256,
        max_epochs=20,
        lr=1e-3,
    )

    # Full pipeline: sklearn + pytorch
    full_pipeline = Pipeline([
        ('preprocess', preprocessor),
        ('model', net),
    ])

    # Now it's just sklearn
    full_pipeline.fit(X_train, y_train)
    full_pipeline.predict(X_test)
    ```
    """
).strip()

PYTHON_312_FEATURES = textwrap.dedent(
    """
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
    # Basic dispatch (shown above)
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
    result = f\"\"\"
    Summary:
    {
        "\\n".join(
            f"  - {key}: {value}"
            for key, value in stats.items()
        )
    }
    \"\"\"

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
    """
).strip()

NAMING_CONVENTIONS = textwrap.dedent(
    """
    | Pattern | Meaning |
    |---------|---------|
    | `<operation>` | Super function / multi-dispatcher: `distance`, `kernel`, `normalize` |
    | `<operation>_<type>` | Type-specific impl: `distance_torch`, `kernel_sparse` |
    | `<metric>_<operation>` | Metric-specific: `euclidean_distance`, `gaussian_kernel` |
    | `<metric>_<operation>_<type>` | Full specific: `euclidean_distance_torch` |
    | `compute_<noun>` | Derives a thing: `compute_laplacian` |
    | `build_<noun>` | Constructs object: `build_graph`, `build_trainer` |
    | `is_<type>` | Boolean check (typeguard): `is_torch`, `is_sparse` |
    | `to_<type>` | Conversion: `to_np`, `to_pt` |
    """
).strip()

ANTI_PATTERNS = textwrap.dedent(
    """
    ## Reimplementing What Exists

    ```python
    # BAD: sklearn already does this
    def my_pairwise_distances(X, metric='euclidean'):
        n = X.shape[0]
        D = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                D[i,j] = np.linalg.norm(X[i] - X[j])
        return D

    # GOOD: Use what exists
    from sklearn.metrics import pairwise_distances
    ```

    ## God Functions

    ```python
    # BAD: Does everything, reuses nothing
    def train_and_evaluate_and_save(data, config, path):
        # 300 lines...

    # GOOD: Compose
    model = build_model(config)
    model = train(model, data)
    metrics = evaluate(model, data)
    save(model, path)
    ```

    ## Copy-Paste Programming

    If you're copying code, you're doing it wrong. Extract it.

    ## Hardcoded Config

    ```python
    # BAD: Can't configure
    def normalize(x):
        return (x - x.mean()) / (x.std() + 1e-8)

    # GOOD: Expose parameters
    def normalize(x, *, eps=1e-8, dim=None):
        return (x - x.mean(dim=dim)) / (x.std(dim=dim) + eps)
    ```

    ## Reimplementing Attention/UNet/etc.

    ```python
    # BAD: 200 lines of attention
    class MultiHeadAttention(nn.Module): ...

    # GOOD: Import it
    from torch.nn import MultiheadAttention
    from transformers.models.bert.modeling_bert import BertAttention
    from diffusers.models.attention import Attention
    ```
    """
).strip()

CHECKLIST = textwrap.dedent(
    """
    - [ ] Did I check if this function already exists in the codebase?
    - [ ] Did I check if sklearn/torch/scipy/transformers/diffusers already has this?
    - [ ] Is any logic duplicated that could be extracted?
    - [ ] Can this 50-line function be 5 composed calls instead?
    - [ ] Does each function do exactly ONE thing?
    - [ ] Are all magic numbers exposed as parameters?
    - [ ] Am I reimplementing attention/unet/transformer? (Don't.)
    """
).strip()

BRIEF = textwrap.dedent(
    """
    Style Guide - condensed contract for agents:

    **Philosophy**: Mathematica-style (one function, one job), REUSE EVERYTHING, compose don't monolith.

    **The 5-Line Rule**: If you see 5+ lines of reusable logic, extract it into a function with configurable parameters.

    **Multi-Dispatch**: 3 levels - Super function (dispatches on metric) -> Metric-specific (dispatches on type) -> Type-specific (just the algorithm).

    **Composability**: Build complex from primitives. `phate_embedding` = distance + knn_affinity + normalize + matrix_power + embed.

    **Before coding**: Search codebase, search dependencies, extract don't duplicate.

    **Anti-patterns**: God functions, copy-paste, hardcoded config, reimplementing sklearn/torch/diffusers/transformers.
    """
).strip()


# ----------------------------- resources ------------------------------------
def add_resources(mcp: FastMCP) -> None:
    """Attach style guide resources to the MCP."""

    @mcp.resource("style://guides/brief")
    def resource_brief() -> str:
        """Condensed style guide contract - start here."""
        return BRIEF

    @mcp.resource("style://philosophy")
    def resource_philosophy() -> str:
        """Core philosophy: Mathematica-style, REUSE, compose."""
        return json.dumps({"philosophy": PHILOSOPHY}, indent=2)

    @mcp.resource("style://reuse/mandate")
    def resource_reuse_mandate() -> str:
        """The reuse mandate - before writing ANY code."""
        return json.dumps({"mandate": REUSE_MANDATE, "five_line_example": FIVE_LINE_EXAMPLE}, indent=2)

    @mcp.resource("style://dispatch/hierarchy")
    def resource_dispatch_hierarchy() -> str:
        """Multi-dispatch 3-level hierarchy diagram."""
        return MULTI_DISPATCH_HIERARCHY

    @mcp.resource("style://dispatch/level-1")
    def resource_dispatch_level_1() -> str:
        """Level 1: Type-specific implementations."""
        return DISPATCH_LEVEL_1

    @mcp.resource("style://dispatch/level-2")
    def resource_dispatch_level_2() -> str:
        """Level 2: Metric-specific dispatcher."""
        return DISPATCH_LEVEL_2

    @mcp.resource("style://dispatch/level-3")
    def resource_dispatch_level_3() -> str:
        """Level 3: Super function."""
        return DISPATCH_LEVEL_3

    @mcp.resource("style://dispatch/why")
    def resource_dispatch_why() -> str:
        """Why the multi-dispatch pattern works."""
        return DISPATCH_WHY

    @mcp.resource("style://composability")
    def resource_composability() -> str:
        """Composability - build up, don't out."""
        return COMPOSABILITY

    @mcp.resource("style://examples/diffusion")
    def resource_example_diffusion() -> str:
        """Example: Diffusion UNet with HuggingFace diffusers."""
        return EXAMPLE_DIFFUSION

    @mcp.resource("style://examples/transformers")
    def resource_example_transformers() -> str:
        """Example: Transformers with HuggingFace."""
        return EXAMPLE_TRANSFORMERS

    @mcp.resource("style://examples/sklearn-pipeline")
    def resource_example_sklearn() -> str:
        """Example: sklearn Pipeline composition."""
        return EXAMPLE_SKLEARN_PIPELINE

    @mcp.resource("style://examples/lightning")
    def resource_example_lightning() -> str:
        """Example: PyTorch Lightning learner."""
        return EXAMPLE_LIGHTNING

    @mcp.resource("style://examples/full-pipeline")
    def resource_example_full_pipeline() -> str:
        """Example: Full pipeline composition (sklearn + PyTorch)."""
        return EXAMPLE_FULL_PIPELINE

    @mcp.resource("style://python312")
    def resource_python312() -> str:
        """Python 3.12+ features to use."""
        return PYTHON_312_FEATURES

    @mcp.resource("style://naming")
    def resource_naming() -> str:
        """Naming conventions for functions."""
        return NAMING_CONVENTIONS

    @mcp.resource("style://anti-patterns")
    def resource_anti_patterns() -> str:
        """Anti-patterns to avoid."""
        return ANTI_PATTERNS

    @mcp.resource("style://checklist")
    def resource_checklist() -> str:
        """Pre-commit checklist."""
        return CHECKLIST


# ----------------------------- tools ----------------------------------------
def add_tools(mcp: FastMCP) -> None:
    """Attach style guide utility tools."""

    @mcp.tool(description="Check if code violates the 5-line rule (duplicated logic).")
    def check_five_line_rule(code: str) -> dict[str, Any]:
        """Analyze code for potential 5-line rule violations."""
        lines = code.strip().split('\n')
        line_count = len(lines)

        issues = []
        if line_count > 50:
            issues.append(f"Function has {line_count} lines - consider breaking into composed calls")

        # Simple heuristic checks
        if code.count('.mean(') > 1 and code.count('.std(') > 1:
            issues.append("Multiple mean/std calls detected - extract normalize() function")

        if code.count('for ') > 2:
            issues.append("Multiple loops detected - check if numpy/torch vectorization or existing functions apply")

        if 'np.zeros' in code and 'for i in range' in code:
            issues.append("Manual loop over zeros array - likely reimplementing vectorized operation")

        result = {
            "ok": len(issues) == 0,
            "line_count": line_count,
            "issues": issues,
            "recommendation": "Consider extracting repeated logic into reusable functions with configurable parameters" if issues else "Code looks reasonable"
        }
        pretty = _render_panel("5-Line Rule Check", f"Found {len(issues)} potential issues", {"lines": line_count})
        result["pretty"] = pretty
        return result

    @mcp.tool(description="Suggest dispatch hierarchy for a given operation name.")
    def suggest_dispatch_hierarchy(operation: str, metrics: list[str] | None = None, types: list[str] | None = None) -> dict[str, Any]:
        """Generate a dispatch hierarchy template for an operation."""
        metrics = metrics or ["euclidean", "cosine"]
        types = types or ["numpy", "torch", "sparse"]

        hierarchy = [f"{operation}(X, metric='...')  <- Super function"]
        hierarchy.append("    |")

        for i, metric in enumerate(metrics):
            prefix = "+-> " if i < len(metrics) - 1 else "+-> "
            hierarchy.append(f"    {prefix}{metric}_{operation}(X)  <- Metric-specific")
            for j, typ in enumerate(types):
                sub_prefix = "    |       +-> " if i < len(metrics) - 1 else "            +-> "
                hierarchy.append(f"{sub_prefix}{metric}_{operation}_{typ}(X)")
            if i < len(metrics) - 1:
                hierarchy.append("    |")

        hierarchy_str = "\n".join(hierarchy)
        pretty = _render_panel("Dispatch Hierarchy", f"```\n{hierarchy_str}\n```")
        return {"ok": True, "hierarchy": hierarchy_str, "pretty": pretty}

    @mcp.tool(description="Generate a type-specific function template.")
    def generate_type_impl_template(operation: str, metric: str, typ: str) -> dict[str, Any]:
        """Generate a template for a type-specific implementation."""
        func_name = f"{metric}_{operation}_{typ}"
        type_desc = {"numpy": "NumPy dense arrays", "torch": "PyTorch tensors", "sparse": "Scipy sparse matrices"}.get(typ, typ)

        template = f'''def {func_name}(X, Y=None, **kwargs):
    """{type_desc} implementation of {metric} {operation}."""
    # TODO: Implement {metric} {operation} for {typ}
    # Check if sklearn/torch/scipy already has this!
    raise NotImplementedError("{func_name}")
'''
        pretty = _render_panel("Type Implementation Template", f"```python\n{template}\n```")
        return {"ok": True, "template": template, "func_name": func_name, "pretty": pretty}

    @mcp.tool(description="Check if an operation might already exist in common libraries.")
    def check_existing_implementations(operation: str) -> dict[str, Any]:
        """Suggest where an operation might already be implemented."""
        suggestions = {
            "distance": ["sklearn.metrics.pairwise_distances", "scipy.spatial.distance", "torch.cdist"],
            "normalize": ["sklearn.preprocessing.normalize", "torch.nn.functional.normalize"],
            "pca": ["sklearn.decomposition.PCA", "torch.pca_lowrank"],
            "kmeans": ["sklearn.cluster.KMeans", "faiss.Kmeans"],
            "knn": ["sklearn.neighbors.NearestNeighbors", "faiss.IndexFlatL2"],
            "attention": ["torch.nn.MultiheadAttention", "transformers BertAttention", "diffusers Attention"],
            "unet": ["diffusers.UNet2DModel", "diffusers.UNet2DConditionModel"],
            "embedding": ["torch.nn.Embedding", "transformers AutoModel"],
            "convolution": ["torch.nn.Conv2d", "torch.nn.functional.conv2d"],
            "lstm": ["torch.nn.LSTM", "torch.nn.LSTMCell"],
            "transformer": ["torch.nn.Transformer", "transformers AutoModel"],
        }

        op_lower = operation.lower()
        found = []
        for key, libs in suggestions.items():
            if key in op_lower or op_lower in key:
                found.extend(libs)

        result = {
            "ok": True,
            "operation": operation,
            "existing_implementations": found if found else ["No direct matches - search sklearn, torch, scipy, transformers, diffusers"],
            "recommendation": "ALWAYS check these libraries before implementing from scratch!"
        }
        pretty = _render_panel("Existing Implementations", f"Found {len(found)} potential matches for '{operation}'")
        result["pretty"] = pretty
        return result

    @mcp.tool(description="Get the pre-commit checklist for code review.")
    def get_checklist() -> dict[str, Any]:
        """Return the style guide pre-commit checklist."""
        items = [
            "Did I check if this function already exists in the codebase?",
            "Did I check if sklearn/torch/scipy/transformers/diffusers already has this?",
            "Is any logic duplicated that could be extracted?",
            "Can this 50-line function be 5 composed calls instead?",
            "Does each function do exactly ONE thing?",
            "Are all magic numbers exposed as parameters?",
            "Am I reimplementing attention/unet/transformer? (Don't.)",
        ]
        pretty = _render_panel("Pre-Commit Checklist", "\n".join(f"- [ ] {item}" for item in items))
        return {"ok": True, "checklist": items, "pretty": pretty}

    @mcp.tool(description="Inspect an installed package for nbdev _modidx and docstring summary.")
    def get_package_index(package: str) -> dict[str, Any]:
        """Return package doc excerpt, discovered modules, and nbdev _modidx (if present)."""
        import importlib
        import pkgutil
        import runpy
        from pathlib import Path

        try:
            pkg = importlib.import_module(package)
        except Exception as exc:  # pragma: no cover - defensive
            pretty = _render_panel("Package Index", f"Import failed: {exc}")
            return {"ok": False, "error": str(exc), "pretty": pretty}

        doc = (pkg.__doc__ or "").strip()
        doc_excerpt = doc[:400] if doc else ""

        root = Path(getattr(pkg, "__file__", "")).parent if getattr(pkg, "__file__", None) else None
        modidx_path: str | None = None
        modidx: dict[str, Any] | None = None

        if root and (root / "_modidx.py").exists():
            modidx_path = str(root / "_modidx.py")
            try:
                data = runpy.run_path(modidx_path)
                # nbdev exports dictionary as variable 'd'
                modidx = data.get("d") or data
            except Exception:
                modidx = {"error": f"Failed to load {modidx_path}"}

        modules: list[str] = []
        if root:
            modules = [m.name for m in pkgutil.iter_modules([str(root)])][:25]

        meta = {
            "package": package,
            "modidx_path": modidx_path,
            "modules_sample": modules,
            "doc_excerpt": doc_excerpt[:120] + ("..." if len(doc_excerpt) > 120 else ""),
        }
        pretty = _render_panel("Package Index", f"Package '{package}' inspection complete.", meta)
        return {"ok": True, "package": package, "doc_excerpt": doc_excerpt, "modules": modules, "modidx": modidx, "modidx_path": modidx_path, "pretty": pretty}


# ----------------------------- prompts --------------------------------------
def add_prompts(mcp: FastMCP) -> None:
    """Attach style guide prompts for agent guidance."""

    @mcp.prompt()
    def style_guide_brief() -> str:
        """Top-level style guide contract - start here."""
        return BRIEF

    @mcp.prompt()
    def philosophy_prompt() -> str:
        """Core philosophy for clean code."""
        return textwrap.dedent(
            f"""
            # Code Philosophy

            {PHILOSOPHY}

            Key principle: If you're writing 200 lines of code, STOP. You're probably reimplementing something that already exists or failing to compose from primitives.
            """
        ).strip()

    @mcp.prompt()
    def reuse_mandate_prompt() -> str:
        """The reuse mandate - before writing any code."""
        return textwrap.dedent(
            f"""
            # The Reuse Mandate

            {REUSE_MANDATE}

            {FIVE_LINE_EXAMPLE}
            """
        ).strip()

    @mcp.prompt()
    def multi_dispatch_prompt() -> str:
        """Multi-dispatch pattern guide."""
        return textwrap.dedent(
            f"""
            # Multi-Dispatch Pattern

            {MULTI_DISPATCH_HIERARCHY}

            {DISPATCH_LEVEL_1}

            {DISPATCH_LEVEL_2}

            {DISPATCH_LEVEL_3}

            {DISPATCH_WHY}
            """
        ).strip()

    @mcp.prompt()
    def composability_prompt() -> str:
        """Composability over monoliths."""
        return textwrap.dedent(
            f"""
            # Composability

            {COMPOSABILITY}
            """
        ).strip()

    @mcp.prompt()
    def examples_prompt() -> str:
        """Complex examples showing reuse patterns."""
        return textwrap.dedent(
            f"""
            # Complex Examples

            {EXAMPLE_DIFFUSION}

            {EXAMPLE_TRANSFORMERS}

            {EXAMPLE_SKLEARN_PIPELINE}

            {EXAMPLE_LIGHTNING}

            {EXAMPLE_FULL_PIPELINE}
            """
        ).strip()

    @mcp.prompt()
    def python312_prompt() -> str:
        """Python 3.12+ features to use."""
        return textwrap.dedent(
            f"""
            # Python 3.12+ Features

            Use modern Python features for cleaner code:

            {PYTHON_312_FEATURES}
            """
        ).strip()

    @mcp.prompt()
    def naming_prompt() -> str:
        """Naming conventions."""
        return textwrap.dedent(
            f"""
            # Naming Conventions

            {NAMING_CONVENTIONS}
            """
        ).strip()

    @mcp.prompt()
    def anti_patterns_prompt() -> str:
        """Anti-patterns to avoid."""
        return textwrap.dedent(
            f"""
            # Anti-Patterns to Avoid

            {ANTI_PATTERNS}
            """
        ).strip()

    @mcp.prompt()
    def code_review_prompt() -> str:
        """Code review checklist prompt."""
        return textwrap.dedent(
            f"""
            # Code Review Checklist

            Before committing or suggesting code, verify:

            {CHECKLIST}

            If any box is unchecked, revise the code before proceeding.
            """
        ).strip()

    @mcp.prompt()
    def before_coding_prompt() -> str:
        """Prompt to run before writing any code."""
        return textwrap.dedent(
            """
            # Before Writing Code

            STOP. Ask yourself:

            1. **Does this function already exist?**
               - Search the current codebase
               - Check sklearn, scipy, torch, transformers, diffusers

            2. **Am I about to write 50+ lines?**
               - Break it into composed function calls
               - Each call should be independently useful

            3. **Is there duplicated logic?**
               - Extract into a helper with configurable parameters
               - Apply the 5-line rule

            4. **Am I reimplementing attention/UNet/transformer?**
               - STOP. Import from torch.nn, transformers, or diffusers

            5. **Are magic numbers hardcoded?**
               - Expose them as keyword arguments with defaults

            Only proceed when all answers are satisfactory.
            """
        ).strip()


# ----------------------------- MCP factory ----------------------------------
def create_style_guide_mcp(name: str = "mcp.style_guide") -> FastMCP:
    """Create and configure the style guide MCP server."""
    mcp = FastMCP(name)
    add_resources(mcp)
    add_tools(mcp)
    add_prompts(mcp)
    return mcp


# ----------------------------- entrypoint -----------------------------------
def _set_http_path_if_supported(mcp: FastMCP, target_path: str) -> bool:
    """Try to set HTTP mount path if SDK supports it."""
    try:
        mcp.settings.streamable_http_path = target_path  # type: ignore[attr-defined]
        return True
    except Exception:
        try:
            mcp.settings.http_path = target_path  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Style Guide MCP server (REUSE, multi-dispatch, composability)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http"),
        default=os.environ.get("STYLE_MCP_TRANSPORT", "stdio"),
        help="Transport mode: stdio (default), streamable-http (built-in), or http (via uvicorn).",
    )
    parser.add_argument("--host", default=os.environ.get("STYLE_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("STYLE_MCP_PORT", "8000")))
    parser.add_argument("--path", default=os.environ.get("STYLE_MCP_PATH", "/mcp"))
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    mcp = create_style_guide_mcp()

    default_host, default_port, default_path = "127.0.0.1", 8000, "/mcp"
    using_defaults = (
        args.host == default_host and args.port == default_port and args.path == default_path
    )

    match args.transport:
        case "stdio":
            mcp.run(transport="stdio")
        case "streamable-http":
            if using_defaults:
                mcp.run(transport="streamable-http")
            else:
                try:
                    import uvicorn
                except ImportError:
                    log.error("uvicorn required for custom host/port HTTP transport.")
                    sys.exit(1)
                if args.path and args.path != default_path:
                    ok = _set_http_path_if_supported(mcp, args.path)
                    if not ok:
                        log.warning("Could not set custom HTTP path; using default '/mcp'.")
                app = mcp.streamable_http_app()
                uvicorn.run(app, host=args.host, port=args.port)
        case "http":
            try:
                import uvicorn
            except ImportError:
                log.error("uvicorn required for http transport.")
                sys.exit(1)
            if args.path and args.path != default_path:
                ok = _set_http_path_if_supported(mcp, args.path)
                if not ok:
                    log.warning("Could not set custom HTTP path; using default '/mcp'.")
            app = mcp.streamable_http_app()
            uvicorn.run(app, host=args.host, port=args.port)
        case _:
            raise SystemExit(f"Unsupported transport option: {args.transport!r}")


if __name__ == "__main__":
    main()
