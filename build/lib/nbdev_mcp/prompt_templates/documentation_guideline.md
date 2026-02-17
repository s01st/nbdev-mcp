# nbdev Documentation Guide

## Top Markdown Cell Structure

The **first markdown cell** sets up the notebook page. Use YAML frontmatter for metadata:

```markdown
---
title: Module Name
description: Brief description of what this module does
output-file: custom_name.html
---

# Module Name
> Detailed description and overview

This module provides functionality for...
```

**Frontmatter options:**
- `title`: Page title (appears in docs navigation)
- `description`: Meta description for SEO and previews
- `output-file`: Custom HTML filename (defaults to notebook name)
- `skip_showdoc`: Set to `true` to skip automatic show_doc
- `skip_exec`: Set to `true` to skip execution

**Without frontmatter**, just use a markdown cell:
```markdown
# Module Name
> Brief description

More details here...
```

## Notebook Headings Structure

Use markdown headings to organize notebooks (they become doc sections):

```markdown
# Main Module Title (H1 - use once at top)

## Section Name (H2 - major sections)
Description of this section...

### Subsection (H3 - functions/classes)
Details about specific items...

#### Notes (H4 - detailed notes)
Additional information...
```

**Best practices:**
- **H1 (#)**: Module title (once per notebook)
- **H2 (##)**: Major sections (Imports, Core Functions, Utilities, Tests)
- **H3 (###)**: Individual functions or classes
- **H4 (####)**: Detailed notes or subsections

**Example structure:**
```markdown
# Data Processing Module

## Setup
(imports and configuration)

## Core Functions
### process_data
### validate_input

## Utilities
### helper_function

## Examples
### Basic Usage
### Advanced Usage

## Tests
```

## The `@patch` Decorator

Use `@patch` to add methods to existing classes (monkey patching):

```python
#| export
from fastcore.basics import patch

@patch
def new_method(self:MyClass, x):
    "Add a new method to MyClass"
    return self.value + x
```

**When to use `@patch`:**
- ✅ Adding methods to classes defined elsewhere (even external libraries)
- ✅ Splitting class methods across multiple notebook cells
- ✅ Organizing related functionality together
- ✅ Extending third-party classes without subclassing

**Example - extending pandas DataFrame:**
```python
#| export
from fastcore.basics import patch
import pandas as pd

@patch
def my_summary(self:pd.DataFrame):
    "Custom summary method for DataFrame"
    return {
        'rows': len(self),
        'columns': len(self.columns),
        'missing': self.isna().sum().sum()
    }
```

**Multiple patches for one class:**
```python
#| export
class DataProcessor:
    def _init__(self, data):
        self.data = data

@patch
def process(self:DataProcessor):
    "Process the data"
    return self.data * 2

@patch
def validate(self:DataProcessor):
    "Validate the data"
    return self.data > 0
```

## NumPy-Style Docstrings

nbdev uses **NumPy docstring format** (https://numpydoc.readthedocs.io/en/latest/format.html)

### Standard Sections (in order):

```python
#| export
def function_name(param1, param2, param3=None):
    '''
    Short one-line description.

    Extended description paragraph. Can be multiple paragraphs.
    Explain what the function does in detail.

    Parameters
    ----------
    param1 : type
        Description of param1
    param2 : int or str
        Description of param2. Can specify multiple types.
    param3 : float, optional
        Description of param3 (default is None)

    Returns
    -------
    type or tuple
        Description of return value
        Can be multiple lines

    Raises
    ------
    ValueError
        When invalid input is provided
    TypeError
        When wrong type is passed

    See Also
    --------
    other_function : Related function
    AnotherClass : Related class

    Notes
    -----
    Additional notes about implementation, algorithms, or edge cases.
    Math can be included:

    .. math:: X(e^{j\omega } ) = x(n)e^{ - j\omega n}

    References
    ----------
    .. [1] Author, "Title", Journal, Year.

    Examples
    --------
    >>> function_name(1, 2)
    3
    >>> function_name(1, 2, param3=0.5)
    3.5
    '''
    pass
```

### Class Docstrings

```python
#| export
class MyClass:
    '''
    One-line summary.

    Extended description of the class.

    Parameters
    ----------
    param1 : type
        Description
    param2 : type, optional
        Description (default is value)

    Attributes
    ----------
    attr1 : type
        Description of attribute
    attr2 : type
        Description of attribute

    Methods
    -------
    method1(arg1, arg2)
        Brief description
    method2()
        Brief description

    See Also
    --------
    RelatedClass : Description

    Examples
    --------
    >>> obj = MyClass(param1)
    >>> obj.method1(x, y)
    result
    '''

    def _init__(self, param1, param2=None):
        self.attr1 = param1
        self.attr2 = param2

    def method1(self, arg1, arg2):
        '''
        Method description.

        Parameters
        ----------
        arg1 : type
            Description
        arg2 : type
            Description

        Returns
        -------
        type
            Description
        '''
        pass
```

### Module Docstrings (Top of Notebook)

Put module-level docstring in first code cell after default_exp:

```python
#| default_exp module_name
'''
Module Name
===========

Brief description of the module.

This module provides...

Main Features
-------------
- Feature 1
- Feature 2

See Also
--------
other_module : Related module
'''
```

### Property Docstrings

```python
#| export
class MyClass:
    @property
    def value(self):
        '''
        Description of property.

        Returns
        -------
        type
            Description of return value
        '''
        return self._value
```

### Docstring Sections Reference

**Always include:**
- Short description (one line)
- `Parameters` (if function takes arguments)
- `Returns` (if function returns value)

**Include when relevant:**
- Extended description
- `Raises` (exceptions that can be raised)
- `Examples` (executable examples with >>>)
- `See Also` (related functions/classes)

**Include occasionally:**
- `Notes` (implementation details, algorithms)
- `References` (citations, papers)
- `Warnings` (important caveats)
- `Attributes` (for classes)
- `Methods` (brief method list in class docstring)

**Type specifications:**
```
param : int
param : str or None
param : list of int
param : dict of {str : int}
param : array-like, shape (n, m)
param : callable
param : MyClass instance
```

## Quarto Callouts in Notebooks

Use callouts for highlighting important information:

```markdown
::: {.callout-note}
This is a note
:::

::: {.callout-warning}
This is a warning
:::

::: {.callout-important}
This is important
:::

::: {.callout-tip}
This is a tip
:::

::: {.callout-caution}
This is a caution
:::
```

## Documentation Best Practices

1. **Start with top markdown cell** - Set title and description
2. **Use headings** - Organize with ##, ###, ####
3. **Write docstrings first** - Before implementation
4. **Include examples** - Show usage in docstrings
5. **Use `show_doc`** - Display formatted documentation
6. **Add tests after examples** - Verify examples work
7. **Use `@patch`** - When extending classes
8. **Keep notebooks focused** - One module per notebook

## Complete Example

```python
# First cell - Markdown
---
title: Data Processing
description: Tools for processing and validating data
---

# Data Processing
> Utilities for data transformation and validation

# Second cell - Code
#| default_exp data_processing

# Third cell - Code
#| export
from fastcore.basics import patch
import pandas as pd

# Fourth cell - Code
#| export
def process_data(df, scale=1.0):
    '''
    Process and scale data.

    Parameters
    ----------
    df : pd.DataFrame
        Input data
    scale : float, optional
        Scaling factor (default is 1.0)

    Returns
    -------
    pd.DataFrame
        Processed data

    Examples
    --------
    >>> df = pd.DataFrame({'a': [1, 2, 3]})
    >>> process_data(df, scale=2.0)
    '''
    return df * scale

# Fifth cell - Code (example)
df = pd.DataFrame({'a': [1, 2, 3]})
result = process_data(df, scale=2.0)
assert result['a'].tolist() == [2, 4, 6]
```
