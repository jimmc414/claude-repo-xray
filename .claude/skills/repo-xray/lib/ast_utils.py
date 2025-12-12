"""
AST utilities for Python code analysis.

Enhanced features:
- Pydantic/dataclass field extraction (AnnAssign)
- Decorator support (@tool, @agent.register, etc.)
- Global constants (SYSTEM_PROMPT, CONFIG, etc.)
- Line numbers for navigation
- ~95% token reduction vs full source
"""

import ast
from typing import Dict, List, Optional, Tuple


def get_skeleton(
    filepath: str,
    include_private: bool = False,
    include_line_numbers: bool = True
) -> Tuple[str, int, int]:
    """
    Extract the skeleton (interface) of a Python file using AST.

    Args:
        filepath: Path to Python file
        include_private: Include _private methods (default: False)
        include_line_numbers: Include line numbers for navigation (default: True)

    Returns:
        Tuple of (skeleton_text, original_tokens, skeleton_tokens)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"# Syntax error in {filepath}: {e}", 0, 0
    except Exception as e:
        return f"# Error parsing {filepath}: {e}", 0, 0

    original_tokens = len(source) // 4
    lines = []

    # Module-level docstring
    if (doc := ast.get_docstring(tree)):
        summary = doc.strip().splitlines()[0][:100]
        lines.append(f'"""{summary}..."""')
        lines.append("")

    # Process top-level nodes
    for node in tree.body:
        # Global constants (UPPERCASE = value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    val = _get_constant_repr(node.value)
                    line_ref = f"  # L{node.lineno}" if include_line_numbers else ""
                    lines.append(f'{target.id} = {val}{line_ref}')

        # Classes
        elif isinstance(node, ast.ClassDef):
            _process_class(node, lines, 0, include_private, include_line_numbers)

        # Module-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if include_private or not node.name.startswith('_'):
                _process_function(node, lines, 0, include_line_numbers)

    skeleton = "\n".join(lines)
    skeleton_tokens = len(skeleton) // 4

    return skeleton, original_tokens, skeleton_tokens


def _get_constant_repr(node) -> str:
    """Get string representation of a constant value."""
    if isinstance(node, ast.Constant):
        val = node.value
        if isinstance(val, str):
            # Truncate long strings (like system prompts)
            val_str = val.replace('\n', '\\n')
            if len(val_str) > 50:
                return f'"{val_str[:47]}..."'
            return f'"{val_str}"'
        return repr(val)
    elif isinstance(node, ast.List):
        return "[...]"
    elif isinstance(node, ast.Dict):
        return "{...}"
    elif isinstance(node, ast.Call):
        func_name = _get_name(node.func)
        return f"{func_name}(...)"
    elif isinstance(node, ast.Name):
        return node.id
    return "..."


def _format_decorators(decorators: List, prefix: str) -> List[str]:
    """Format decorator list for output."""
    lines = []
    for dec in decorators:
        if isinstance(dec, ast.Name):
            lines.append(f"{prefix}@{dec.id}")
        elif isinstance(dec, ast.Attribute):
            name = _get_name(dec)
            lines.append(f"{prefix}@{name}")
        elif isinstance(dec, ast.Call):
            func_name = _get_name(dec.func)
            lines.append(f"{prefix}@{func_name}(...)")
    return lines


def _process_class(
    node: ast.ClassDef,
    lines: List[str],
    indent: int,
    include_private: bool,
    include_line_numbers: bool
):
    """Process a class definition with fields and decorators."""
    prefix = "    " * indent

    # Decorators
    lines.extend(_format_decorators(node.decorator_list, prefix))

    # Class signature with bases
    bases = [_get_name(b) for b in node.bases]
    base_str = f"({', '.join(bases)})" if bases else ""
    line_ref = f"  # L{node.lineno}" if include_line_numbers else ""
    lines.append(f"{prefix}class {node.name}{base_str}:{line_ref}")

    # Docstring
    if (doc := ast.get_docstring(node)):
        summary = doc.strip().splitlines()[0][:80]
        lines.append(f'{prefix}    """{summary}..."""')

    has_content = False

    for child in node.body:
        # Class attributes / Pydantic fields (AnnAssign)
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            field_name = child.target.id
            type_hint = _get_annotation(child.annotation)

            # Get default value if present
            default = ""
            if child.value:
                default = f" = {_get_constant_repr(child.value)}"

            line_ref = f"  # L{child.lineno}" if include_line_numbers else ""
            lines.append(f"{prefix}    {field_name}: {type_hint}{default}{line_ref}")
            has_content = True

        # Class-level assignments (class attributes)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    val = _get_constant_repr(child.value)
                    line_ref = f"  # L{child.lineno}" if include_line_numbers else ""
                    lines.append(f"{prefix}    {target.id} = {val}{line_ref}")
                    has_content = True

        # Methods
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Include dunders, public methods, and optionally private
            if (include_private or
                not child.name.startswith('_') or
                (child.name.startswith('__') and child.name.endswith('__'))):
                _process_function(child, lines, indent + 1, include_line_numbers)
                has_content = True

        # Nested classes
        elif isinstance(child, ast.ClassDef):
            _process_class(child, lines, indent + 1, include_private, include_line_numbers)
            has_content = True

    if not has_content:
        lines.append(f"{prefix}    pass")

    lines.append("")


def _process_function(
    node,
    lines: List[str],
    indent: int,
    include_line_numbers: bool
):
    """Process a function/method definition with decorators."""
    prefix = "    " * indent

    # Decorators
    lines.extend(_format_decorators(node.decorator_list, prefix))

    is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""

    # Build argument list
    args = []
    defaults_offset = len(node.args.args) - len(node.args.defaults)

    for i, arg in enumerate(node.args.args):
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {_get_annotation(arg.annotation)}"

        # Default value
        default_idx = i - defaults_offset
        if 0 <= default_idx < len(node.args.defaults):
            default = node.args.defaults[default_idx]
            arg_str += f" = {_get_default_repr(default)}"

        args.append(arg_str)

    # *args
    if node.args.vararg:
        vararg = f"*{node.args.vararg.arg}"
        if node.args.vararg.annotation:
            vararg += f": {_get_annotation(node.args.vararg.annotation)}"
        args.append(vararg)

    # **kwargs
    if node.args.kwarg:
        kwarg = f"**{node.args.kwarg.arg}"
        if node.args.kwarg.annotation:
            kwarg += f": {_get_annotation(node.args.kwarg.annotation)}"
        args.append(kwarg)

    # Return annotation
    ret = ""
    if node.returns:
        ret = f" -> {_get_annotation(node.returns)}"

    line_ref = f"  # L{node.lineno}" if include_line_numbers else ""
    lines.append(f"{prefix}{is_async}def {node.name}({', '.join(args)}){ret}: ...{line_ref}")

    # Docstring summary
    if (doc := ast.get_docstring(node)):
        summary = doc.strip().splitlines()[0][:80]
        lines.append(f'{prefix}    """{summary}..."""')


def _get_name(node) -> str:
    """Get name from various AST node types."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    elif isinstance(node, ast.Subscript):
        return f"{_get_name(node.value)}[{_get_annotation(node.slice)}]"
    return "..."


def _get_annotation(node) -> str:
    """Get type annotation string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        return repr(node.value)
    elif isinstance(node, ast.Subscript):
        value = _get_name(node.value)
        slice_val = _get_annotation(node.slice)
        return f"{value}[{slice_val}]"
    elif isinstance(node, ast.Tuple):
        return ", ".join(_get_annotation(e) for e in node.elts)
    elif isinstance(node, ast.Attribute):
        return _get_name(node)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{_get_annotation(node.left)} | {_get_annotation(node.right)}"
    elif isinstance(node, ast.List):
        if node.elts:
            return "[" + ", ".join(_get_annotation(e) for e in node.elts[:2]) + ", ...]"
        return "[]"
    return "..."


def _get_default_repr(node) -> str:
    """Get string representation of default value."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str) and len(node.value) > 20:
            return '"..."'
        return repr(node.value)
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, (ast.List, ast.Tuple)):
        return "..." if node.elts else "[]"
    elif isinstance(node, ast.Dict):
        return "..." if node.keys else "{}"
    elif isinstance(node, ast.Call):
        return f"{_get_name(node.func)}(...)"
    return "..."


def parse_imports(filepath: str) -> Tuple[List[str], List[str]]:
    """
    Parse imports from a Python file.

    Args:
        filepath: Path to Python file

    Returns:
        Tuple of (absolute_imports, relative_imports)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return [], []

    absolute_imports = []
    relative_imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0:
                prefix = "." * node.level
                relative_imports.append(f"{prefix}{module}")
            else:
                absolute_imports.append(module)

    return absolute_imports, relative_imports


def get_class_hierarchy(filepath: str) -> Dict[str, List[str]]:
    """
    Extract class inheritance hierarchy from a Python file.

    Args:
        filepath: Path to Python file

    Returns:
        Dict mapping class names to their base classes
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return {}

    hierarchy = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [_get_name(base) for base in node.bases]
            hierarchy[node.name] = bases

    return hierarchy
