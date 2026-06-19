from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.data import repository
from app.models.schemas import Evidence
from app.services.notifications import notify_work_order_changed, notify_work_order_created
from app.services.retrieval import retrieve_evidence

WORK_ORDER_ACTION_ROLES = {
    "admin",
    "maintenance_engineer",
    "maintenance_technician",
    "maintenance_supervisor",
    "reliability_engineer",
    "planner",
}
WORK_ORDER_APPROVAL_ROLES = {"admin", "maintenance_supervisor"}
WORK_ORDER_MATERIAL_UPDATE_ROLES = {"admin", "maintenance_supervisor", "maintenance_engineer", "reliability_engineer", "planner"}
WORK_ORDER_ASSIGNMENT_ROLES = {"admin", "maintenance_supervisor", "planner"}
WORK_ORDER_STATUS_LABELS = {
    "WAPPR": "Waiting for approval",
    "APPR": "Approved",
    "WMATL": "Waiting for material",
    "INPRG": "In progress",
    "COMP": "Completed",
    "CLOSE": "Closed",
}
RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
IST = timezone(timedelta(hours=5, minutes=30))


class AssistantToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


ToolFunction = Callable[..., dict[str, Any]]


def assistant_tool_specs(assistant_id: str) -> list[AssistantToolSpec]:
    common = [
        AssistantToolSpec(
            name="load_asset_context",
            description="Load current equipment, active alert, spare, sensor, and work-order context for one asset.",
            input_schema={
                "type": "object",
                "properties": {
                    "equipment_id": {"type": "string"},
                },
                "required": ["equipment_id"],
            },
        ),
        AssistantToolSpec(
            name="load_work_order_context",
            description="Load current work-order status, material readiness, spares, logs, and linked asset context.",
            input_schema={
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "string"},
                },
                "required": ["work_order_id"],
            },
        ),
        AssistantToolSpec(
            name="load_evidence_context",
            description="Retrieve grounded RAG evidence from documents, learning examples, and indexed plant records.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "equipment_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "required": ["query"],
            },
        ),
    ]
    if assistant_id == "neo":
        return [
            *common,
            AssistantToolSpec(
                name="load_plant_priority_context",
                description="Load current plant risk, critical assets, urgent work, material blockers, and production exposure.",
                input_schema={"type": "object", "properties": {}},
            ),
            *_work_order_action_tool_specs(),
        ]
    if assistant_id == "trinity":
        return [
            *common,
            *_work_order_action_tool_specs(),
            AssistantToolSpec(
                name="add_work_order_log",
                description="Role-checked action to add a technician, supervisor, or assistant note to a work order log.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "work_order_id": {"type": "string"},
                        "content": {"type": "string"},
                        "entry_type": {"type": "string"},
                    },
                    "required": ["work_order_id", "content"],
                },
                read_only=False,
            ),
        ]
    return common


def _work_order_action_tool_specs() -> list[AssistantToolSpec]:
    return [
        AssistantToolSpec(
            name="update_work_order_status",
            description="Role-checked action to approve, start, complete, or otherwise update a work order status.",
            input_schema={
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "string"},
                    "target_status": {"type": "string", "enum": ["WAPPR", "APPR", "WMATL", "INPRG", "COMP", "CLOSE"]},
                },
                "required": ["work_order_id", "target_status"],
            },
            read_only=False,
        ),
        AssistantToolSpec(
            name="update_work_order_material_ready",
            description="Role-checked action to clear material blockers and mark a work order's materials ready.",
            input_schema={
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "string"},
                },
                "required": ["work_order_id"],
            },
            read_only=False,
        ),
        AssistantToolSpec(
            name="assign_work_order",
            description="Role-checked action to assign or reassign a work order to an active application user by display name or email.",
            input_schema={
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "string"},
                    "assignee": {"type": "string"},
                },
                "required": ["work_order_id", "assignee"],
            },
            read_only=False,
        ),
        AssistantToolSpec(
            name="create_work_order",
            description="Role-checked action to create a corrective work order for an asset, optionally assigned to an active application user by display name or email.",
            input_schema={
                "type": "object",
                "properties": {
                    "equipment_id": {"type": "string"},
                    "assignee": {"type": "string"},
                    "title": {"type": "string"},
                    "recommended_action": {"type": "string"},
                },
                "required": ["equipment_id"],
            },
            read_only=False,
        ),
    ]


def assistant_tool_functions(assistant_id: str, current_user: Optional[Any] = None) -> dict[str, ToolFunction]:
    tools: dict[str, ToolFunction] = {
        "load_asset_context": load_asset_context,
        "load_work_order_context": load_work_order_context,
        "load_evidence_context": load_evidence_context,
    }
    if assistant_id == "neo":
        tools["load_plant_priority_context"] = load_plant_priority_context
    if assistant_id in {"neo", "trinity"}:
        tools["update_work_order_status"] = lambda work_order_id, target_status: update_work_order_status(
            work_order_id,
            target_status,
            current_user=current_user,
        )
        tools["update_work_order_material_ready"] = lambda work_order_id: update_work_order_material_ready(
            work_order_id,
            current_user=current_user,
        )
        tools["assign_work_order"] = lambda work_order_id, assignee: assign_work_order(
            work_order_id,
            assignee,
            current_user=current_user,
        )
        tools["create_work_order"] = lambda equipment_id, assignee=None, title=None, recommended_action=None: create_work_order(
            equipment_id,
            assignee=assignee,
            title=title,
            recommended_action=recommended_action,
            current_user=current_user,
        )
    if assistant_id == "trinity":
        tools["add_work_order_log"] = lambda work_order_id, content, entry_type="assistant_tool": add_work_order_log(
            work_order_id,
            content=content,
            entry_type=entry_type,
            current_user=current_user,
        )
    return tools


def load_asset_context(equipment_id: str) -> dict[str, Any]:
    equipment = repository.get_equipment(equipment_id)
    if not equipment:
        return {"status": "not_found", "equipment_id": equipment_id}
    alerts = repository.list_alerts(equipment_id)
    spares = repository.list_spares(equipment_id)
    readings = repository.list_sensor_readings(equipment_id)
    work_orders = repository.list_work_orders(equipment_id=equipment_id)
    pm_plans = repository.list_pm_plans(equipment_id=equipment_id, limit=20)
    return {
        "status": "completed",
        "equipment": equipment,
        "alerts": alerts[:8],
        "spares": spares[:8],
        "sensor_readings": readings[:12],
        "work_orders": work_orders[:8],
        "pm_plans": pm_plans,
    }


def load_work_order_context(work_order_id: str) -> dict[str, Any]:
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        return {"status": "not_found", "work_order_id": work_order_id}
    equipment = repository.get_equipment(work_order["equipment_id"])
    spares = repository.list_spares(work_order["equipment_id"])
    alerts = repository.list_alerts(work_order["equipment_id"])
    return {
        "status": "completed",
        "work_order": work_order,
        "equipment": equipment,
        "spares": spares[:8],
        "alerts": alerts[:8],
    }


def load_evidence_context(query: str, equipment_id: Optional[str] = None, limit: int = 4) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 8))
    evidence = retrieve_evidence(query, equipment_id=equipment_id, limit=bounded_limit, use_reranker=False)
    return {
        "status": "completed",
        "query": query,
        "equipment_id": equipment_id,
        "evidence": [_evidence_payload(item) for item in evidence],
    }


def load_plant_priority_context() -> dict[str, Any]:
    equipment = repository.list_equipment()
    alerts = repository.list_alerts()
    work_orders = repository.list_work_orders()
    open_orders = [item for item in work_orders if item["status"] not in {"COMP", "CLOSE"}]
    priority_assets = sorted(
        equipment,
        key=lambda item: (int(item.get("criticality") or 0), item.get("status") in {"degraded", "watch"}),
        reverse=True,
    )
    material_blockers = [
        item
        for item in open_orders
        if item.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
    ]
    return {
        "status": "completed",
        "assets_at_risk": priority_assets[:8],
        "active_alerts": alerts[:12],
        "urgent_work_orders": [item for item in open_orders if item["priority"] == 1][:8],
        "material_blockers": material_blockers[:8],
        "pm_exposure": [item for item in open_orders if item["work_type"] == "PM" or item["status"] in {"WAPPR", "WMATL"}][:8],
    }


def update_work_order_status(work_order_id: str, target_status: str, current_user: Optional[Any] = None) -> dict[str, Any]:
    user = _user_context(current_user)
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        return {"status": "not_found", "work_order_id": work_order_id, "detail": "Work order not found."}
    normalized_status = target_status.strip().upper()
    allowed, reason = _can_update_work_order_status(work_order, normalized_status, user)
    if not allowed:
        return {
            "status": "not_allowed",
            "work_order_id": work_order_id,
            "target_status": normalized_status,
            "detail": reason,
        }
    updated = repository.update_work_order(work_order_id, {"status": normalized_status})
    if updated:
        notify_work_order_changed(work_order, updated, current_user)
    return {
        "status": "completed",
        "action_type": "update_work_order_status",
        "work_order_id": work_order_id,
        "from_status": work_order["status"],
        "to_status": normalized_status,
        "detail": f"Status moved to {WORK_ORDER_STATUS_LABELS.get(normalized_status, normalized_status)}.",
        "work_order": updated,
    }


def update_work_order_material_ready(work_order_id: str, current_user: Optional[Any] = None) -> dict[str, Any]:
    user = _user_context(current_user)
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        return {"status": "not_found", "work_order_id": work_order_id, "detail": "Work order not found."}
    if user["role"] not in WORK_ORDER_MATERIAL_UPDATE_ROLES:
        return {
            "status": "not_allowed",
            "work_order_id": work_order_id,
            "detail": f"Role {user['role']} cannot clear material blockers.",
        }
    payload: dict[str, Any] = {
        "material_readiness": "ready",
        "material_blocker_status": "reserved",
        "material_blocker_note": None,
        "spare_reservations": [_resolved_spare_reservation(item) for item in work_order.get("spare_reservations", [])],
    }
    if work_order["status"] == "WMATL":
        payload["status"] = "APPR"
    updated = repository.update_work_order(work_order_id, payload)
    if updated:
        notify_work_order_changed(work_order, updated, current_user)
    return {
        "status": "completed",
        "action_type": "update_work_order_material_ready",
        "work_order_id": work_order_id,
        "detail": "Material readiness is ready and blockers are cleared.",
        "work_order": updated,
    }


def assign_work_order(work_order_id: str, assignee: str, current_user: Optional[Any] = None) -> dict[str, Any]:
    user = _user_context(current_user)
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        return {"status": "not_found", "work_order_id": work_order_id, "detail": "Work order not found."}
    if user["role"] not in WORK_ORDER_ASSIGNMENT_ROLES:
        return {
            "status": "not_allowed",
            "work_order_id": work_order_id,
            "detail": f"Role {user['role']} cannot assign work orders.",
        }
    clean_assignee = assignee.strip()
    if not clean_assignee:
        return {"status": "blocked", "work_order_id": work_order_id, "detail": "Assignee is required."}
    assignee_user = _active_user_for_assignee(clean_assignee)
    if not assignee_user:
        return _unknown_assignee_result(clean_assignee, work_order_id=work_order_id)
    resolved_assignee = assignee_user["display_name"]
    updated = repository.update_work_order(work_order_id, {"assigned_to": resolved_assignee})
    if updated:
        notify_work_order_changed(work_order, updated, current_user)
    return {
        "status": "completed",
        "action_type": "assign_work_order",
        "work_order_id": work_order_id,
        "assignee": resolved_assignee,
        "assignee_user_id": assignee_user["id"],
        "detail": f"Assigned to {resolved_assignee}.",
        "work_order": updated,
    }


def create_work_order(
    equipment_id: str,
    assignee: Optional[str] = None,
    title: Optional[str] = None,
    recommended_action: Optional[str] = None,
    current_user: Optional[Any] = None,
) -> dict[str, Any]:
    user = _user_context(current_user)
    if user["role"] not in WORK_ORDER_ACTION_ROLES:
        return {
            "status": "not_allowed",
            "equipment_id": equipment_id,
            "detail": f"Role {user['role']} cannot create work orders.",
        }
    normalized_equipment_id = equipment_id.strip().upper()
    equipment = repository.get_equipment(normalized_equipment_id)
    if not equipment:
        return {
            "status": "not_found",
            "equipment_id": normalized_equipment_id,
            "detail": "Equipment not found.",
        }
    profile = repository.get_asset_profile(normalized_equipment_id) or {}
    recommendations = repository.list_asset_recommendations(normalized_equipment_id)
    top_recommendation = recommendations[0] if recommendations else None
    requested_assignee = (assignee or "").strip()
    assignee_user = _active_user_for_assignee(requested_assignee) if requested_assignee else None
    if requested_assignee and not assignee_user:
        return _unknown_assignee_result(requested_assignee, equipment_id=normalized_equipment_id)
    clean_assignee = assignee_user["display_name"] if assignee_user else ""
    work_title = (title or "").strip() or f"Inspect {equipment['name']} critical condition"
    action_text = (recommended_action or "").strip() or (
        top_recommendation["description"]
        if top_recommendation
        else "Inspect asset condition, validate active alerts, and document required corrective action."
    )
    due_date = (datetime.now(IST) + timedelta(days=1)).replace(microsecond=0).isoformat()
    priority = 1 if _asset_risk_level(equipment, repository.list_alerts(normalized_equipment_id)) in {"critical", "high"} else 2
    work_order = repository.create_work_order(
        {
            "equipment_id": normalized_equipment_id,
            "title": work_title,
            "description": (
                f"Neo created this work order for {equipment['name']} from an assistant action request. "
                f"Recommended action: {action_text}"
            ),
            "status": "WAPPR",
            "priority": priority,
            "work_type": "CM",
            "failure_class": _failure_class_for_asset(normalized_equipment_id),
            "problem_code": _problem_code_from_recommendation(top_recommendation),
            "classification": top_recommendation["title"] if top_recommendation else "Critical asset follow-up",
            "assigned_to": clean_assignee,
            "supervisor": profile.get("supervisor") or "Maintenance Supervisor",
            "due_date": due_date,
            "recommended_action": action_text,
            "follow_up_required": True,
            "ai_summary": f"Neo created a role-authorized follow-up work order for {normalized_equipment_id}.",
        }
    )
    notify_work_order_created(work_order, current_user)
    return {
        "status": "completed",
        "action_type": "create_work_order",
        "work_order_id": work_order["id"],
        "equipment_id": normalized_equipment_id,
        "assignee": clean_assignee,
        "assignee_user_id": assignee_user["id"] if assignee_user else None,
        "detail": (
            f"Created {work_order['id']} for {normalized_equipment_id} and assigned it to {clean_assignee}."
            if clean_assignee
            else f"Created {work_order['id']} for {normalized_equipment_id}; assignment is blank."
        ),
        "work_order": work_order,
    }


def add_work_order_log(
    work_order_id: str,
    content: str,
    entry_type: str = "assistant_tool",
    current_user: Optional[Any] = None,
) -> dict[str, Any]:
    user = _user_context(current_user)
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        return {"status": "not_found", "work_order_id": work_order_id, "detail": "Work order not found."}
    if user["role"] not in WORK_ORDER_ACTION_ROLES:
        return {
            "status": "not_allowed",
            "work_order_id": work_order_id,
            "detail": f"Role {user['role']} cannot add work-order logs.",
        }
    if user["role"] == "maintenance_technician" and work_order["assigned_to"] != user["display_name"]:
        return {
            "status": "not_allowed",
            "work_order_id": work_order_id,
            "detail": "Technicians can add logs only to work orders assigned to them.",
        }
    clean_content = content.strip()
    if not clean_content:
        return {"status": "blocked", "work_order_id": work_order_id, "detail": "Log content is required."}
    clean_entry_type = (entry_type or "assistant_tool").strip() or "assistant_tool"
    updated = repository.add_work_order_log(
        work_order_id,
        {
            "author": user["display_name"] or "Assistant",
            "entry_type": clean_entry_type,
            "content": clean_content,
        },
    )
    return {
        "status": "completed",
        "action_type": "add_work_order_log",
        "work_order_id": work_order_id,
        "detail": f"Added {clean_entry_type} log to {work_order_id}.",
        "work_order": updated,
    }


def _evidence_payload(item: Evidence) -> dict[str, Any]:
    return {
        "source_type": item.source_type,
        "source_id": item.source_id,
        "title": item.title,
        "excerpt": item.excerpt,
        "equipment_id": item.equipment_id,
        "timestamp": item.timestamp,
        "relevance_reason": item.relevance_reason,
    }


def _user_context(current_user: Optional[Any]) -> dict[str, str]:
    if current_user is None:
        return {"role": "anonymous", "display_name": ""}
    if isinstance(current_user, dict):
        return {
            "role": str(current_user.get("role") or "anonymous"),
            "display_name": str(current_user.get("display_name") or ""),
        }
    return {
        "role": str(getattr(current_user, "role", "anonymous")),
        "display_name": str(getattr(current_user, "display_name", "")),
    }


def _active_user_for_assignee(assignee: str) -> Optional[dict[str, Any]]:
    clean_assignee = (assignee or "").strip()
    if not clean_assignee:
        return None
    normalized = clean_assignee.casefold()
    for user in repository.list_users():
        if not user.get("is_active"):
            continue
        if str(user.get("display_name") or "").casefold() == normalized:
            return user
        if str(user.get("email") or "").casefold() == normalized:
            return user
    return None


def _valid_assignee_options() -> list[dict[str, str]]:
    return [
        {
            "id": str(user.get("id") or ""),
            "display_name": str(user.get("display_name") or ""),
            "email": str(user.get("email") or ""),
            "role": str(user.get("role") or ""),
        }
        for user in repository.list_users()
        if user.get("is_active")
    ]


def _unknown_assignee_result(
    assignee: str,
    *,
    work_order_id: Optional[str] = None,
    equipment_id: Optional[str] = None,
) -> dict[str, Any]:
    valid_assignees = _valid_assignee_options()
    valid_names = ", ".join(item["display_name"] for item in valid_assignees if item["display_name"])
    detail = f"Assignee '{assignee or 'unknown'}' is not an active Maintenance Wizard user."
    if valid_names:
        detail = f"{detail} Choose one of: {valid_names}."
    result: dict[str, Any] = {
        "status": "blocked",
        "detail": detail,
        "assignee": assignee,
        "valid_assignees": valid_assignees,
    }
    if work_order_id:
        result["work_order_id"] = work_order_id
    if equipment_id:
        result["equipment_id"] = equipment_id
    return result


def _can_update_work_order_status(work_order: dict[str, Any], target_status: str, user: dict[str, str]) -> tuple[bool, str]:
    if target_status not in WORK_ORDER_STATUS_LABELS:
        return False, "Unsupported work order status."
    role = user["role"]
    if role not in WORK_ORDER_ACTION_ROLES:
        return False, "Your role cannot update work orders."
    if target_status == "APPR":
        if role not in WORK_ORDER_APPROVAL_ROLES:
            return False, "Only admin and supervisor roles can approve work orders."
        if work_order["status"] != "WAPPR":
            return False, "Only WAPPR work orders can be approved."
    if role == "maintenance_technician":
        if work_order["assigned_to"] != user["display_name"]:
            return False, "Technicians can update only work orders assigned to them."
        if target_status == "INPRG" and _work_order_has_material_blocker(work_order):
            return False, _material_start_block_reason(work_order)
        if target_status == "INPRG" and work_order["status"] not in {"APPR", "WMATL"}:
            return False, "Technicians can start only APPR or WMATL work orders."
        if target_status == "COMP" and work_order["status"] != "INPRG":
            return False, "Technicians can complete only INPRG work orders."
        if target_status not in {"INPRG", "COMP"}:
            return False, "Technician status update is not permitted."
    return True, "Allowed"


def _work_order_has_material_blocker(work_order: dict[str, Any]) -> bool:
    if work_order.get("material_blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
        return True
    return any(
        item.get("blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}
        for item in work_order.get("spare_reservations", [])
    )


def _material_start_block_reason(work_order: dict[str, Any]) -> str:
    note = work_order.get("material_blocker_note")
    if note:
        return str(note)
    for item in work_order.get("spare_reservations", []):
        if item.get("blocker_status") in {"blocked", "waiting_procurement", "reorder_requested"}:
            return str(item.get("blocker_note") or "Material blocker is unresolved.")
    return "Material blocker is unresolved."


def _resolved_spare_reservation(reservation: dict[str, Any]) -> dict[str, Any]:
    updated = dict(reservation)
    updated["blocker_status"] = "reserved"
    updated["blocker_note"] = None
    return updated


def _asset_risk_level(equipment: dict[str, Any], alerts: list[dict[str, Any]]) -> str:
    if alerts:
        return max((alert["severity"] for alert in alerts), key=lambda severity: RISK_ORDER[severity])
    criticality = int(equipment.get("criticality") or 0)
    if criticality >= 5:
        return "high"
    if criticality >= 3:
        return "medium"
    return "low"


def _failure_class_for_asset(equipment_id: str) -> str:
    if equipment_id.startswith("BF-"):
        return "CTRL"
    if equipment_id.startswith("HYD-"):
        return "HYD"
    if equipment_id.startswith("OH-"):
        return "ELEC"
    return "MECH"


def _problem_code_from_recommendation(recommendation: Optional[dict[str, Any]]) -> str:
    if not recommendation:
        return "INVESTIGATE"
    compact = re.sub(r"[^A-Z0-9]", "", str(recommendation["title"]).upper())
    return compact[:12] or "INVESTIGATE"
