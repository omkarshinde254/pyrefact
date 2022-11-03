import ast
import functools
import itertools
from typing import Collection, Iterable, Sequence, Tuple, Union


def is_valid_python(content: str) -> bool:
    """Determine if source code is valid python.

    Args:
        content (str): Python source code

    Returns:
        bool: True if content is valid python.
    """
    try:
        ast.parse(content, "")
        return True
    except SyntaxError:
        return False


def _unpack_ast_target(target: ast.AST) -> Iterable[ast.Name]:
    if isinstance(target, ast.Name):
        yield target
        return
    if isinstance(target, ast.Tuple):
        for subtarget in target.elts:
            yield from _unpack_ast_target(subtarget)


def iter_assignments(ast_tree: ast.Module) -> Iterable[ast.Name]:
    """Iterate over defined variables in code

    Args:
        content (str): Python source code

    Yields:
        ast.Name: A name that is being assigned.
    """
    for node in ast_tree.body:
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            yield from _unpack_ast_target(node.target)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                yield from _unpack_ast_target(target)


def iter_funcdefs(ast_tree: ast.Module) -> Iterable[ast.FunctionDef]:
    """Iterate over defined variables in code

    Args:
        content (str): Python source code

    Yields:
        ast.FunctionDef: A function definition node
    """
    for node in ast_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def iter_classdefs(ast_tree: ast.Module) -> Iterable[ast.ClassDef]:
    """Iterate over defined variables in code

    Args:
        content (str): Python source code

    Yields:
        ast.ClassDef: A class definition node
    """
    for node in ast_tree.body:
        if isinstance(node, (ast.ClassDef)):
            yield node


def has_side_effect(
    node: ast.AST,
    safe_callable_whitelist: Collection[str] = frozenset(),
) -> bool:
    """Determine if a statement has a side effect.

    A statement has a side effect if it can influence the outcome of a subsequent statement.
    A slight exception to this rule exists: Anything named "_" is assumed to be unused and
    meaningless. So a statement like "_ = 100" is assumed to have no side effect.

    Args:
        node (ast.AST): Node to check
        safe_callable_whitelist (Collection[str]): Items known to not have a side effect

    Returns:
        bool: True if it may have a side effect.

    """
    if isinstance(
        node,
        (
            ast.Yield,
            ast.YieldFrom,
            ast.Return,
            ast.Raise,
            ast.Continue,
            ast.Break,
            ast.Assert,
        ),
    ):
        return True

    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name != "_"

    if isinstance(node, ast.For):
        return any(
            has_side_effect(item, safe_callable_whitelist)
            for item in itertools.chain(
                [node.target],
                [node.iter],
                node.body,
            )
        )

    if isinstance(node, ast.Lambda):
        return has_side_effect(node.args, safe_callable_whitelist) or has_side_effect(
            node.body, safe_callable_whitelist
        )

    if isinstance(node, ast.arguments):
        return any(
            has_side_effect(item, safe_callable_whitelist)
            for item in itertools.chain(
                node.posonlyargs,
                node.args,
                node.kwonlyargs,
                node.kw_defaults,
                node.defaults,
            )
        )

    if node is None:
        return False

    if isinstance(node, ast.Module):
        return any(has_side_effect(value, safe_callable_whitelist) for value in node.body)

    if isinstance(node, (ast.Constant, ast.Pass)):
        return False

    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return True

    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(has_side_effect(value, safe_callable_whitelist) for value in node.elts)

    if isinstance(node, ast.Dict):
        return any(
            has_side_effect(value, safe_callable_whitelist)
            for value in itertools.chain(node.keys, node.values)
        )

    if isinstance(node, ast.Expr):
        return has_side_effect(node.value, safe_callable_whitelist)

    if isinstance(node, ast.Expression):
        return has_side_effect(node.body, safe_callable_whitelist)

    if isinstance(node, ast.UnaryOp):
        return has_side_effect(node.operand, safe_callable_whitelist)

    if isinstance(node, ast.BinOp):
        return any(
            has_side_effect(child, safe_callable_whitelist) for child in (node.left, node.right)
        )

    if isinstance(node, ast.Compare):
        return any(
            has_side_effect(child, safe_callable_whitelist)
            for child in [node.left] + node.comparators
        )

    if isinstance(node, ast.BoolOp):
        return any(has_side_effect(value, safe_callable_whitelist) for value in node.values)

    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Store) and node.id != "_"

    if isinstance(node, ast.Subscript):
        return (
            has_side_effect(node.value, safe_callable_whitelist)
            or has_side_effect(node.slice, safe_callable_whitelist)
            or (isinstance(node.ctx, ast.Store) and node.value.id != "_")
        )

    if isinstance(node, ast.Slice):
        return any(
            has_side_effect(child, safe_callable_whitelist) for child in (node.lower, node.upper)
        )

    if isinstance(node, (ast.DictComp)) and has_side_effect(node.value, safe_callable_whitelist):
        return True

    if isinstance(node, (ast.SetComp, ast.ListComp, ast.GeneratorExp, ast.DictComp)):
        return any(has_side_effect(item, safe_callable_whitelist) for item in node.generators)

    if isinstance(node, ast.comprehension):
        if (
            isinstance(node.target, ast.Name)
            and not has_side_effect(node.iter, safe_callable_whitelist)
            and not any(has_side_effect(value, safe_callable_whitelist) for value in node.ifs)
        ):
            return False
        return True

    if isinstance(node, ast.Call):
        return (
            has_side_effect(node.func, safe_callable_whitelist)
            or not all(
                child.id in safe_callable_whitelist or child.id == "_"
                for child in ast.walk(node.func)
                if isinstance(child, ast.Name)
            )
            or any(has_side_effect(item, safe_callable_whitelist) for item in node.args)
            or any(has_side_effect(item.value, safe_callable_whitelist) for item in node.keywords)
        )

    if isinstance(node, ast.Starred):
        return has_side_effect(node.value, safe_callable_whitelist)

    if isinstance(node, ast.If):
        return any(
            has_side_effect(item, safe_callable_whitelist)
            for item in itertools.chain(node.body, [node.test], node.orelse)
        )

    if isinstance(node, ast.IfExp):
        return any(
            has_side_effect(child, safe_callable_whitelist)
            for child in (node.test, node.body, node.orelse)
        )

    if isinstance(node, ast.Subscript):
        return isinstance(node.ctx, ast.Store) or any(
            has_side_effect(child, safe_callable_whitelist) for child in (node.value, node.slice)
        )

    # NamedExpr is :=
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target]
        return has_side_effect(node.value) or any(has_side_effect(target) for target in targets)

    return True


@functools.lru_cache(maxsize=1)
def _get_line_lengths(content: str) -> Sequence[int]:
    return tuple([len(line) for line in content.splitlines(keepends=True)])


def get_charnos(node: ast.AST, content: str) -> Tuple[int, int]:
    """Get start and end character numbers in source code from ast node.

    Args:
        node (ast.AST): Node to fetch character numbers for
        content (str): Python source code

    Returns:
        Tuple[int, int]: start, end
    """
    line_lengths = _get_line_lengths(content)

    start_charno = sum(line_lengths[: node.lineno - 1]) + node.col_offset
    end_charno = sum(line_lengths[: node.end_lineno - 1]) + node.end_col_offset

    return start_charno, end_charno


def get_code(node: ast.AST, content: str) -> str:
    """Get python code from ast

    Args:
        node (ast.AST): ast to get code from
        content (str): Python source code that ast was parsed from

    Returns:
        str: Python source code

    """
    start_charno, end_charno = get_charnos(node, content)
    return content[start_charno:end_charno]


def literal_value(node: ast.AST) -> bool:
    if has_side_effect(node):
        raise ValueError("Cannot find a deterministic value for a node with a side effect")

    return ast.literal_eval(node)


def _is_exception(node: ast.AST) -> bool:
    """Check if a node is an exception.

    Args:
        node (ast.AST): Node to check

    Returns:
        bool: True if it will always raise an exception
    """
    if isinstance(node, ast.Raise):
        return True

    if isinstance(node, ast.Assert):
        try:
            return not literal_value(node.test)
        except (ValueError, AttributeError):
            return False

    return False


def is_blocking(node: ast.AST, parent_type: ast.AST = None) -> bool:
    """Check if a node is impossible to get past.

    Args:
        node (ast.AST): Node to check

    Returns:
        bool: True if no code after this node can ever be executed.
    """
    if _is_exception(node):
        return True

    if parent_type is None:
        blocking_types = (ast.Return, ast.Continue, ast.Break)
    elif parent_type in (ast.For, ast.While):
        blocking_types = (ast.Return,)

    if isinstance(node, blocking_types):
        return True

    if isinstance(node, ast.If):
        try:
            branch = node.body if literal_value(node.test) else node.orelse
        except ValueError:
            branches = [node.body, node.orelse]
            return all(
                any(is_blocking(child, parent_type) for child in branch) for branch in branches
            )
        else:
            return any(is_blocking(child, parent_type) for child in branch)

    if isinstance(node, ast.While):
        try:
            test_value = literal_value(node.test)
        except ValueError:
            pass
        else:
            if not test_value:
                return False

            for child in node.body:
                if isinstance(child, ast.Break):
                    return False
                if is_blocking(child, type(node)):
                    return True

    if isinstance(node, (ast.For, ast.While)):
        for child in node.body:
            if is_blocking(child, type(node)):
                return True
            if is_blocking(child, parent_type):
                return False
        if isinstance(node, ast.For):
            return False
        try:
            return literal_value(node.test)
        except ValueError:
            return False

    if isinstance(node, ast.With):
        return any(is_blocking(child, parent_type) for child in node.body)

    return False


def iter_bodies_recursive(
    ast_root: ast.Module,
) -> Iterable[Union[ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef]]:
    left = list(ast_root.body)
    while left:
        for node in left.copy():
            left.remove(node)
            if isinstance(
                node,
                (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef, ast.For, ast.While, ast.With),
            ):
                left.extend(node.body)
                yield node
            if isinstance(node, ast.If):
                left.extend(node.body)
                left.extend(node.orelse)
                yield node
