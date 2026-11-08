import asyncio
import json
import mimetypes
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.entities import SourceNotFoundError
from app.domain.model_provider_entities import ProviderCredentials
from app.domain.repositories import (
    IndexRunStatus,
    IndexSearchRepository,
    MaterialGenerationGateway,
    ModelProviderRepository,
    RetrievedChunk,
    SourceRepository,
)
from app.usecase.documentation_fs import DocumentationPathError, normalize_documentation_path
from app.usecase.documentation_indexer import chunk_document_file
from app.usecase.indexing import IndexingUsecase
from app.usecase.project_resources import ProjectResourceUsecase
from app.usecase.user_flow_indexer import UserFlowDocument


@dataclass(frozen=True, slots=True)
class GeneratorDefinition:
    required_indexes: tuple[str, ...]
    file_extension: str
    system_prompt: str
    retrieval_queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaterialGenerationConfig:
    timeout_seconds: int
    max_output_tokens: int
    context_chunks: int
    max_context_characters: int
    max_files: int
    max_file_bytes: int
    max_total_bytes: int


MATERIAL_GENERATOR_REGISTRY: dict[str, GeneratorDefinition] = {
    "documentation": GeneratorDefinition(
        ("code",),
        ".md",
        """Write detailed, functional Russian project documentation from source code and existing documentation. """
        "Describe what the product does, user-visible capabilities, concrete workflows, business "
        "rules, data changes, integrations, validation, failure behavior, and how relevant code "
        "components work together. Do not produce only a directory or module overview. Do not "
        "infer behavior unsupported by sources. Prefer separate Markdown files for distinct "
        "functional areas. Use existing documentation to avoid repetition; add complementary "
        "files in the same directories and never replace existing files. "
        "Each file must cite one or more source IDs from the supplied context. Return only JSON "
        'matching this shape: {"files":[{"path":"relative/path.md",'
        '"content":"Markdown text","source_refs":["S1"]}]}.',
        (
            "User-visible product capabilities, end-to-end workflows, request handlers, screens, commands, and API routes; пользовательские возможности, сценарии, API и обработчики запросов",
            "Business logic, use cases, state transitions, validation rules, and decisions that change behavior; бизнес-логика, сценарии использования, переходы состояний и правила проверки",
            "Data entities, database models, repositories, persistence, and important relationships between them; сущности, модели базы данных, репозитории и сохранение данных",
            "Integrations, external services, background jobs, events, queues, and their failure behavior; интеграции, внешние сервисы, фоновые задачи, события, очереди и их ошибки",
            "Authentication, authorization, errors, retries, configuration, and operational behavior; аутентификация, права доступа, ошибки, повторы и настройки",
            "Tests that demonstrate expected behavior, edge cases, and acceptance criteria; тесты, ожидаемое поведение, крайние случаи и критерии приёмки",
            "Module entry points and call paths connecting user actions to business logic and storage; точки входа и цепочки вызовов от действий пользователя до логики и хранилища",
        ),
    ),
    "user_flow": GeneratorDefinition(
        ("code", "documentation"),
        ".json",
        """Identify user workflows from the supplied code and documentation. Do not invent screens or behavior. """
        "The content field of each file must be a JSON array of scenario objects. Every object "
        "must contain a non-empty string title, a non-empty string actor, and a non-empty steps "
        "array. Every step must be an object with non-empty string action and expected_result. "
        "Optional fields are components, failure_modes, checklist, doc_refs, provenance, and "
        "approved. Lists contain strings, provenance is an object, and approved is false. Do not "
        "add other scenario keys. Cite source IDs in the outer file's source_refs. Return only "
        'valid JSON matching this outer shape: {"files":[{"path":'
        '"relative/path.json","content":"JSON text","source_refs":["S1"]}]}.',
        (
            "User-facing workflows, actors, product actions, expected outcomes, decisions, validation, failure modes, related components, and documentation-backed constraints",
            "Concrete UI and API operations, routes, commands, and the business logic they trigger",
        ),
    ),
}


class GeneratedFile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class GeneratedMaterialDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    files: list[GeneratedFile] = Field(min_length=1)


class DocumentationSynthesis(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    summary: str = Field(min_length=80)
    source_refs: list[str] = Field(default_factory=list)


class MaterialGenerationUnavailableError(ValueError):
    pass


class MaterialGenerationResponseError(RuntimeError):
    pass


class MaterialGenerationConflictError(ValueError):
    def __init__(self, conflicts: list[dict[str, str]]) -> None:
        super().__init__("generated paths already exist with different content")
        self.conflicts = conflicts


class MaterialGenerationUsecase:
    def __init__(
        self,
        sources: SourceRepository,
        models: ModelProviderRepository,
        indexes: IndexingUsecase,
        search: IndexSearchRepository,
        gateway: MaterialGenerationGateway,
        resources: ProjectResourceUsecase,
        config: MaterialGenerationConfig,
    ) -> None:
        self._sources = sources
        self._models = models
        self._indexes = indexes
        self._search = search
        self._gateway = gateway
        self._resources = resources
        self._config = config

    async def generate(
        self, source_id: int, category: str, instructions: str | None
    ) -> list[dict[str, Any]]:
        definition = MATERIAL_GENERATOR_REGISTRY.get(category)
        if definition is None:
            raise MaterialGenerationUnavailableError("unsupported material category")
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        index_state = await self._indexes.status(source_id)
        selected_runs = {}
        for index_type in definition.required_indexes:
            run = next(
                (item for item in index_state.indexes if item.index_type == index_type), None
            )
            if run is None or run.status != "completed" or run.run_id is None:
                raise MaterialGenerationUnavailableError(
                    f"index {index_type} must be completed and current before generation"
                )
            selected_runs[index_type] = run

        selections = await self._models.get_project_selections(source_id)
        generation_model_id = selections.get("documentation_generation")
        embedding_model_id = selections.get("indexing")
        if generation_model_id is None:
            raise MaterialGenerationUnavailableError("select a chat model before generation")
        if embedding_model_id is None:
            raise MaterialGenerationUnavailableError("select an embedding model before generation")
        generation_model = await self._models.get_model(generation_model_id)
        embedding_model = await self._models.get_model(embedding_model_id)
        if generation_model is None or "chat" not in generation_model.capabilities:
            raise MaterialGenerationUnavailableError(
                "selected generation model does not support chat"
            )
        if generation_model.status not in {"available", "installed"}:
            raise MaterialGenerationUnavailableError("selected generation model is not ready")
        if embedding_model is None or "embedding" not in embedding_model.capabilities:
            raise MaterialGenerationUnavailableError(
                "selected indexing model does not support embeddings"
            )
        generation_credentials = await self._models.get_credentials(
            generation_model.provider_connection_id
        )
        embedding_credentials = await self._models.get_credentials(
            embedding_model.provider_connection_id
        )
        if generation_credentials is None or embedding_credentials is None:
            raise MaterialGenerationUnavailableError("a selected model provider is unavailable")

        search_queries = [
            " ".join(part for part in (query, instructions or "") if part.strip())
            for query in definition.retrieval_queries
        ]
        retrieval_index_types = list(definition.required_indexes)
        if category == "documentation":
            documentation_run = next(
                (item for item in index_state.indexes if item.index_type == "documentation"), None
            )
            if (
                documentation_run is not None
                and documentation_run.status == "completed"
                and documentation_run.run_id is not None
            ):
                retrieval_index_types.append("documentation")
                selected_runs["documentation"] = documentation_run
        context = await self._retrieve_context(
            source_id,
            tuple(retrieval_index_types),
            selected_runs,
            search_queries,
            embedding_credentials,
            embedding_model.provider_model_id,
            include_local_documentation=category == "documentation",
        )
        if not context:
            raise MaterialGenerationUnavailableError(
                "the selected indexes contain no relevant searchable content"
            )
        missing_context = [
            index_type
            for index_type in definition.required_indexes
            if not any(chunk.index_type == index_type for chunk in context.values())
        ]
        if missing_context:
            raise MaterialGenerationUnavailableError(
                "no searchable chunks were found for required indexes: "
                + ", ".join(missing_context)
            )
        context_text, provided_context = _format_context(
            context, self._config.max_context_characters
        )
        missing_prompt_context = [
            index_type
            for index_type in definition.required_indexes
            if not any(chunk.index_type == index_type for chunk in provided_context.values())
        ]
        if missing_prompt_context:
            raise MaterialGenerationUnavailableError(
                "the context limit excluded required indexes: " + ", ".join(missing_prompt_context)
            )
        prompt = (
            f"Material category: {category}\n"
            f"User instructions: {instructions.strip() if instructions else 'Create a useful initial set.'}\n\n"
            "Use only facts supported by the sources. Cite the supplied source IDs in every file. "
            "Do not include source IDs that were not supplied.\n\n"
            f"Retrieved context:\n{context_text}"
        )
        if category == "documentation":
            synthesis = await self._synthesize_documentation(
                context_text,
                list(provided_context),
                generation_credentials,
                generation_model.provider_model_id,
            )
            prompt += (
                "\n\nEvidence synthesis (derived from the indexed code and existing files; "
                "use it to explain functionality, then verify every claim against the source "
                "fragments above):\n" + synthesis
            )
        raw = await asyncio.to_thread(
            self._gateway.generate_json,
            generation_credentials,
            generation_model.provider_model_id,
            definition.system_prompt,
            prompt,
            self._config.timeout_seconds,
            self._config.max_output_tokens,
        )
        try:
            draft = _parse_generated_draft(raw, list(provided_context))
        except (TypeError, ValueError, ValidationError):
            repair_system = (
                "Convert the supplied model response into valid JSON with this exact schema: "
                '{"files":[{"path":"relative/file.md","content":"text",'
                '"source_refs":["S1"]}]}. Keep the same useful content, cite only supplied '
                "source IDs, and return JSON only without Markdown fences."
            )
            repair_prompt = (
                f"Allowed source IDs: {', '.join(provided_context)}\n\n"
                f"Response to repair:\n{raw[: self._config.max_file_bytes]}"
            )
            repaired = await asyncio.to_thread(
                self._gateway.generate_json,
                generation_credentials,
                generation_model.provider_model_id,
                repair_system,
                repair_prompt,
                self._config.timeout_seconds,
                self._config.max_output_tokens,
            )
            try:
                draft = _parse_generated_draft(repaired, list(provided_context))
            except (TypeError, ValueError, ValidationError) as exc:
                raise MaterialGenerationResponseError(
                    "the model response could not be converted to the required file format; try again"
                ) from exc
        if len(draft.files) > self._config.max_files:
            raise MaterialGenerationUnavailableError("the model generated too many files")

        allowed_sources = provided_context
        output_files: dict[str, bytes] = {}
        content_types: dict[str, str] = {}
        provenance_by_path: dict[str, dict[str, Any]] = {}
        stored_resources = source.config.get("resources", {})
        category_entries = (
            stored_resources.get(category, []) if isinstance(stored_resources, dict) else []
        )
        if not isinstance(category_entries, list):
            category_entries = []
        used_paths = {
            str(item.get("path", item.get("name", ""))).casefold()
            for item in category_entries
            if isinstance(item, dict)
        }
        total_bytes = 0
        for generated in draft.files:
            try:
                path = normalize_documentation_path(generated.path)
            except DocumentationPathError as exc:
                raise MaterialGenerationUnavailableError(
                    "the model generated an unsafe file path"
                ) from exc
            if not path.casefold().endswith(definition.file_extension):
                raise MaterialGenerationUnavailableError(
                    f"generated files must use the {definition.file_extension} format"
                )
            path = _unique_generated_path(path, used_paths)
            normalized_key = path.casefold()
            if normalized_key in {item.casefold() for item in output_files}:
                raise MaterialGenerationUnavailableError("the model generated duplicate file paths")
            used_paths.add(normalized_key)
            if any(source_ref not in allowed_sources for source_ref in generated.source_refs):
                raise MaterialGenerationUnavailableError(
                    "the model cited a source that was not in the retrieved context"
                )
            references = [allowed_sources[source_ref] for source_ref in generated.source_refs]
            generated_content = generated.content
            if category == "user_flow":
                try:
                    generated_content = _normalize_user_flow_content(generated_content)
                except (TypeError, ValueError, ValidationError):
                    flow_repair = await asyncio.to_thread(
                        self._gateway.generate_json,
                        generation_credentials,
                        generation_model.provider_model_id,
                        "Repair the supplied User Flow content and return a JSON array only. "
                        "Each scenario must have title, actor, steps. Each step must have "
                        "action and expected_result. Optional fields: components, failure_modes, "
                        "checklist, doc_refs, provenance, approved. Lists contain strings, "
                        "provenance is an object, approved is false. Remove unknown fields. "
                        "Do not invent missing behavior; if a result is not present, derive a "
                        "conservative expected result from the described action. Preserve the "
                        "same workflows.",
                        f"Allowed source IDs: {', '.join(provided_context)}\n\n"
                        f"Invalid content:\n{generated_content[: self._config.max_file_bytes]}",
                        self._config.timeout_seconds,
                        self._config.max_output_tokens,
                    )
                    try:
                        generated_content = _normalize_user_flow_content(flow_repair)
                    except (TypeError, ValueError, ValidationError) as exc:
                        raise MaterialGenerationResponseError(
                            "the model returned an invalid User Flow scenario even after repair; try again"
                        ) from exc
            content = self._normalize_generated_content(
                category,
                path,
                generated_content,
                references,
                generated.source_refs,
                selected_runs,
                generation_model.id,
            )
            data = content.encode("utf-8")
            if len(data) > self._config.max_file_bytes:
                raise MaterialGenerationUnavailableError("a generated file exceeds the size limit")
            total_bytes += len(data)
            if total_bytes > self._config.max_total_bytes:
                raise MaterialGenerationUnavailableError(
                    "generated files exceed the total size limit"
                )
            output_files[path] = data
            content_types[path] = mimetypes.guess_type(path)[0] or "text/plain"
            provenance_by_path[path] = {
                "generator": "indexed-material-generator-v1",
                "model_id": generation_model.id,
                "index_runs": {key: value.run_id for key, value in selected_runs.items()},
                "generated_at": datetime.now(UTC).isoformat(),
                "source_refs": [
                    _reference_metadata(ref, allowed_sources[ref]) for ref in generated.source_refs
                ],
            }

        imported = await self._resources.import_documentation(
            source_id,
            output_files,
            content_types,
            category=category,
            origin="generated",
            provenance_by_path=provenance_by_path,
        )
        if imported["conflicts"]:
            raise MaterialGenerationConflictError(imported["conflicts"])
        updated_source = await self._sources.get_any(source_id)
        if updated_source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = updated_source.config.get("resources", {})
        entries = resources.get(category, []) if isinstance(resources, dict) else []
        paths = set(imported["added"] + imported["unchanged"])
        return [
            item
            for item in entries
            if isinstance(item, dict) and str(item.get("path", item.get("name", ""))) in paths
        ]

    async def _synthesize_documentation(
        self,
        context_text: str,
        source_ids: list[str],
        credentials: ProviderCredentials,
        model_id: str,
    ) -> str:
        system_prompt = (
            "Analyze the supplied indexed code fragments and existing local documentation. "
            "Write a concise but information-dense Russian functional synopsis: explain product "
            "capabilities, concrete user actions and outcomes, business rules and state changes, "
            "data read or written, calls between components, integrations, validation and errors. "
            "Avoid a directory-only summary. Do not guess; mark gaps as unknown. Return JSON only "
            'with shape {"summary":"...","source_refs":["S1"]}.'
        )
        user_prompt = (
            f"Available evidence IDs: {', '.join(source_ids)}\n\nEvidence:\n{context_text}"
        )
        raw = await asyncio.to_thread(
            self._gateway.generate_json,
            credentials,
            model_id,
            system_prompt,
            user_prompt,
            self._config.timeout_seconds,
            self._config.max_output_tokens,
        )
        try:
            synthesis = _parse_documentation_synthesis(raw)
        except (TypeError, ValueError, ValidationError):
            repaired = await asyncio.to_thread(
                self._gateway.generate_json,
                credentials,
                model_id,
                "Rewrite the supplied content as valid JSON with a Russian string field named "
                '"summary" (at least 80 characters) and a string-array field "source_refs". '
                "Preserve its facts, cite only the allowed IDs, and return JSON only.",
                f"Allowed IDs: {', '.join(source_ids)}\n\nContent:\n{raw[: self._config.max_file_bytes]}",
                self._config.timeout_seconds,
                self._config.max_output_tokens,
            )
            try:
                synthesis = _parse_documentation_synthesis(repaired)
            except (TypeError, ValueError, ValidationError) as exc:
                raise MaterialGenerationResponseError(
                    "the model could not synthesize documentation from the retrieved evidence"
                ) from exc
        valid_refs = [ref for ref in synthesis.source_refs if ref in source_ids]
        if not valid_refs:
            valid_refs = source_ids[: min(3, len(source_ids))]
        return synthesis.summary + "\nEvidence IDs used: " + ", ".join(valid_refs)

    async def _retrieve_context(
        self,
        source_id: int,
        index_types: tuple[str, ...],
        selected_runs: dict[str, Any],
        queries: list[str],
        embedding_credentials: ProviderCredentials,
        embedding_model_id: str,
        include_local_documentation: bool = False,
    ) -> dict[str, RetrievedChunk]:
        context: dict[str, RetrievedChunk] = {}
        limit = self._config.context_chunks
        vectors = await asyncio.to_thread(
            self._gateway.embed_queries,
            embedding_credentials,
            embedding_model_id,
            queries,
            self._config.timeout_seconds,
        )
        query_results: list[list[RetrievedChunk]] = []
        global_dense: list[RetrievedChunk] = []
        global_lexical: list[RetrievedChunk] = []
        for query, vector in zip(queries, vectors, strict=True):
            dense_results: list[RetrievedChunk] = []
            lexical_results: list[RetrievedChunk] = []
            for index_type in index_types:
                run = selected_runs[index_type]
                dense_results.extend(
                    await self._search.search_dense(
                        source_id, index_type, run.run_id, vector, limit
                    )
                )
                lexical_results.extend(
                    await self._search.search_lexical(
                        source_id, index_type, run.run_id, query, limit
                    )
                )
            global_dense.extend(dense_results)
            global_lexical.extend(lexical_results)
            query_results.append(_rrf(dense_results, lexical_results, limit))
        selected: list[RetrievedChunk] = []
        selected_ids: set[int] = set()
        per_query = max(1, limit // max(1, len(query_results)))
        for results in query_results:
            for chunk in results[:per_query]:
                if chunk.chunk_id not in selected_ids and len(selected) < limit:
                    selected.append(chunk)
                    selected_ids.add(chunk.chunk_id)
        for chunk in _rrf(global_dense, global_lexical, limit * 2):
            if chunk.chunk_id not in selected_ids and len(selected) < limit:
                selected.append(chunk)
                selected_ids.add(chunk.chunk_id)
        for chunk in selected:
            context[f"S{len(context) + 1}"] = chunk
        if include_local_documentation:
            documents = await self._resources.read_local_text_documents(source_id)
            local_chunks: list[RetrievedChunk] = []
            query_text = " ".join(queries)
            for path, content in documents:
                parsed = chunk_document_file(path=path, content=content)
                local_chunks.extend(
                    RetrievedChunk(
                        chunk_id=-(len(local_chunks) + 1),
                        index_type="documentation",
                        path=chunk.path,
                        branch="local",
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        symbol=None,
                        content=chunk.content,
                        metadata={**chunk.metadata, "section": chunk.section, "local": True},
                        score=_keyword_relevance(query_text, chunk.content),
                    )
                    for chunk in parsed.chunks
                )
            local_chunks.sort(key=lambda item: item.score, reverse=True)
            for chunk in local_chunks[:limit]:
                context[f"S{len(context) + 1}"] = chunk
        return context

    def _normalize_generated_content(
        self,
        category: str,
        path: str,
        content: str,
        references: list[RetrievedChunk],
        source_refs: list[str],
        selected_runs: dict[str, IndexRunStatus],
        model_id: int,
    ) -> str:
        if category == "documentation":
            source_lines = ["", "## Источники"]
            source_lines.extend(f"- `{item.path}`{_line_suffix(item)}" for item in references)
            return content.rstrip() + "\n" + "\n".join(source_lines) + "\n"
        try:
            normalized_content = _normalize_user_flow_content(content)
            raw_flows = json.loads(normalized_content)
            flows = [UserFlowDocument.model_validate(item) for item in raw_flows]
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise MaterialGenerationResponseError(
                "the model returned an invalid User Flow scenario; try again"
            ) from exc
        source_metadata = [
            _reference_metadata(source_id, chunk)
            for source_id, chunk in zip(source_refs, references, strict=True)
        ]
        provenance = {
            "generator": "indexed-material-generator-v1",
            "model_id": model_id,
            "index_runs": {key: value.run_id for key, value in selected_runs.items()},
            "generated_at": datetime.now(UTC).isoformat(),
            "source_refs": source_metadata,
        }
        normalized = [
            flow.model_copy(
                update={"approved": False, "provenance": {**flow.provenance, **provenance}}
            ).model_dump(mode="json")
            for flow in flows
        ]
        return json.dumps(normalized, ensure_ascii=False, indent=2)


def _rrf(
    dense: list[RetrievedChunk], lexical: list[RetrievedChunk], limit: int
) -> list[RetrievedChunk]:
    scores: dict[int, float] = {}
    chunks: dict[int, RetrievedChunk] = {}
    for results in (dense, lexical):
        for rank, chunk in enumerate(results, start=1):
            chunks[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (60 + rank)
    ranked = sorted(chunks.values(), key=lambda item: scores[item.chunk_id], reverse=True)
    return ranked[:limit]


def _format_context(
    chunks: dict[str, RetrievedChunk], max_characters: int
) -> tuple[str, dict[str, RetrievedChunk]]:
    sections: list[str] = []
    provided: dict[str, RetrievedChunk] = {}
    remaining = max_characters
    grouped: dict[str, list[tuple[str, RetrievedChunk]]] = {}
    for source_id, chunk in chunks.items():
        grouped.setdefault(chunk.index_type, []).append((source_id, chunk))
    while grouped and remaining > 0:
        for index_type in list(grouped):
            source_id, chunk = grouped[index_type].pop(0)
            if not grouped[index_type]:
                del grouped[index_type]
            locator = _line_suffix(chunk) or (f" · {chunk.symbol}" if chunk.symbol else "")
            header = f"[{source_id} {chunk.index_type} · {chunk.path}{locator}]\n"
            available = remaining - len(header)
            if available <= 0:
                return "\n\n".join(sections), provided
            content = chunk.content[:available]
            sections.append(header + content)
            provided[source_id] = chunk
            remaining -= len(header) + len(content) + 2
            if remaining <= 0:
                break
    return "\n\n".join(sections), provided


def _reference_metadata(source_id: str, chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "index_type": chunk.index_type,
        "path": chunk.path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "symbol": chunk.symbol,
        "section": chunk.metadata.get("section"),
    }


def _line_suffix(chunk: RetrievedChunk) -> str:
    if chunk.start_line is None:
        return ""
    if chunk.end_line is None or chunk.end_line == chunk.start_line:
        return f" · строка {chunk.start_line}"
    return f" · строки {chunk.start_line}–{chunk.end_line}"


def _keyword_relevance(query: str, content: str) -> float:
    terms = {word.casefold() for word in query.split() if len(word) > 2}
    words = {word.casefold() for word in content.split() if len(word) > 2}
    return len(terms & words) / max(1, len(terms))


def _unique_generated_path(path: str, used_paths: set[str]) -> str:
    if path.casefold() not in used_paths:
        return path
    parent, _, filename = path.rpartition("/")
    stem, dot, extension = filename.rpartition(".")
    if not dot:
        stem, extension = filename, ""
    suffix = f".{extension}" if extension else ""
    position = 1
    while True:
        generated_suffix = "-generated" if position == 1 else f"-generated-{position}"
        candidate_name = f"{stem}{generated_suffix}{suffix}"
        candidate = f"{parent}/{candidate_name}" if parent else candidate_name
        if candidate.casefold() not in used_paths:
            return candidate
        position += 1


def _parse_generated_draft(raw: str, source_ids: list[str]) -> GeneratedMaterialDraft:
    value = _extract_json_value(raw)
    if isinstance(value, list):
        raw_files = value
    elif isinstance(value, dict):
        raw_files = value.get("files")
        if raw_files is None and "path" in value:
            raw_files = [value]
    else:
        raise TypeError("model output has no file list")
    if not isinstance(raw_files, list):
        raise TypeError("model output has no file list")
    normalized_files: list[dict[str, Any]] = []
    for item in raw_files:
        if not isinstance(item, dict):
            raise TypeError("generated file must be an object")
        path = item.get("path", item.get("name", item.get("filename")))
        content = item.get("content", item.get("text", item.get("body")))
        refs = item.get("source_refs", item.get("sources", item.get("citations")))
        if isinstance(refs, str):
            refs = re.findall(r"S\d+", refs)
        if not isinstance(refs, list) or not refs:
            content_refs = re.findall(r"\bS\d+\b", content) if isinstance(content, str) else []
            refs = [ref for ref in content_refs if ref in source_ids]
        if not refs and source_ids:
            refs = [source_ids[0]]
        normalized_files.append({"path": path, "content": content, "source_refs": refs})
    return GeneratedMaterialDraft.model_validate({"files": normalized_files})


def _parse_documentation_synthesis(raw: str) -> DocumentationSynthesis:
    value = _extract_json_value(raw)
    if not isinstance(value, dict):
        raise TypeError("documentation synthesis must be a JSON object")
    return DocumentationSynthesis.model_validate(value)


def _extract_json_value(raw: str) -> Any:
    candidate = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.IGNORECASE | re.DOTALL)
    if fenced is not None:
        candidate = fenced.group(1)
    decoder = json.JSONDecoder()
    start_positions = [
        position for position in (candidate.find("{"), candidate.find("[")) if position >= 0
    ]
    if not start_positions:
        raise ValueError("model output does not contain JSON")
    value, _ = decoder.raw_decode(candidate[min(start_positions) :])
    return value


def _normalize_user_flow_content(content: str) -> str:
    value = _extract_json_value(content)
    if isinstance(value, dict):
        value = value.get("scenarios", value.get("flows", value.get("user_flows", [value])))
    if not isinstance(value, list) or not value:
        raise TypeError("User Flow content must contain a non-empty scenario array")
    normalized: list[dict[str, Any]] = []
    for scenario in value:
        if not isinstance(scenario, dict):
            raise TypeError("User Flow scenarios must be objects")
        raw_steps = scenario.get("steps", scenario.get("actions"))
        if not isinstance(raw_steps, list) or not raw_steps:
            raise TypeError("User Flow scenario must contain steps")
        steps: list[dict[str, str]] = []
        for step in raw_steps:
            if not isinstance(step, dict):
                raise TypeError("User Flow steps must be objects")
            action = step.get("action", step.get("user_action", step.get("description")))
            expected = step.get(
                "expected_result",
                step.get("expected", step.get("result", step.get("outcome"))),
            )
            if not isinstance(action, str) or not action.strip():
                raise TypeError("User Flow step is missing its action")
            if not isinstance(expected, str) or not expected.strip():
                raise TypeError("User Flow step is missing its expected result")
            steps.append({"action": action.strip(), "expected_result": expected.strip()})
        title = scenario.get("title", scenario.get("name", scenario.get("flow_name")))
        actor = scenario.get("actor", scenario.get("role", scenario.get("persona")))
        normalized.append(
            UserFlowDocument.model_validate(
                {
                    "title": (
                        title.strip()
                        if isinstance(title, str) and title.strip()
                        else "Сценарий пользователя"
                    ),
                    "actor": (
                        actor.strip()
                        if isinstance(actor, str) and actor.strip()
                        else "Пользователь"
                    ),
                    "steps": steps,
                    "components": _string_list(scenario.get("components", scenario.get("systems"))),
                    "failure_modes": _string_list(
                        scenario.get(
                            "failure_modes", scenario.get("errors", scenario.get("exceptions"))
                        )
                    ),
                    "checklist": _string_list(
                        scenario.get("checklist", scenario.get("preconditions"))
                    ),
                    "doc_refs": _string_list(
                        scenario.get("doc_refs", scenario.get("documentation_refs"))
                    ),
                    "provenance": (
                        scenario.get("provenance")
                        if isinstance(scenario.get("provenance"), dict)
                        else {}
                    ),
                    "approved": False,
                }
            ).model_dump(mode="json")
        )
    return json.dumps(normalized, ensure_ascii=False)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []
