from __future__ import annotations

from contextvars import ContextVar
from collections.abc import Callable, Iterator
from typing import Any, Optional
import re
import uuid

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import (
    AssistantFinalResponse,
    AssistantPriorityItem,
    AssistantStatus,
    AssistantToolCall,
    AssistantToolResult,
    ChatMessage,
    NeoAction,
    NeoTable,
    UserPublic,
)
from app.services.llm import LLMClient, LLMTextResponse
from app.services.assistant_tools import assistant_tool_functions, assistant_tool_specs
from pydantic import BaseModel, Field


LegacyEventFactory = Callable[[str, list[ChatMessage]], Iterator[dict[str, Any]]]
AssistantFallbackFactory = Callable[[str, str], LLMTextResponse]
_TOOL_EVENT_CAPTURE: ContextVar[Optional[list[dict[str, Any]]]] = ContextVar("assistant_tool_event_capture", default=None)
PLAIN_LIVE_ASSISTANTS = {"neo", "trinity"}
PLAIN_LIVE_MAX_TOKENS = 250


class AssistantRuntimeFailure(RuntimeError):
    pass


class AssistantRuntimeOutput(BaseModel):
    """Validated final assistant response."""

    markdown: str = Field(
        description=(
            "Formatter-safe Markdown answer shown to the user. "
            "Do not include JSON, prompt instructions, raw context rows, or schema field names."
        )
    )
    status: AssistantStatus = "completed"
    referenced_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional cited app records such as asset, alert, work_order, document, or user_interaction IDs.",
    )


def pydantic_ai_available() -> bool:
    try:
        import pydantic_ai  # noqa: F401
    except Exception:
        return False
    return True


def assistant_runtime_name() -> str:
    if get_settings().llm_provider == "mock":
        return "legacy"
    configured = (get_settings().assistant_runtime or "legacy").strip().lower()
    if configured in {"pydantic", "pydantic_ai", "pydantic-ai"}:
        return "pydantic_ai"
    return "legacy"


def stream_assistant_markdown(
    *,
    assistant_id: str,
    prompt: str,
    system_prompt: str,
    fallback_client: LLMClient,
    fallback_factory: AssistantFallbackFactory,
    max_tokens: int,
    timeout_seconds: Optional[float] = None,
    current_user: Optional[UserPublic] = None,
    history: Optional[list[ChatMessage]] = None,
) -> Iterator[LLMTextResponse]:
    if _uses_plain_live_text(assistant_id):
        yield from fallback_client.stream_text(
            prompt,
            system_prompt,
            fallback_factory,
            max_tokens=PLAIN_LIVE_MAX_TOKENS,
            timeout_seconds=timeout_seconds,
        )
        return
    if assistant_runtime_name() != "pydantic_ai":
        yield from fallback_client.stream_text(
            prompt,
            system_prompt,
            fallback_factory,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        return

    try:
        output = _run_pydantic_ai_output(
            assistant_id=assistant_id,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            current_user=current_user,
            history=history or [],
        )
    except AssistantRuntimeFailure as exc:
        yield _structured_runtime_failure(fallback_factory, "pydantic_ai", str(exc))
        return
    except Exception as exc:
        yield _structured_runtime_failure(fallback_factory, "pydantic_ai", f"Pydantic AI assistant runtime failed: {exc}")
        return

    if not output.markdown.strip():
        yield _structured_runtime_failure(fallback_factory, "pydantic_ai", "Pydantic AI assistant runtime returned no content")
        return
    for chunk in _chunk_markdown(output.markdown):
        yield LLMTextResponse(
            content=chunk,
            used_live_provider=True,
            provider="pydantic_ai",
            runtime="pydantic_ai",
            referenced_records=output.referenced_records,
        )


def complete_assistant_markdown(
    *,
    assistant_id: str,
    prompt: str,
    system_prompt: str,
    fallback_client: LLMClient,
    fallback_factory: AssistantFallbackFactory,
    max_tokens: int,
    current_user: Optional[UserPublic] = None,
    history: Optional[list[ChatMessage]] = None,
) -> LLMTextResponse:
    if _uses_plain_live_text(assistant_id):
        return fallback_client.complete_text(
            prompt,
            system_prompt,
            fallback_factory,
            max_tokens=PLAIN_LIVE_MAX_TOKENS,
        )
    if assistant_runtime_name() != "pydantic_ai":
        return fallback_client.complete_text(prompt, system_prompt, fallback_factory, max_tokens=max_tokens)
    try:
        output = _run_pydantic_ai_output(
            assistant_id=assistant_id,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            current_user=current_user,
            history=history or [],
        )
    except AssistantRuntimeFailure as exc:
        return _structured_runtime_failure(fallback_factory, "pydantic_ai", str(exc))
    except Exception as exc:
        return _structured_runtime_failure(fallback_factory, "pydantic_ai", f"Pydantic AI assistant runtime failed: {exc}")
    if not output.markdown.strip():
        return _structured_runtime_failure(fallback_factory, "pydantic_ai", "Pydantic AI assistant runtime returned no content")
    return LLMTextResponse(
        content=output.markdown,
        used_live_provider=True,
        provider="pydantic_ai",
        runtime="pydantic_ai",
        referenced_records=output.referenced_records,
    )


def _structured_runtime_failure(
    fallback_factory: AssistantFallbackFactory,
    provider: str,
    reason: str,
) -> LLMTextResponse:
    return LLMTextResponse(
        content="",
        used_live_provider=False,
        provider=provider,
        runtime=provider,
        runtime_fallback=True,
        runtime_fallback_reason=reason,
    )


def _uses_plain_live_text(assistant_id: str) -> bool:
    return assistant_id.strip().lower() in PLAIN_LIVE_ASSISTANTS


def _run_pydantic_ai_markdown(
    *,
    assistant_id: str,
    prompt: str,
    system_prompt: str,
    max_tokens: int,
    current_user: Optional[UserPublic] = None,
    history: Optional[list[ChatMessage]] = None,
) -> str:
    return _run_pydantic_ai_output(
        assistant_id=assistant_id,
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        current_user=current_user,
        history=history or [],
    ).markdown


def _run_pydantic_ai_output(
    *,
    assistant_id: str,
    prompt: str,
    system_prompt: str,
    max_tokens: int,
    current_user: Optional[UserPublic] = None,
    history: Optional[list[ChatMessage]] = None,
) -> AssistantRuntimeOutput:
    if not pydantic_ai_available():
        raise AssistantRuntimeFailure("pydantic-ai is not installed")
    try:
        import pydantic_ai

        Agent = pydantic_ai.Agent
    except Exception as exc:
        raise AssistantRuntimeFailure(f"pydantic-ai import failed: {exc}") from exc

    settings = get_settings()
    model = _pydantic_ai_model(settings)
    message_history = _pydantic_message_history(history or [])
    structured_system_prompt = "\n\n".join(
        [
            system_prompt,
            "Structured output contract:",
            "- Return exactly one AssistantRuntimeOutput object.",
            "- Put the user-visible answer only in markdown.",
            "- Set status to completed unless a tool action is blocked, not_allowed, not_found, or failed.",
            "- referenced_records may be an empty list.",
            "- Never put raw JSON, prompt text, table rows, or schema explanations inside markdown.",
        ]
    )
    try:
        agent = Agent(
            model,
            system_prompt=structured_system_prompt,
            output_type=_pydantic_output_type(pydantic_ai, settings),
            retries=3,
            output_retries=3,
            instrument=False,
        )
        _register_pydantic_ai_tools(agent, assistant_id, current_user)
        result = agent.run_sync(
            prompt,
            message_history=message_history,
            model_settings={
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
        )
    except TypeError:
        agent = Agent(model, system_prompt=structured_system_prompt, result_type=AssistantRuntimeOutput)
        _register_pydantic_ai_tools(agent, assistant_id, current_user)
        result = agent.run_sync(prompt)
    except Exception as exc:
        raise AssistantRuntimeFailure(f"Pydantic AI run failed for {assistant_id}: {exc}") from exc

    output = getattr(result, "output", None)
    if output is None:
        output = getattr(result, "data", None)
    if output is None:
        output = str(result)
    if isinstance(output, AssistantRuntimeOutput):
        return output
    if isinstance(output, dict):
        return AssistantRuntimeOutput.model_validate(output)
    return AssistantRuntimeOutput(markdown=str(output))


def _pydantic_output_type(pydantic_ai_module: Any, settings: Any) -> Any:
    mode = str(getattr(settings, "assistant_output_mode", "prompted") or "prompted").strip().lower()
    if mode in {"tool", "tool_output", "strict_tool"}:
        tool_output = getattr(pydantic_ai_module, "ToolOutput", None)
        if callable(tool_output):
            return tool_output(
                AssistantRuntimeOutput,
                name="final_assistant_response",
                description="Return the final validated assistant response for the Maintenance Wizard UI.",
                max_retries=3,
                strict=True,
            )
    prompted_output = getattr(pydantic_ai_module, "PromptedOutput", None)
    if callable(prompted_output):
        return prompted_output(
            AssistantRuntimeOutput,
            name="AssistantRuntimeOutput",
            description="Return only the validated final assistant response.",
        )
    return AssistantRuntimeOutput


def _pydantic_message_history(history: list[ChatMessage]) -> list[Any]:
    if not history:
        return []
    try:
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    except Exception:
        return []
    messages: list[Any] = []
    for item in history[-get_settings().assistant_history_limit :]:
        content = item.content.strip()
        if not assistant_history_content_is_contextual(content):
            continue
        if item.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif item.role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages


def assistant_history_content_is_contextual(content: str) -> bool:
    normalized = re.sub(r"\s+", " ", content or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    non_context_markers = [
        "could not get a live llm response",
        "please retry after confirming the llm service is responding",
        "stream failed:",
        "llm fallback",
        "fallback:",
        "pydantic ai assistant runtime failed",
        "pydantic ai assistant runtime returned no content",
    ]
    return not any(marker in lowered for marker in non_context_markers)


def _pydantic_ai_model(settings: Any) -> Any:
    if settings.llm_provider == "openai":
        try:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
        except Exception:
            return settings.openai_model
        return OpenAIChatModel(
            settings.openai_model,
            provider=OpenAIProvider(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key or "maintenance-wizard-local",
            ),
        )
    return settings.ollama_model


def _chunk_markdown(markdown: str, chunk_size: int = 220) -> Iterator[str]:
    current = ""
    for part in re_split_markdown(markdown):
        if len(current) + len(part) > chunk_size and current:
            yield current
            current = part
        else:
            current += part
    if current:
        yield current


def re_split_markdown(markdown: str) -> list[str]:
    import re

    return [part for part in re.split(r"(\n\n|\n)", markdown) if part]


def _register_pydantic_ai_tools(agent: Any, assistant_id: str, current_user: Optional[UserPublic]) -> None:
    register = getattr(agent, "tool_plain", None)
    if not callable(register):
        return
    for name, tool_function in assistant_tool_functions(assistant_id, current_user=current_user).items():
        register(_named_tool_wrapper(assistant_id, name, tool_function))


def _named_tool_wrapper(assistant_id: str, name: str, tool_function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def tool(**kwargs: Any) -> dict[str, Any]:
        description = next(
            (spec.description for spec in assistant_tool_specs(assistant_id) if spec.name == name),
            f"Run assistant tool {name}.",
        )
        call = AssistantToolCall(
            id=f"ATC-{uuid.uuid4().hex[:10].upper()}",
            name=name,
            arguments=kwargs,
            assistant_id=assistant_id,
            description=description,
        )
        _capture_tool_event({"type": "tool_call", "tool_call": call.model_dump(mode="json")})
        try:
            result_payload = tool_function(**kwargs)
        except Exception as exc:
            result = AssistantToolResult(
                tool_call_id=call.id,
                name=name,
                status="failed",
                content={"error": str(exc)},
                artifact_type="assistant_tool",
            )
            _capture_tool_event({"type": "tool_result", "tool_result": result.model_dump(mode="json")})
            raise
        result = AssistantToolResult(
            tool_call_id=call.id,
            name=name,
            status=_tool_status(str(result_payload.get("status") or "completed")),
            content=result_payload,
            artifact_type="assistant_tool",
        )
        _capture_tool_event({"type": "tool_result", "tool_result": result.model_dump(mode="json")})
        return result_payload

    tool.__name__ = name
    tool.__doc__ = next(
        (spec.description for spec in assistant_tool_specs(assistant_id) if spec.name == name),
        f"Run assistant tool {name}.",
    )
    return tool


def _capture_tool_event(event: dict[str, Any]) -> None:
    capture = _TOOL_EVENT_CAPTURE.get()
    if capture is not None:
        capture.append(event)


def ensure_assistant_session(
    *,
    assistant_id: str,
    current_user: UserPublic,
    screen: str,
    session_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    existing = repository.get_assistant_session(session_id) if session_id else None
    if (
        existing
        and existing.get("assistant_id") == assistant_id
        and str(existing.get("user_id") or "") == str(current_user.id)
    ):
        return repository.upsert_assistant_session(
            {
                **existing,
                "assistant_id": assistant_id,
                "user_id": current_user.id,
                "user_role": current_user.role,
                "screen": screen,
                "status": "active",
                "metadata": {**(existing.get("metadata") or {}), **(metadata or {})},
            }
        )
    return repository.upsert_assistant_session(
        {
            "id": None if existing else session_id,
            "assistant_id": assistant_id,
            "user_id": current_user.id,
            "user_role": current_user.role,
            "screen": screen,
            "status": "active",
            "metadata": metadata or {},
        }
    )


def session_chat_history(session_id: str, limit: Optional[int] = None) -> list[ChatMessage]:
    history_limit = get_settings().assistant_history_limit if limit is None else limit
    if history_limit <= 0:
        return []
    messages = repository.list_assistant_messages(session_id, limit=history_limit)
    history: list[ChatMessage] = []
    for message in messages:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "").strip()
        if assistant_history_content_is_contextual(content):
            history.append(ChatMessage(role=role, content=content))
    return history


def standardized_assistant_stream(
    *,
    assistant_id: str,
    screen: str,
    current_user: UserPublic,
    session_id: Optional[str],
    user_content: str,
    legacy_events: LegacyEventFactory,
    request_metadata: Optional[dict[str, Any]] = None,
) -> Iterator[dict[str, Any]]:
    tool_specs = [spec.model_dump(mode="json") for spec in assistant_tool_specs(assistant_id)]
    session = ensure_assistant_session(
        assistant_id=assistant_id,
        current_user=current_user,
        screen=screen,
        session_id=session_id,
        metadata={**(request_metadata or {}), "tool_specs": tool_specs},
    )
    persisted_history = session_chat_history(session["id"])
    runtime_name = assistant_runtime_name()
    repository.save_assistant_message(
        {
            "session_id": session["id"],
            "assistant_id": assistant_id,
            "role": "user",
            "content": user_content,
            "metadata": request_metadata or {},
        }
    )
    yield {
        "type": "session",
        "session_id": session["id"],
        "assistant_id": assistant_id,
        "screen": screen,
        "runtime": runtime_name,
        "tools": tool_specs,
    }

    provider = "mock"
    used_live_provider = False
    runtime_fallback = False
    runtime_fallback_reason: Optional[str] = None
    token_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    final_response: Optional[AssistantFinalResponse] = None
    captured_runtime_tool_events: list[dict[str, Any]] = []
    capture_token = _TOOL_EVENT_CAPTURE.set(captured_runtime_tool_events)

    try:
        for event in legacy_events(session["id"], persisted_history):
            event_type = event.get("type")
            if event_type == "meta":
                provider = str(event.get("provider") or provider)
                used_live_provider = bool(event.get("used_live_provider"))
                runtime_fallback = bool(event.get("runtime_fallback", runtime_fallback))
                runtime_fallback_reason = str(event.get("runtime_fallback_reason") or runtime_fallback_reason or "") or None
                event = {**event, "runtime": runtime_name}
            elif event_type == "token":
                token_parts.append(str(event.get("content") or ""))
            elif event_type == "error":
                message = str(event.get("message") or f"{assistant_id} stream failed")
                repository.save_assistant_message(
                    {
                        "session_id": session["id"],
                        "assistant_id": assistant_id,
                        "role": "assistant",
                        "content": message,
                        "provider": provider,
                        "used_live_provider": False,
                        "metadata": {
                            "runtime": runtime_name,
                            "runtime_fallback": True,
                            "runtime_fallback_reason": message,
                        },
                    }
                )
                yield event
                return
            elif event_type == "done":
                response_payload = event.get("response") or {}
                for tool_event in captured_runtime_tool_events:
                    if tool_event["type"] == "tool_call":
                        tool_calls.append(tool_event["tool_call"])
                    if tool_event["type"] == "tool_result":
                        tool_results.append(tool_event["tool_result"])
                    yield tool_event
                for tool_event in _context_tool_events(assistant_id, response_payload):
                    if tool_event["type"] == "tool_call":
                        tool_calls.append(tool_event["tool_call"])
                    if tool_event["type"] == "tool_result":
                        tool_results.append(tool_event["tool_result"])
                    yield tool_event
                final_response = _final_response_from_legacy(
                    assistant_id=assistant_id,
                    session_id=session["id"],
                    response=response_payload,
                    provider=provider,
                    used_live_provider=used_live_provider,
                    runtime=runtime_name,
                    runtime_fallback=runtime_fallback,
                    runtime_fallback_reason=runtime_fallback_reason,
                    fallback_markdown="".join(token_parts),
                )
                yield {"type": "final", "response": final_response.model_dump(mode="json")}
            yield event
    except Exception as exc:
        repository.save_assistant_message(
            {
                "session_id": session["id"],
                "assistant_id": assistant_id,
                "role": "assistant",
                "content": f"{assistant_id} stream failed: {exc}",
                "provider": provider,
                "used_live_provider": False,
                "metadata": {"error": str(exc)},
            }
        )
        yield {"type": "error", "message": f"{assistant_id} stream failed: {exc}"}
        return
    finally:
        try:
            _TOOL_EVENT_CAPTURE.reset(capture_token)
        except ValueError:
            _TOOL_EVENT_CAPTURE.set(None)

    assistant_text = final_response.markdown if final_response else "".join(token_parts).strip()
    repository.save_assistant_message(
        {
            "session_id": session["id"],
            "assistant_id": assistant_id,
            "role": "assistant",
            "content": assistant_text,
            "provider": provider,
            "used_live_provider": used_live_provider,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "final_response": final_response.model_dump(mode="json") if final_response else None,
            "metadata": {
                "runtime": get_settings().assistant_runtime,
                "runtime_fallback": runtime_fallback,
                "runtime_fallback_reason": runtime_fallback_reason,
            },
        }
    )


def _context_tool_events(assistant_id: str, response: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    action = response.get("action")
    if isinstance(action, dict):
        events.extend(
            _tool_event_pair(
                assistant_id=assistant_id,
                name=_tool_name_for_action(action),
                arguments={
                    "action_type": action.get("type"),
                    "target_id": action.get("target_id"),
                    "status": action.get("status"),
                },
                status=str(action.get("status") or "completed"),
                content={"action": action},
                artifact_type="assistant_action",
                description=str(action.get("label") or action.get("type") or "Assistant action"),
            )
        )
    table = response.get("table")
    if isinstance(table, dict):
        events.extend(
            _tool_event_pair(
                assistant_id=assistant_id,
                name=_tool_name_for_table(table),
                arguments={
                    "title": table.get("title"),
                    "columns": table.get("columns") or [],
                    "row_count": len(table.get("rows") or []),
                },
                status="completed",
                content={"table": table},
                artifact_type="assistant_table",
                description=f"Loaded {table.get('title') or 'table'} context",
            )
        )
    evidence = response.get("evidence")
    if evidence:
        events.extend(
            _tool_event_pair(
                assistant_id=assistant_id,
                name="load_evidence_context",
                arguments={"count": len(evidence) if isinstance(evidence, list) else 1},
                status="completed",
                content={"evidence": evidence},
                artifact_type="retrieval_evidence",
                description="Loaded retrieved maintenance evidence",
            )
        )
    return events


def _tool_event_pair(
    *,
    assistant_id: str,
    name: str,
    arguments: dict[str, Any],
    status: str,
    content: dict[str, Any],
    artifact_type: str,
    description: str,
) -> list[dict[str, Any]]:
    call = AssistantToolCall(
        id=f"ATC-{uuid.uuid4().hex[:10].upper()}",
        name=name,
        arguments=arguments,
        assistant_id=assistant_id,
        description=description,
    )
    result = AssistantToolResult(
        tool_call_id=call.id,
        name=call.name,
        status=_tool_status(status),
        content=content,
        artifact_type=artifact_type,
    )
    return [
        {"type": "tool_call", "tool_call": call.model_dump(mode="json")},
        {"type": "tool_result", "tool_result": result.model_dump(mode="json")},
    ]


def _tool_name_for_action(action: dict[str, Any]) -> str:
    action_type = str(action.get("type") or "").strip()
    allowed = {
        "add_work_order_log",
        "asset_decision_guidance",
        "assign_work_order",
        "close_rca_case",
        "convert_pm_plan",
        "create_rca_case",
        "create_work_order",
        "dispatch_work_order",
        "learning_review",
        "manage_rca_case",
        "manage_user",
        "plan_work_order",
        "session_context_lookup",
        "show_alerts",
        "show_asset_risk",
        "update_work_order_material",
        "update_work_order_status",
        "work_order_material_status",
        "work_order_next_steps",
    }
    return action_type if action_type in allowed else "assistant_action"


def _tool_name_for_table(table: dict[str, Any]) -> str:
    title = str(table.get("title") or "").lower()
    if "work" in title:
        return "load_work_order_context"
    if "asset" in title or "equipment" in title:
        return "load_asset_context"
    if "user" in title:
        return "load_user_context"
    if "alert" in title:
        return "load_alert_context"
    return "load_structured_context"


def _tool_status(status: str) -> AssistantStatus:
    if status in {"completed", "blocked", "not_allowed", "not_found", "failed"}:
        return status  # type: ignore[return-value]
    return "completed"


def _final_response_from_legacy(
    *,
    assistant_id: str,
    session_id: str,
    response: dict[str, Any],
    provider: str,
    used_live_provider: bool,
    runtime: str,
    runtime_fallback: bool,
    runtime_fallback_reason: Optional[str],
    fallback_markdown: str,
) -> AssistantFinalResponse:
    markdown = _legacy_markdown(response, fallback_markdown)
    final = AssistantFinalResponse(
        assistant_id=assistant_id,
        session_id=session_id,
        markdown=_formatter_safe_markdown(markdown),
        status=_legacy_status(response),
        priorities=_priorities_from_table(response.get("table")),
        action=NeoAction.model_validate(response["action"]) if response.get("action") else None,
        table=NeoTable.model_validate(response["table"]) if response.get("table") else None,
        referenced_records=_referenced_records(response),
        provider=str(response.get("provider") or provider),
        used_live_provider=bool(response.get("used_live_provider", used_live_provider)),
        runtime=runtime,
        runtime_fallback=runtime_fallback,
        runtime_fallback_reason=runtime_fallback_reason,
    )
    return AssistantFinalResponse.model_validate(final.model_dump(mode="json"))


def _legacy_markdown(response: dict[str, Any], fallback_markdown: str) -> str:
    for key in ("answer", "next_prompt", "summary", "message"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback_markdown.strip()


def _legacy_status(response: dict[str, Any]) -> str:
    action = response.get("action") if isinstance(response, dict) else None
    if isinstance(action, dict) and action.get("status"):
        return str(action["status"])
    return "completed"


def _priorities_from_table(table: Any) -> list[AssistantPriorityItem]:
    if not isinstance(table, dict):
        return []
    rows = table.get("rows")
    if not isinstance(rows, list):
        return []
    priorities: list[AssistantPriorityItem] = []
    for row in rows[:10]:
        if not isinstance(row, dict):
            continue
        priority = str(row.get("Priority") or row.get("priority") or "P3")
        title = str(row.get("Focus") or row.get("Work order") or row.get("Asset") or row.get("title") or "Priority")
        priorities.append(
            AssistantPriorityItem(
                priority=priority,
                title=title,
                impact=str(row.get("Plant impact") or row.get("Impact") or row.get("Status") or ""),
                signal=str(row.get("Signal") or row.get("Description") or row.get("Asset") or ""),
                recommendation=str(row.get("Recommendation") or row.get("Next action") or ""),
                referenced_ids=[
                    str(value)
                    for key, value in row.items()
                    if key.lower() in {"asset", "work order", "id"} and value is not None
                ],
            )
        )
    return priorities


def _referenced_records(response: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    table = response.get("table")
    if isinstance(table, dict):
        records.append({"source_type": "assistant_table", "source_id": table.get("title"), "rows": len(table.get("rows") or [])})
    action = response.get("action")
    if isinstance(action, dict):
        records.append({"source_type": "assistant_action", "source_id": action.get("type"), "status": action.get("status")})
    return records


def _formatter_safe_markdown(markdown: str) -> str:
    cleaned = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    leaked_sections = (
        "Answer requirements:",
        "Grounded app response:",
        "Action context:",
        "Relevant work-order context:",
        "Rows:",
        "Columns:",
    )
    if any(section.lower() in cleaned.lower() for section in leaked_sections):
        cleaned = "The assistant produced internal context instead of a user-ready response. Please retry the live model request."
    return cleaned
