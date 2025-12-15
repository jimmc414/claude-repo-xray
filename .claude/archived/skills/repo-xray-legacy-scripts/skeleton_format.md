# Skeleton Output Format Reference

This document describes the output format of skeleton.py.

## Single File Output

```
# ============================================================
# FILE: path/to/module.py
# Tokens: 5000 -> 250 (95.0% reduction)
# ============================================================
"""Module docstring summary..."""

CONFIG = "value"  # L15

@dataclass
class Config:  # L18
    name: str  # L19
    timeout: int = 30  # L20

class ClassName(BaseClass):  # L25
    """Class docstring summary..."""

    def __init__(self, arg1: Type, arg2: Type = default): ...  # L28
        """Initialize the class..."""

    def method_name(self, arg: Type) -> ReturnType: ...  # L35
        """Method docstring summary..."""

    async def async_method(self, arg: Type) -> ReturnType: ...  # L42
        """Async method docstring summary..."""

def module_function(arg1: Type, *args, **kwargs) -> ReturnType: ...  # L50
    """Function docstring summary..."""
```

## Key Features

1. **Token Estimation**
   - Original tokens: full file size / 4
   - Skeleton tokens: output size / 4
   - Reduction percentage shown in header

2. **Included Elements**
   - Classes with inheritance
   - Methods with full signatures
   - Type annotations (when present)
   - Default values (abbreviated)
   - First line of docstrings
   - Pydantic/dataclass fields
   - Decorators (@dataclass, @property, @tool)
   - Global constants (UPPERCASE names)
   - Line numbers (# L{n})

3. **Excluded Elements**
   - Method bodies (replaced with `...`)
   - Full docstrings (only first line)
   - Private methods (unless `--private` flag)
   - Comments
   - Imports (use dependency_graph.py for these)

## JSON Output (--json flag)

```json
{
  "files": [
    {
      "file": "path/to/module.py",
      "original_tokens": 5000,
      "skeleton_tokens": 250,
      "reduction": "95.0%",
      "skeleton": "..."
    }
  ],
  "summary": {
    "file_count": 10,
    "total_original_tokens": 50000,
    "total_skeleton_tokens": 2500,
    "overall_reduction": "95.0%"
  }
}
```

## Usage Examples

```bash
# Single file
python skeleton.py src/core/workflow.py

# Directory with pattern
python skeleton.py src/ --pattern "**/base*.py"

# Priority-based (from config)
python skeleton.py src/ --priority critical

# Include private methods
python skeleton.py src/agents/base.py --private

# Omit line numbers
python skeleton.py src/config.py --no-line-numbers

# JSON output for programmatic use
python skeleton.py src/ --json
```
