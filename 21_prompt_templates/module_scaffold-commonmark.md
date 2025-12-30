

# {module}

> Auto-generated scaffold for `{lib}.{module}`

## Imports

``` python
#| hide
from nbdev.showdoc import *
%load_ext autoreload
%autoreload 2
```

``` python
#| default_exp {module}
```

## {module.capitalize()} API

``` python
#| export
def my_function(x: int) -> int:
    "Example function"
    return x + 1
```

## Examples

``` python
y = my_function(1)
assert y == 2
```

## Next

``` python
#| export
```

## Export

``` python
#| hide
import nbdev; nbdev.nbdev_export()
```
