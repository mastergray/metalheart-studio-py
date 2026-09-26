# Repository-owned checks for required Python structure and documentation rules

import ast  # Inspect production syntax without importing runtime dependencies
import re  # Validate camelCase method and function names
from pathlib import Path  # Discover and read production Python modules
from typing import List  # Python 3.8-compatible error collection annotation


CAMEL_CASE = re.compile(r"^_?[a-z][A-Za-z0-9]*$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATHS = sorted((REPOSITORY_ROOT / "metalheart").glob("*.py")) + [REPOSITORY_ROOT / "studio.py"]


# :: PATH -> [STRING]
# Finds style violations in one production Python module
def _checkModule(path: Path) -> List[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    errors: List[str] = []
    if ast.get_docstring(tree, clean=False) is not None:
        errors.append("module docstrings are forbidden")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            line = lines[node.lineno - 1]
            if "#" not in line:
                errors.append("line {0}: import needs a purpose comment".format(node.lineno))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in ("__init__", "__str__", "__repr__", "__eq__") and not CAMEL_CASE.match(node.name):
                errors.append("line {0}: function is not camelCase: {1}".format(node.lineno, node.name))
            for argument in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
                if argument.arg not in ("self", "cls") and argument.annotation is None:
                    errors.append("line {0}: untyped parameter: {1}".format(node.lineno, argument.arg))
            if node.args.vararg is not None and node.args.vararg.annotation is None:
                errors.append("line {0}: untyped variadic parameter".format(node.lineno))
            if node.args.kwarg is not None and node.args.kwarg.annotation is None:
                errors.append("line {0}: untyped keyword parameter".format(node.lineno))
            if node.returns is None:
                errors.append("line {0}: missing return annotation".format(node.lineno))
            signatureStart = max(0, node.lineno - 7)
            preceding = lines[signatureStart:node.lineno - 1]
            if not any("::" in line and line.lstrip().startswith("#") for line in preceding):
                errors.append("line {0}: missing signature comment".format(node.lineno))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    if not target.attr.startswith("_"):
                        errors.append("line {0}: instance attribute needs a leading underscore: {1}".format(node.lineno, target.attr))
    return ["{0}: {1}".format(path.relative_to(REPOSITORY_ROOT), error) for error in errors]


# :: VOID -> NONE
# Verifies production modules follow the repository's enforceable style subset
def testProductionPythonStyle() -> None:
    errors: List[str] = []
    for path in PRODUCTION_PATHS:
        errors.extend(_checkModule(path))
    assert not errors, "\n" + "\n".join(errors)

