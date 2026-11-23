import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_METHOD = r"GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE|CONNECT"
_PATH = r"/[a-zA-Z0-9_.:/%{}<>\[\]-]*"
_MARKUP = r"[`*_]*"
_CLAIM = re.compile(rf"\b(?P<method>{_METHOD})\b{_MARKUP}[:\s]+{_MARKUP}(?P<path>{_PATH})")
_REVERSED_CLAIM = re.compile(
    rf"(?P<path>{_PATH}){_MARKUP}\s+(?:endpoint\s+)?"
    rf"(?:accepts|handles|responds to|supports|uses)\s+{_MARKUP}(?P<method>{_METHOD})\b"
)
_TABLE_CLAIMS = (
    re.compile(
        rf"(?m)(?:^|\|)[ \t]*{_MARKUP}(?P<method>{_METHOD}){_MARKUP}[ \t]*\|[ \t]*{_MARKUP}(?P<path>{_PATH}){_MARKUP}[ \t]*(?=\||$)"
    ),
    re.compile(
        rf"(?m)(?:^|\|)[ \t]*{_MARKUP}(?P<path>{_PATH}){_MARKUP}[ \t]*\|[ \t]*{_MARKUP}(?P<method>{_METHOD}){_MARKUP}[ \t]*(?=\||$)"
    ),
)
_INLINE_HTML = re.compile(r"</?(?:code|strong|em|b|i)>", re.IGNORECASE)
_QUOTED_PATH = rf"""["'](?P<path>{_PATH})["']"""
_DECLARATIONS = [
    rf"(?im)(?:@|\b(?=(?:app|router|routes|server|api|r)\.))(?P<receiver>\w+)\.(?P<method>{_METHOD})\s*\(\s*{_QUOTED_PATH}",
    rf"""\b(?:[Hh]andleFunc|[Hh]andle)\s*\(\s*["'](?P<method>{_METHOD})\s+(?P<path>{_PATH})["']""",
    rf"(?i)(?:@(?P<method>{_METHOD})Mapping|\[Http(?P<alt_method>{_METHOD})|\.Map(?P<map_method>{_METHOD}))\s*\(\s*(?:(?:path|value|template)\s*=\s*)?{_QUOTED_PATH}",
    rf"(?i)\broute\s*\(\s*{_QUOTED_PATH}\s*,\s*(?:\w+::)?(?P<method>{_METHOD})\s*\(",
    rf"(?i)\broute\s*\(\s*{_QUOTED_PATH}\s*\)\s*\.(?P<method>{_METHOD})\s*\(",
    rf"(?i)\bresource\s*\(\s*{_QUOTED_PATH}\s*\)\s*\.route\s*\(\s*(?:\w+::)?(?P<method>{_METHOD})\s*\(",
    rf"""\bHandleFunc\s*\(\s*{_QUOTED_PATH}\s*,[^)\n]+\)\s*\.Methods\s*\(\s*["'](?P<method>{_METHOD})["']""",
]
_PYTHON_PREFIX = re.compile(
    rf"""\b(?P<receiver>\w+)\s*=\s*APIRouter\s*\([^)]{{0,1000}}?\bprefix\s*=\s*{_QUOTED_PATH}"""
)
_ROUTE_WITH_METHODS = re.compile(
    rf"""(?i)@\w+\.route\s*\(\s*{_QUOTED_PATH}\s*,\s*methods\s*=\s*\[(?P<methods>[^\]]*)\]"""
)
_JAVA_ROUTE = re.compile(r"@RequestMapping\s*\(([^()]*)\)")
_METHOD_TOKEN = re.compile(rf"\b(?:{_METHOD})\b", re.IGNORECASE)
_JSON_OBJECT = re.compile(r'\{(?:[^{}"]|"(?:[^"\\]|\\.)*")*\}')
_JSON_PATH = re.compile(rf'"(?:path|route)"\s*:\s*{_QUOTED_PATH}')
_JSON_METHOD = re.compile(rf'"method"\s*:\s*"(?P<method>{_METHOD})"', re.IGNORECASE)
_YAML_ROUTE = re.compile(
    rf"""(?im)^(?P<indent>[ \t]*)(?P<sequence>-\s*)?(?:path|route):\s*["']?(?P<path>{_PATH})["']?[ \t]*$
(?P=indent)(?(sequence)[ \t]+|)method:[ \t]*["']?(?P<method>{_METHOD})["']?[ \t]*$"""
)
_YAML_REVERSED = re.compile(
    rf"""(?im)^(?P<indent>[ \t]*)(?P<sequence>-\s*)?method:[ \t]*["']?(?P<method>{_METHOD})["']?[ \t]*$
(?P=indent)(?(sequence)[ \t]+|)(?:path|route):\s*["']?(?P<path>{_PATH})["']?[ \t]*$"""
)
_BLOCK_COMMENTS = re.compile(r"/\*.*?\*/|<!--.*?-->", re.DOTALL)
_COMMENT_LINE = re.compile(r"^\s*(?://|#(?!\[)|\*|--)", re.MULTILINE)
_CONTRACT_ROOT = re.compile(r"(?im)^\s*(?:openapi|swagger)\s*:")
_CONTRACT_NAME = re.compile(r"(?:^|[._-])(?:openapi|swagger)(?:$|[._-])")
_PARAMETER = re.compile(r"^(?:\{[^{}]+\}|<[^<>]+>|:[\w-]+|\[[^\[\]]+\])$")


@dataclass(frozen=True, slots=True)
class EndpointClaim:
    method: str
    path: str

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"


def _claim_path(path: str) -> str:
    path = path.rstrip(".")
    for start, end in (("[", "]"), ("<", ">")):
        if path.endswith(end) and path.count(end) > path.count(start):
            path = path[:-1]
    return path


def endpoint_claims(answer: str) -> list[EndpointClaim]:
    text = _INLINE_HTML.sub("", answer)
    return list(
        dict.fromkeys(
            EndpointClaim(match["method"], _claim_path(match["path"]))
            for pattern in (_CLAIM, _REVERSED_CLAIM, *_TABLE_CLAIMS)
            for match in pattern.finditer(text)
        )
    )


def _matches_path(binding: str, claimed: str) -> bool:
    actual, expected = binding.split("/"), claimed.split("/")
    return len(actual) == len(expected) and all(
        value == claim or (_PARAMETER.fullmatch(value) is not None and bool(claim))
        for value, claim in zip(actual, expected, strict=True)
    )


def _routing_declarations(source: str) -> set[EndpointClaim]:
    declarations = set()
    prefixes = {
        match["receiver"]: match["path"].rstrip("/") for match in _PYTHON_PREFIX.finditer(source)
    }
    patterns = [*map(re.compile, _DECLARATIONS), _YAML_ROUTE, _YAML_REVERSED]
    for pattern in patterns:
        for match in pattern.finditer(source):
            fields = match.groupdict()
            method = next(
                value for key, value in fields.items() if key.endswith("method") and value
            )
            prefix = prefixes.get(fields.get("receiver") or "", "")
            declarations.add(EndpointClaim(method.upper(), f"{prefix}{match['path']}"))
    for match in _ROUTE_WITH_METHODS.finditer(source):
        declarations.update(
            EndpointClaim(method.upper(), match["path"])
            for method in _METHOD_TOKEN.findall(match["methods"])
        )
    for match in _JAVA_ROUTE.finditer(source):
        arguments = match[1]
        path = re.search(rf"""(?:\b(?:path|value)\s*=\s*)?{_QUOTED_PATH}""", arguments)
        if path is not None:
            declarations.update(
                EndpointClaim(method, path["path"])
                for method in re.findall(rf"\bRequestMethod\.({_METHOD})\b", arguments)
            )
    for route in _JSON_OBJECT.finditer(source):
        path, method_match = _JSON_PATH.search(route[0]), _JSON_METHOD.search(route[0])
        if path and method_match:
            declarations.add(EndpointClaim(method_match["method"].upper(), path["path"]))
    return declarations


def matching_endpoint_claims(
    source_path: str, excerpt: str, claims: list[EndpointClaim]
) -> set[EndpointClaim]:
    if not claims:
        return set()
    file = PurePosixPath(source_path.casefold())
    if (
        _CONTRACT_NAME.search(file.stem)
        or file.suffix in {".md", ".rst", ".adoc", ".txt", ".sql"}
        or _CONTRACT_ROOT.search(excerpt)
    ):
        return set()
    source = "\n".join(
        line
        for line in _BLOCK_COMMENTS.sub("", excerpt).splitlines()
        if not _COMMENT_LINE.match(line)
    )
    bindings = _routing_declarations(source)
    return {
        claim
        for claim in claims
        if any(
            binding.method == claim.method and _matches_path(binding.path, claim.path)
            for binding in bindings
        )
    }
