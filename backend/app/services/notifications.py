from __future__ import annotations

from typing import Any, Optional

from app.data import repository
from app.models.schemas import Recommendation, UserPublic
from app.services.ai_client import configured_llm_client
from app.services.llm import LLMTextResponse


PLANNER_ROLES = ["planner"]
SUPERVISOR_ROLES = ["maintenance_supervisor", "admin"]
ENGINEERING_ROLES = ["maintenance_engineer", "reliability_engineer", "maintenance_supervisor", "admin"]
ALERT_ROLES = ["operator", "maintenance_engineer", "reliability_engineer", "maintenance_supervisor", "admin"]
RELIABILITY_REVIEW_ROLES = ["reliability_engineer", "maintenance_supervisor", "admin"]


def notify_work_order_created(work_order: dict[str, Any], actor: Optional[UserPublic] = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    assignee = _active_user_for_display_name(work_order.get("assigned_to"))
    if assignee:
        events.append(
            _emit_notification(
                event_key=_event_key("work_order_assigned", work_order, "technician", assignee["id"]),
                event_type="work_order_assigned",
                audience="technician",
                title=f"New work order assigned: {work_order['id']}",
                summary=f"{work_order['title']} is assigned to you.",
                fallback_action="Review the asset, latest alerts, material readiness, SOP, and planned window before field execution.",
                work_order=work_order,
                recipient_user_ids=[assignee["id"]],
                actor=actor,
            )
        )
    if int(work_order.get("priority") or 5) <= 2:
        events.append(
            _emit_notification(
                event_key=_event_key("work_order_created", work_order, "supervisor"),
                event_type="work_order_created",
                audience="supervisor",
                title=f"Priority work order created: {work_order['id']}",
                summary=f"{work_order['title']} was created for {work_order['equipment_id']}.",
                fallback_action="Confirm owner, approval state, material readiness, and shift priority before release.",
                work_order=work_order,
                recipient_roles=SUPERVISOR_ROLES,
                actor=actor,
            )
        )
    return [event for event in events if event]


def notify_work_order_changed(
    before: dict[str, Any],
    after: dict[str, Any],
    actor: Optional[UserPublic] = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    timestamp_key = _timestamp_key(after)
    if before.get("assigned_to") != after.get("assigned_to"):
        old_assignee = _active_user_for_display_name(before.get("assigned_to"))
        new_assignee = _active_user_for_display_name(after.get("assigned_to"))
        if old_assignee:
            events.append(
                _emit_notification(
                    event_key=f"work_order_reassigned:{after['id']}:old:{old_assignee['id']}:{timestamp_key}",
                    event_type="work_order_reassigned",
                    audience="technician",
                    title=f"Work order reassigned: {after['id']}",
                    summary=f"{after['title']} is no longer assigned to you.",
                    fallback_action="Confirm handoff notes and stop using this work order as your active execution item.",
                    work_order=after,
                    recipient_user_ids=[old_assignee["id"]],
                    actor=actor,
                )
            )
        if new_assignee:
            events.append(
                _emit_notification(
                    event_key=f"work_order_assigned:{after['id']}:new:{new_assignee['id']}:{timestamp_key}",
                    event_type="work_order_assigned",
                    audience="technician",
                    title=f"Work order assigned: {after['id']}",
                    summary=f"{after['title']} is now assigned to you.",
                    fallback_action="Review the latest asset condition, material readiness, and safe execution sequence.",
                    work_order=after,
                    recipient_user_ids=[new_assignee["id"]],
                    actor=actor,
                )
            )
        events.append(
            _emit_notification(
                event_key=f"work_order_reassigned:{after['id']}:supervisor:{timestamp_key}",
                event_type="work_order_reassigned",
                audience="supervisor",
                title=f"Assignment changed: {after['id']}",
                summary=f"{after['id']} changed from {before.get('assigned_to') or 'unassigned'} to {after.get('assigned_to') or 'unassigned'}.",
                fallback_action="Check the handoff, planned window, and whether the new owner can execute safely.",
                work_order=after,
                recipient_roles=SUPERVISOR_ROLES,
                actor=actor,
            )
        )

    if before.get("status") != after.get("status"):
        events.extend(_status_notifications(before, after, actor, timestamp_key))

    if before.get("planning_status") != after.get("planning_status") and after.get("planning_status") == "dispatched":
        events.extend(_dispatch_notifications(after, actor, timestamp_key))

    if _schedule_changed(before, after):
        events.extend(_schedule_notifications(after, actor, timestamp_key))

    if _material_changed(before, after):
        events.extend(_material_notifications(before, after, actor, timestamp_key))

    return [event for event in events if event]


def notify_alerts_registered(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for alert in alerts:
        if alert.get("severity") not in {"high", "critical"}:
            continue
        events.append(
            _emit_notification(
                event_key=f"alert_registered:{alert['id']}",
                event_type="anomaly_alert_registered",
                audience="plant",
                title=f"{str(alert['severity']).title()} alert on {alert['equipment_id']}",
                summary=str(alert.get("message") or "A high-priority plant alert was registered."),
                fallback_action="Review the live sensor trend, confirm whether production load should be reduced, and assign an owner.",
                alert=alert,
                recipient_roles=ALERT_ROLES,
            )
        )
    return [event for event in events if event]


def notify_recommendation_generated(recommendation: Recommendation) -> Optional[dict[str, Any]]:
    if recommendation.risk_level not in {"high", "critical"}:
        return None
    return _emit_notification(
        event_key=f"recommendation_generated:{recommendation.id}",
        event_type="recommendation_generated",
        audience="engineering",
        title=f"{recommendation.risk_level.title()} recommendation for {recommendation.equipment_id}",
        summary=recommendation.diagnosis,
        fallback_action=recommendation.immediate_actions[0] if recommendation.immediate_actions else recommendation.urgency,
        recommendation=recommendation,
        recipient_roles=ENGINEERING_ROLES + PLANNER_ROLES,
    )


def _status_notifications(
    before: dict[str, Any],
    after: dict[str, Any],
    actor: Optional[UserPublic],
    timestamp_key: str,
) -> list[dict[str, Any]]:
    status = after.get("status")
    previous = before.get("status")
    events: list[dict[str, Any]] = []
    assignee = _active_user_for_display_name(after.get("assigned_to"))
    if status == "APPR":
        reason = "materials cleared" if previous == "WMATL" else "approved"
        if assignee:
            events.append(
                _emit_notification(
                    event_key=f"work_order_approved:{after['id']}:technician:{timestamp_key}",
                    event_type="work_order_approved",
                    audience="technician",
                    title=f"Work order ready: {after['id']}",
                    summary=f"{after['title']} is {reason} and ready for execution planning.",
                    fallback_action="Verify permits, isolation, material readiness, and dispatch timing before starting work.",
                    work_order=after,
                    recipient_user_ids=[assignee["id"]],
                    actor=actor,
                )
            )
        events.append(
            _emit_notification(
                event_key=f"work_order_approved:{after['id']}:planner:{timestamp_key}",
                event_type="work_order_approved",
                audience="planner",
                title=f"Work order approved: {after['id']}",
                summary=f"{after['title']} moved from {previous} to APPR.",
                fallback_action="Confirm planned start, material readiness, outage window, and dispatch readiness.",
                work_order=after,
                recipient_roles=PLANNER_ROLES,
                actor=actor,
            )
        )
        events.append(
            _emit_notification(
                event_key=f"work_order_approved:{after['id']}:supervisor:{timestamp_key}",
                event_type="work_order_approved",
                audience="supervisor",
                title=f"Approval state changed: {after['id']}",
                summary=f"{after['title']} moved from {previous} to APPR.",
                fallback_action="Review shift priority, owner readiness, and whether the work should be released now.",
                work_order=after,
                recipient_roles=SUPERVISOR_ROLES,
                actor=actor,
            )
        )
    elif status == "WMATL":
        events.append(
            _emit_notification(
                event_key=f"work_order_waiting_material:{after['id']}:planner:{timestamp_key}",
                event_type="work_order_waiting_material",
                audience="planner",
                title=f"Material blocker: {after['id']}",
                summary=f"{after['title']} is waiting for material.",
                fallback_action="Resolve reservations, procurement status, substitute availability, and expected material date.",
                work_order=after,
                recipient_roles=PLANNER_ROLES + SUPERVISOR_ROLES,
                actor=actor,
            )
        )
    elif status == "INPRG":
        events.append(
            _emit_notification(
                event_key=f"work_order_started:{after['id']}:supervisor:{timestamp_key}",
                event_type="work_order_started",
                audience="supervisor",
                title=f"Work started: {after['id']}",
                summary=f"{after['title']} is now in progress.",
                fallback_action="Monitor execution progress, safety constraints, and any material or access blockers.",
                work_order=after,
                recipient_roles=SUPERVISOR_ROLES + PLANNER_ROLES,
                actor=actor,
            )
        )
    elif status in {"COMP", "CLOSE"}:
        events.append(
            _emit_notification(
                event_key=f"work_order_review:{after['id']}:{status.lower()}:{timestamp_key}",
                event_type="work_order_review",
                audience="reliability",
                title=f"Work order {status.lower()}: {after['id']}",
                summary=f"{after['title']} moved to {status}.",
                fallback_action="Review completion notes, closeout quality, RCA need, and learning suitability.",
                work_order=after,
                recipient_roles=RELIABILITY_REVIEW_ROLES,
                actor=actor,
            )
        )
    return events


def _dispatch_notifications(
    work_order: dict[str, Any],
    actor: Optional[UserPublic],
    timestamp_key: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    assignee = _active_user_for_display_name(work_order.get("assigned_to"))
    if assignee:
        events.append(
            _emit_notification(
                event_key=f"work_order_dispatched:{work_order['id']}:technician:{timestamp_key}",
                event_type="work_order_dispatched",
                audience="technician",
                title=f"Work order dispatched: {work_order['id']}",
                summary=f"{work_order['title']} has been dispatched to you.",
                fallback_action="Check the planned start, permit/isolation requirements, material readiness, and first safe field step.",
                work_order=work_order,
                recipient_user_ids=[assignee["id"]],
                actor=actor,
            )
        )
    events.append(
        _emit_notification(
            event_key=f"work_order_dispatched:{work_order['id']}:supervisor:{timestamp_key}",
            event_type="work_order_dispatched",
            audience="supervisor",
            title=f"Dispatch confirmed: {work_order['id']}",
            summary=f"{work_order['title']} was dispatched.",
            fallback_action="Confirm technician readiness and watch for blockers before the planned execution window.",
            work_order=work_order,
            recipient_roles=SUPERVISOR_ROLES,
            actor=actor,
        )
    )
    return events


def _schedule_notifications(
    work_order: dict[str, Any],
    actor: Optional[UserPublic],
    timestamp_key: str,
) -> list[dict[str, Any]]:
    assignee = _active_user_for_display_name(work_order.get("assigned_to"))
    recipient_user_ids = [assignee["id"]] if assignee else []
    return [
        _emit_notification(
            event_key=f"work_order_schedule_changed:{work_order['id']}:{timestamp_key}",
            event_type="work_order_schedule_changed",
            audience="schedule",
            title=f"Schedule changed: {work_order['id']}",
            summary=f"{work_order['title']} has an updated due date or planned window.",
            fallback_action="Review the new timing, outage window, and whether material readiness still supports execution.",
            work_order=work_order,
            recipient_roles=PLANNER_ROLES + SUPERVISOR_ROLES,
            recipient_user_ids=recipient_user_ids,
            actor=actor,
        )
    ]


def _material_notifications(
    before: dict[str, Any],
    after: dict[str, Any],
    actor: Optional[UserPublic],
    timestamp_key: str,
) -> list[dict[str, Any]]:
    blocker_status = after.get("material_blocker_status")
    event_type = "work_order_material_cleared" if blocker_status in {"not_required", "reserved"} and after.get("material_readiness") == "ready" else "work_order_material_changed"
    fallback = (
        "Confirm execution can proceed and align dispatch with the planned maintenance window."
        if event_type == "work_order_material_cleared"
        else "Resolve material readiness, procurement state, substitute options, and blocker notes before execution."
    )
    assignee = _active_user_for_display_name(after.get("assigned_to"))
    return [
        _emit_notification(
            event_key=f"{event_type}:{after['id']}:{timestamp_key}",
            event_type=event_type,
            audience="material",
            title=f"Material state changed: {after['id']}",
            summary=(
                f"{after['title']} material state changed from "
                f"{before.get('material_blocker_status')} to {after.get('material_blocker_status')}."
            ),
            fallback_action=fallback,
            work_order=after,
            recipient_roles=PLANNER_ROLES + SUPERVISOR_ROLES,
            recipient_user_ids=[assignee["id"]] if assignee else [],
            actor=actor,
        )
    ]


def _emit_notification(
    *,
    event_key: str,
    event_type: str,
    audience: str,
    title: str,
    summary: str,
    fallback_action: str,
    recipient_roles: Optional[list[str]] = None,
    recipient_user_ids: Optional[list[str]] = None,
    work_order: Optional[dict[str, Any]] = None,
    alert: Optional[dict[str, Any]] = None,
    recommendation: Optional[Recommendation] = None,
    actor: Optional[UserPublic] = None,
) -> dict[str, Any]:
    recipient_roles = _unique(recipient_roles or [])
    recipient_user_ids = _unique(recipient_user_ids or [])
    if not recipient_roles and not recipient_user_ids:
        return {}
    equipment_id = _equipment_id(work_order, alert, recommendation)
    source_type, source_id = _source(work_order, alert, recommendation)
    text = _recommended_action_text(
        audience=audience,
        title=title,
        summary=summary,
        fallback_action=fallback_action,
        work_order=work_order,
        alert=alert,
        recommendation=recommendation,
    )
    return repository.create_notification_event(
        {
            "event_key": event_key,
            "event_type": event_type,
            "severity": _severity(work_order, alert, recommendation),
            "title": title,
            "summary": summary,
            "recommended_action": text.content.strip() or fallback_action,
            "source_type": source_type,
            "source_id": source_id,
            "equipment_id": equipment_id,
            "work_order_id": work_order.get("id") if work_order else None,
            "alert_id": alert.get("id") if alert else None,
            "recommendation_id": recommendation.id if recommendation else None,
            "actor_user_id": actor.id if actor else None,
            "actor_display_name": actor.display_name if actor else None,
            "recipient_roles": recipient_roles,
            "recipient_user_ids": recipient_user_ids,
            "metadata": {
                "audience": audience,
                "status": work_order.get("status") if work_order else None,
                "planning_status": work_order.get("planning_status") if work_order else None,
            },
            "llm_provider": text.provider,
            "llm_used_live_provider": text.used_live_provider,
        }
    )


def _recommended_action_text(
    *,
    audience: str,
    title: str,
    summary: str,
    fallback_action: str,
    work_order: Optional[dict[str, Any]],
    alert: Optional[dict[str, Any]],
    recommendation: Optional[Recommendation],
) -> LLMTextResponse:
    prompt = "\n".join(
        [
            f"Audience: {audience}",
            f"Notification: {title}",
            f"Summary: {summary}",
            f"Fallback action: {fallback_action}",
            f"Work order: {_compact_work_order(work_order)}",
            f"Alert: {_compact_alert(alert)}",
            f"Recommendation: {_compact_recommendation(recommendation)}",
            "Write one concise, role-specific next action sentence. Do not use markdown.",
        ]
    )
    return configured_llm_client().complete_text(
        prompt,
        "You write concise steel-plant maintenance notification recommendations. Keep instructions safe and role-specific.",
        lambda provider, _reason: LLMTextResponse(content=fallback_action, used_live_provider=False, provider=provider),
        max_tokens=80,
    )


def _active_user_for_display_name(display_name: Optional[str]) -> Optional[dict[str, Any]]:
    if not display_name:
        return None
    normalized = display_name.strip().casefold()
    for user in repository.list_users():
        if user.get("is_active") and str(user.get("display_name") or "").casefold() == normalized:
            return user
    return None


def _schedule_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return any(before.get(field) != after.get(field) for field in ("planned_start", "planned_end", "due_date"))


def _material_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return any(
        before.get(field) != after.get(field)
        for field in ("material_readiness", "material_blocker_status", "material_blocker_note")
    )


def _event_key(event_type: str, work_order: dict[str, Any], audience: str, subject: Optional[str] = None) -> str:
    parts = [event_type, work_order["id"], audience]
    if subject:
        parts.append(subject)
    parts.append(_timestamp_key(work_order))
    return ":".join(parts)


def _timestamp_key(work_order: dict[str, Any]) -> str:
    return str(work_order.get("updated_at") or work_order.get("created_at") or "initial").replace(":", "").replace(" ", "T")


def _severity(
    work_order: Optional[dict[str, Any]],
    alert: Optional[dict[str, Any]],
    recommendation: Optional[Recommendation],
) -> str:
    if alert:
        return str(alert.get("severity") or "medium")
    if recommendation:
        return recommendation.risk_level
    if work_order:
        priority = int(work_order.get("priority") or 5)
        if priority <= 1:
            return "critical"
        if priority == 2:
            return "high"
        if priority == 3:
            return "medium"
    return "info"


def _source(
    work_order: Optional[dict[str, Any]],
    alert: Optional[dict[str, Any]],
    recommendation: Optional[Recommendation],
) -> tuple[str, str]:
    if work_order:
        return "work_order", work_order["id"]
    if alert:
        return "alert", alert["id"]
    if recommendation:
        return "recommendation", recommendation.id
    return "notification", "unknown"


def _equipment_id(
    work_order: Optional[dict[str, Any]],
    alert: Optional[dict[str, Any]],
    recommendation: Optional[Recommendation],
) -> Optional[str]:
    if work_order:
        return work_order.get("equipment_id")
    if alert:
        return alert.get("equipment_id")
    if recommendation:
        return recommendation.equipment_id
    return None


def _compact_work_order(work_order: Optional[dict[str, Any]]) -> str:
    if not work_order:
        return "none"
    return (
        f"{work_order.get('id')} {work_order.get('title')}; status {work_order.get('status')}; "
        f"priority {work_order.get('priority')}; assigned to {work_order.get('assigned_to') or 'unassigned'}; "
        f"material {work_order.get('material_readiness')}/{work_order.get('material_blocker_status')}; "
        f"recommended action {work_order.get('recommended_action')}"
    )


def _compact_alert(alert: Optional[dict[str, Any]]) -> str:
    if not alert:
        return "none"
    return (
        f"{alert.get('id')} {alert.get('severity')} {alert.get('equipment_id')}; "
        f"{alert.get('signal')} {alert.get('value')} {alert.get('unit')} threshold {alert.get('threshold')}; "
        f"{alert.get('message')}"
    )


def _compact_recommendation(recommendation: Optional[Recommendation]) -> str:
    if not recommendation:
        return "none"
    return (
        f"{recommendation.id} {recommendation.risk_level} {recommendation.equipment_id}; "
        f"{recommendation.diagnosis}; first action "
        f"{recommendation.immediate_actions[0] if recommendation.immediate_actions else recommendation.urgency}"
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result
