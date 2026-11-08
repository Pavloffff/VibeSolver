from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, cast

from tree_sitter import Language, Node, Parser
from tree_sitter_language_pack import get_language

AST_PARSER_VERSION = "tree-sitter-registry-v2"
AST_CHUNKER_VERSION = "ast-declarations-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CHUNK_CHARACTERS = 12_000
MAX_AST_NODES = 200_000
LINE_OVERLAP = 4


@dataclass(frozen=True, slots=True)
class CodeChunk:
    path: str
    branch: str
    content_hash: str
    language: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CodeFileResult:
    chunks: list[CodeChunk]
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class LanguageGrammar:
    name: str
    load: Callable[[], Language]
    declaration_types: frozenset[str]
    scope_types: frozenset[str]


GRAMMAR_REGISTRY: dict[str, LanguageGrammar] = {}


def register_grammar(extensions: tuple[str, ...], grammar: LanguageGrammar) -> None:
    for extension in extensions:
        normalized = extension.lower().lstrip(".")
        if not normalized:
            raise ValueError("grammar extension must not be empty")
        GRAMMAR_REGISTRY[normalized] = grammar


def _grammar(
    name: str,
    declarations: tuple[str, ...] = (),
    scopes: tuple[str, ...] = (),
) -> LanguageGrammar:
    return LanguageGrammar(
        name=name,
        load=lambda: get_language(cast(Any, _LANGUAGE_NAMES.get(name, name))),
        declaration_types=frozenset(declarations),
        scope_types=frozenset(scopes),
    )


_COMMON_DECLARATIONS = (
    "function_declaration",
    "function_definition",
    "class_declaration",
    "class_definition",
    "method_definition",
    "method_declaration",
    "interface_declaration",
    "type_declaration",
    "type_alias_declaration",
    "enum_declaration",
    "struct_item",
    "trait_item",
    "impl_item",
    "mod_item",
)
_COMMON_SCOPES = (
    "class_declaration",
    "class_definition",
    "interface_declaration",
    "struct_item",
    "trait_item",
    "impl_item",
    "mod_item",
)
_LANGUAGE_STRUCTURES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "rust": (
        (
            "function_item",
            "struct_item",
            "enum_item",
            "trait_item",
            "impl_item",
            "mod_item",
            "type_item",
            "const_item",
            "static_item",
        ),
        ("struct_item", "enum_item", "trait_item", "impl_item", "mod_item"),
    ),
    "go": (
        (
            "function_declaration",
            "method_declaration",
            "type_declaration",
            "const_declaration",
            "var_declaration",
        ),
        ("type_declaration",),
    ),
    "java": (
        (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "method_declaration",
            "constructor_declaration",
        ),
        ("class_declaration", "interface_declaration", "enum_declaration", "record_declaration"),
    ),
    "kotlin": (
        (
            "class_declaration",
            "object_declaration",
            "function_declaration",
            "property_declaration",
            "type_alias",
        ),
        ("class_declaration", "object_declaration"),
    ),
    "c": (
        (
            "function_definition",
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "type_definition",
        ),
        ("struct_specifier", "union_specifier", "enum_specifier"),
    ),
    "cpp": (
        (
            "function_definition",
            "class_specifier",
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "namespace_definition",
            "template_declaration",
        ),
        ("class_specifier", "struct_specifier", "union_specifier", "namespace_definition"),
    ),
    "csharp": (
        (
            "class_declaration",
            "struct_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "method_declaration",
            "constructor_declaration",
        ),
        ("class_declaration", "struct_declaration", "interface_declaration", "record_declaration"),
    ),
    "ruby": (
        ("class", "module", "method", "singleton_method"),
        ("class", "module", "method"),
    ),
    "php": (
        (
            "function_definition",
            "class_declaration",
            "interface_declaration",
            "trait_declaration",
            "method_declaration",
        ),
        ("class_declaration", "interface_declaration", "trait_declaration"),
    ),
    "swift": (
        (
            "class_declaration",
            "struct_declaration",
            "enum_declaration",
            "protocol_declaration",
            "function_declaration",
            "init_declaration",
        ),
        ("class_declaration", "struct_declaration", "enum_declaration", "protocol_declaration"),
    ),
    "dart": (
        (
            "class_definition",
            "mixin_declaration",
            "enum_declaration",
            "extension_declaration",
            "function_signature",
            "method_signature",
        ),
        ("class_definition", "mixin_declaration", "enum_declaration", "extension_declaration"),
    ),
    "scala": (
        (
            "class_definition",
            "object_definition",
            "trait_definition",
            "function_definition",
            "type_definition",
        ),
        ("class_definition", "object_definition", "trait_definition"),
    ),
    "haskell": (("function", "data_type", "type_synomym"), ("data_type",)),
    "lua": (("function_declaration",), ("function_declaration",)),
    "perl": (("subroutine_declaration_statement", "package_statement"), ("package_statement",)),
    "julia": (
        ("function_definition", "struct_definition", "module_definition", "macro_definition"),
        ("struct_definition", "module_definition"),
    ),
    "objective_c": (
        ("function_definition", "class_interface", "class_implementation", "method_definition"),
        ("class_interface", "class_implementation"),
    ),
    "powershell": (
        ("function_statement", "class_statement", "enum_statement"),
        ("class_statement", "enum_statement"),
    ),
    "groovy": (
        ("class_declaration", "method_declaration", "interface_declaration", "enum_declaration"),
        ("class_declaration", "interface_declaration", "enum_declaration"),
    ),
    "fsharp": (
        ("module_or_namespace", "type_definition", "function_or_value_defn"),
        ("module_or_namespace", "type_definition"),
    ),
    "ocaml": (("value_definition", "type_definition", "module_definition"), ("module_definition",)),
    "zig": (("FnProto", "FnDecl", "ContainerDecl"), ("ContainerDecl",)),
}

_LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": ("py", "pyi", "pyw"),
    "javascript": ("js", "jsx", "mjs", "cjs"),
    "typescript": ("ts", "mts", "cts"),
    "tsx": ("tsx",),
    "rust": ("rs",),
    "go": ("go",),
    "java": ("java",),
    "kotlin": ("kt", "kts"),
    "c": ("c", "h"),
    "cpp": ("cc", "cpp", "cxx", "hh", "hpp", "hxx"),
    "csharp": ("cs",),
    "ruby": ("rb",),
    "php": ("php", "phtml"),
    "swift": ("swift",),
    "dart": ("dart",),
    "scala": ("scala", "sc"),
    "elixir": ("ex", "exs"),
    "erlang": ("erl", "hrl"),
    "haskell": ("hs", "lhs"),
    "lua": ("lua",),
    "perl": ("pl", "pm", "t"),
    "r": ("r", "rmd"),
    "julia": ("jl",),
    "objective_c": ("m", "mm"),
    "bash": ("sh", "bash", "zsh", "ksh"),
    "powershell": ("ps1", "psm1", "psd1"),
    "groovy": ("groovy", "gvy", "gy", "gsh", "gradle"),
    "starlark": ("bzl", "sky"),
    "requirements": ("requirements",),
    "sql": ("sql",),
    "graphql": ("graphql", "gql"),
    "proto": ("proto",),
    "yaml": ("yaml", "yml"),
    "json": ("json", "jsonc"),
    "jsonnet": ("jsonnet", "libsonnet"),
    "toml": ("toml",),
    "hcl": ("tf", "tfvars", "hcl", "nomad"),
    "bicep": ("bicep",),
    "ini": ("ini",),
    "properties": ("properties", "prop"),
    "rego": ("rego",),
    "dockerfile": ("dockerfile",),
    "make": ("mk",),
    "cmake": ("cmake",),
    "html": ("html", "htm"),
    "css": ("css",),
    "scss": ("scss",),
    "vue": ("vue",),
    "svelte": ("svelte",),
    "astro": ("astro",),
    "xml": ("xml", "xsd", "xsl", "svg"),
    "markdown": ("md", "markdown", "mdx"),
    "zig": ("zig",),
    "ocaml": ("ml", "mli"),
    "ocaml_interface": ("mli",),
    "fsharp": ("fs", "fsi", "fsx"),
    "fortran": ("f", "for", "f90", "f95", "f03", "f08"),
    "cobol": ("cob", "cbl"),
    "solidity": ("sol",),
    "verilog": ("v", "vh"),
    "vhdl": ("vhd", "vhdl"),
    "nix": ("nix",),
    "elisp": ("el",),
    "gitignore": ("gitignore",),
    "gitattributes": ("gitattributes",),
}

_LANGUAGE_NAMES = {
    "objective_c": "objc",
    "ocaml_interface": "ocaml_interface",
    "fsharp": "fsharp",
}

for _language_name, _extensions in _LANGUAGE_EXTENSIONS.items():
    _is_source_language = _language_name not in {
        "yaml",
        "json",
        "toml",
        "hcl",
        "dockerfile",
        "make",
        "cmake",
        "html",
        "css",
        "scss",
        "vue",
        "svelte",
        "astro",
        "xml",
        "markdown",
        "jsonnet",
        "bicep",
        "ini",
        "properties",
        "rego",
    }
    _declarations, _scopes = _LANGUAGE_STRUCTURES.get(
        _language_name,
        (_COMMON_DECLARATIONS, _COMMON_SCOPES) if _is_source_language else ((), ()),
    )
    register_grammar(
        _extensions,
        _grammar(
            _language_name,
            _declarations,
            _scopes,
        ),
    )

_FILENAME_GRAMMARS = {
    "dockerfile": "dockerfile",
    "containerfile": "dockerfile",
    "makefile": "make",
    "gnumakefile": "make",
    "jenkinsfile": "groovy",
    "requirements.txt": "requirements",
    "go.mod": "gomod",
    "go.sum": "gosum",
    "cmakelists.txt": "cmake",
    ".editorconfig": "ini",
    "build": "starlark",
    "workspace": "starlark",
    "buck": "starlark",
    "tiltfile": "starlark",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "vagrantfile": "ruby",
    "brewfile": "ruby",
    ".gitignore": "gitignore",
    ".gitattributes": "gitattributes",
    ".dockerignore": "gitignore",
    ".bashrc": "bash",
    ".zshrc": "bash",
}


def chunk_code_file(
    *,
    path: str,
    content: bytes,
    content_hash: str,
    branch: str = "",
    metadata: dict[str, Any] | None = None,
) -> CodeFileResult:
    filename = PurePosixPath(path).name.lower()
    if filename.startswith(("dockerfile.", "containerfile.")):
        extension = "dockerfile"
    elif filename.startswith(("makefile.", "gnumakefile.")):
        extension = "make"
    else:
        extension = _FILENAME_GRAMMARS.get(filename, PurePosixPath(path).suffix.lower().lstrip("."))
    if len(content) > MAX_SOURCE_BYTES:
        return CodeFileResult([], f"File exceeds the parser limit of {MAX_SOURCE_BYTES} bytes")
    if b"\x00" in content:
        return CodeFileResult([], "Binary content is not indexed as source code")
    grammar = GRAMMAR_REGISTRY.get(extension)
    if grammar is None:
        return _plain_text_fallback(
            path,
            content,
            content_hash,
            branch,
            metadata or {},
            f"No tree-sitter grammar is registered for .{extension or '(none)'}; indexed as text",
        )
    try:
        parser = Parser(grammar.load())
        tree = parser.parse(content)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return _plain_text_fallback(
            path,
            content,
            content_hash,
            branch,
            metadata or {},
            f"Tree-sitter grammar is unavailable; indexed as text ({type(exc).__name__})",
        )
    if tree is None:
        return CodeFileResult([], "Tree-sitter parser timed out")

    lines = content.decode("utf-8", errors="replace").splitlines()
    chunks: list[CodeChunk] = []
    visited_nodes = 0
    parse_errors = tree.root_node.has_error

    def visit(node: Node, scopes: tuple[str, ...]) -> Iterator[CodeChunk]:
        nonlocal visited_nodes
        visited_nodes += 1
        if visited_nodes > MAX_AST_NODES:
            raise OverflowError("Tree-sitter AST node limit exceeded")
        next_scopes = scopes
        if node.type in grammar.declaration_types:
            name = _node_name(node, content)
            symbol = ".".join((*scopes, name)) if name else ".".join(scopes) or "<module>"
            start_line = node.start_point.row + 1
            code = content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            yield from _split_chunk(
                path=path,
                branch=branch,
                content_hash=content_hash,
                language=grammar.name,
                symbol=symbol,
                start_line=start_line,
                code=code,
                metadata=metadata or {},
            )
            if name and node.type in grammar.scope_types:
                next_scopes = (*scopes, name)
        for child in node.children:
            yield from visit(child, next_scopes)

    try:
        chunks.extend(visit(tree.root_node, ()))
    except OverflowError as exc:
        return CodeFileResult([], str(exc))

    if not chunks and lines:
        chunks.extend(
            _split_chunk(
                path=path,
                branch=branch,
                content_hash=content_hash,
                language=grammar.name,
                symbol="<module>",
                start_line=1,
                code="\n".join(lines),
                metadata=metadata or {},
            )
        )
    diagnostic = (
        "Parser recovered declarations from a file with syntax errors" if parse_errors else None
    )
    return CodeFileResult(chunks, diagnostic)


def _plain_text_fallback(
    path: str,
    content: bytes,
    content_hash: str,
    branch: str,
    metadata: dict[str, Any],
    diagnostic: str | None = None,
) -> CodeFileResult:
    text = content.decode("utf-8-sig", errors="replace")
    if not text.strip():
        return CodeFileResult([], diagnostic or "File contains no text")
    chunks = _split_chunk(
        path=path,
        branch=branch,
        content_hash=content_hash,
        language="plain-text",
        symbol="<text>",
        start_line=1,
        code=text,
        metadata={**metadata, "parser": "text-fallback"},
    )
    return CodeFileResult(chunks, diagnostic)


def _node_name(node: Node, content: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = next(
            (
                child
                for child in node.children
                if child.type in {"identifier", "property_identifier", "type_identifier"}
            ),
            None,
        )
    if name_node is None:
        return ""
    return content[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace")


def _split_chunk(
    *,
    path: str,
    branch: str,
    content_hash: str,
    language: str,
    symbol: str,
    start_line: int,
    code: str,
    metadata: dict[str, Any],
) -> list[CodeChunk]:
    if len(code) <= MAX_CHUNK_CHARACTERS:
        line_count = max(1, len(code.splitlines()))
        return [
            CodeChunk(
                path=path,
                branch=branch,
                content_hash=content_hash,
                language=language,
                symbol=symbol,
                start_line=start_line,
                end_line=start_line + line_count - 1,
                content=code,
                metadata=metadata,
            )
        ]
    result: list[CodeChunk] = []
    lines = code.splitlines()
    start = 0
    while start < len(lines):
        end = start
        length = 0
        while end < len(lines) and length + len(lines[end]) + 1 <= MAX_CHUNK_CHARACTERS:
            length += len(lines[end]) + 1
            end += 1
        if end == start:
            end += 1
        text = "\n".join(lines[start:end])
        result.append(
            CodeChunk(
                path=path,
                branch=branch,
                content_hash=content_hash,
                language=language,
                symbol=f"{symbol} [part {len(result) + 1}]",
                start_line=start_line + start,
                end_line=start_line + end - 1,
                content=text,
                metadata=metadata,
            )
        )
        if end >= len(lines):
            break
        start = max(start + 1, end - LINE_OVERLAP)
    return result
