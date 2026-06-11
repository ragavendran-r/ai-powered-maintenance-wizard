from typing import Iterable, Optional

from app.data import repository
from app.models.schemas import MaintenanceLabel
from app.services.ai_client import configured_llm_client


COMPONENT_HINTS = [
    "bearing",
    "motor",
    "pump",
    "gearbox",
    "coupling",
    "seal",
    "valve",
    "actuator",
    "brake",
    "rope",
    "foundation",
]
FAILURE_HINTS = {
    "vibration": "vibration_excursion",
    "temperature": "thermal_excursion",
    "overheat": "thermal_excursion",
    "current": "electrical_overload",
    "pressure": "pressure_instability",
    "flow": "flow_instability",
    "leak": "leakage",
    "wear": "wear",
    "misalignment": "misalignment",
    "loose": "looseness",
    "looseness": "looseness",
}


def label_maintenance_history(equipment_id: Optional[str] = None) -> list[MaintenanceLabel]:
    records = []
    for event in repository.list_maintenance_events(equipment_id):
        records.append(label_maintenance_event(event))
    for feedback in repository.list_feedback(equipment_id):
        records.append(label_feedback(feedback))
    return records


def stored_labels(equipment_id: Optional[str] = None) -> list[MaintenanceLabel]:
    return [MaintenanceLabel(**record) for record in repository.list_maintenance_labels(equipment_id)]


def label_maintenance_event(event: dict) -> MaintenanceLabel:
    text = f"{event['issue']} {event['root_cause']} {event['action']}"
    fallback = _fallback_label(
        source_type="maintenance_event",
        source_id=event["id"],
        equipment_id=event["equipment_id"],
        text=text,
        root_cause=event.get("root_cause") or "unknown",
        action=event.get("action") or "unknown",
        outcome_status="historical_event",
    )
    label = _complete_label(
        fallback,
        [
            "Source type: maintenance_event",
            f"Source id: {event['id']}",
            f"Equipment id: {event['equipment_id']}",
            f"Issue: {event['issue']}",
            f"Root cause: {event['root_cause']}",
            f"Action: {event['action']}",
            f"Downtime hours: {event['downtime_hours']}",
        ],
    )
    repository.save_maintenance_label(label.model_dump())
    return label


def label_feedback(feedback: dict) -> MaintenanceLabel:
    text = " ".join(
        part
        for part in [
            feedback.get("corrected_diagnosis"),
            feedback.get("actual_root_cause"),
            feedback.get("action_taken"),
            feedback.get("outcome"),
            feedback.get("notes"),
        ]
        if part
    )
    fallback = _fallback_label(
        source_type="feedback",
        source_id=str(feedback["id"]),
        equipment_id=feedback.get("equipment_id"),
        text=text,
        root_cause=feedback.get("actual_root_cause") or feedback.get("corrected_diagnosis") or "unknown",
        action=feedback.get("action_taken") or "unknown",
        outcome_status=feedback.get("status") or "unknown",
    )
    label = _complete_label(
        fallback,
        [
            "Source type: feedback",
            f"Source id: {feedback['id']}",
            f"Equipment id: {feedback.get('equipment_id') or 'not specified'}",
            f"Status: {feedback['status']}",
            f"Corrected diagnosis: {feedback.get('corrected_diagnosis') or ''}",
            f"Actual root cause: {feedback.get('actual_root_cause') or ''}",
            f"Action taken: {feedback.get('action_taken') or ''}",
            f"Outcome: {feedback.get('outcome') or ''}",
            f"Notes: {feedback.get('notes') or ''}",
        ],
    )
    repository.save_maintenance_label(label.model_dump())
    return label


def training_signal_summary(equipment_id: Optional[str] = None) -> list[str]:
    labels = repository.list_maintenance_labels(equipment_id)
    if not labels:
        labels = [label.model_dump() for label in label_maintenance_history(equipment_id)]
    return [
        (
            f"{label['source_type']} {label['source_id']}: {label['failure_mode']} on "
            f"{label['component']} from {label['root_cause']} -> {label['action_class']}"
        )
        for label in labels[:5]
        if label.get("usable_for_training", True)
    ]


def _complete_label(fallback: MaintenanceLabel, prompt_lines: Iterable[str]) -> MaintenanceLabel:
    label = configured_llm_client().complete_model(
        "\n".join(prompt_lines),
        MaintenanceLabel,
        _label_system_prompt(),
        lambda provider, reason: fallback.model_copy(update={"provider": provider, "used_live_provider": False}),
    )
    return label.model_copy(
        update={
            "source_type": fallback.source_type,
            "source_id": fallback.source_id,
            "equipment_id": fallback.equipment_id,
        }
    )


def _label_system_prompt() -> str:
    return (
        "Normalize maintenance history or engineer feedback into JSON with keys "
        "source_type, source_id, equipment_id, failure_mode, component, root_cause, "
        "action_class, outcome_status, signal_hints, usable_for_training, "
        "used_live_provider, and provider. Use stable snake_case labels where possible."
    )


def _fallback_label(
    source_type: str,
    source_id: str,
    equipment_id: Optional[str],
    text: str,
    root_cause: str,
    action: str,
    outcome_status: str,
) -> MaintenanceLabel:
    lowered = text.lower()
    component = next((hint for hint in COMPONENT_HINTS if hint in lowered), "asset")
    failure_mode = next((value for key, value in FAILURE_HINTS.items() if key in lowered), "degraded_condition")
    action_class = _action_class(action)
    signal_hints = [key for key in FAILURE_HINTS if key in lowered][:5]
    return MaintenanceLabel(
        source_type=source_type,
        source_id=source_id,
        equipment_id=equipment_id,
        failure_mode=failure_mode,
        component=component,
        root_cause=root_cause,
        action_class=action_class,
        outcome_status=outcome_status,
        signal_hints=signal_hints,
        usable_for_training=bool(text.strip()),
        used_live_provider=False,
        provider="mock",
    )


def _action_class(action: str) -> str:
    lowered = action.lower()
    if any(term in lowered for term in ("replace", "replacement")):
        return "replace_component"
    if any(term in lowered for term in ("inspect", "inspection", "check")):
        return "inspect"
    if any(term in lowered for term in ("align", "alignment")):
        return "align"
    if any(term in lowered for term in ("lubric", "grease", "oil")):
        return "lubricate"
    if any(term in lowered for term in ("retorque", "tighten")):
        return "tighten"
    return "maintenance_action"
