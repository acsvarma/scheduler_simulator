"""Persist and restore the full scheduler session to/from a JSON file."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    BatchStatus, Equipment, EquipmentType, Patient,
    ScheduledBatch, Segment,
)

SESSION_FILE = Path("scheduler_session.json")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None

def _dts(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


# ── Serialise ──────────────────────────────────────────────────────────────────

def _ser_sequence(seq: list) -> list:
    result = []
    for step in seq:
        s = {k: v for k, v in step.items()}
        s["equipment_type"] = (
            step["equipment_type"].value
            if hasattr(step["equipment_type"], "value")
            else step["equipment_type"]
        )
        s["segments"] = [dict(seg) for seg in step.get("segments", [])]
        result.append(s)
    return result


def _ser_segment(s: Segment) -> dict:
    return {
        "segment_id":        s.segment_id,
        "segment_name":      s.segment_name,
        "target_duration_min": s.target_duration_min,
        "sequence":          s.sequence,
        "robot_types":       s.robot_types,
        "robot_duration_min": s.robot_duration_min,
        "max_duration_min":  s.max_duration_min,
        "overlap_next_step": s.overlap_next_step,
        "std_dev_sec":       s.std_dev_sec,
        "max_duration_type": s.max_duration_type,
        "actual_start":      _dts(s.actual_start),
        "actual_end":        _dts(s.actual_end),
        "status":            s.status,
    }


def _ser_batch(b: ScheduledBatch) -> dict:
    return {
        "batch_id":           b.batch_id,
        "patient_id":         b.patient_id,
        "phase_name":         b.phase_name,
        "phase_label":        b.phase_label,
        "phase_key":          b.phase_key,
        "step_index":         b.step_index,
        "equipment_id":       b.equipment_id,
        "equipment_type":     b.equipment_type.value,
        "scheduled_start":    _dts(b.scheduled_start),
        "scheduled_end":      _dts(b.scheduled_end),
        "target_duration_min": b.target_duration_min,
        "actual_start":       _dts(b.actual_start),
        "actual_end":         _dts(b.actual_end),
        "status":             b.status.value,
        # tuples → lists for JSON; restored as tuples on load
        "robot_offsets":      [list(t) for t in b.robot_offsets],
        "segments":           [_ser_segment(s) for s in b.segments],
    }


def dump_session(state) -> dict:
    """Convert Streamlit session_state into a plain JSON-serialisable dict."""
    return {
        "version":                    2,
        "schedule_start":             _dts(state.get("schedule_start")),
        "active_sequence":            state.get("active_sequence", "Default CAR-T"),
        "reschedule_threshold_min":   state.get("reschedule_threshold_min", 0),
        "auto_start_grace_min":       state.get("auto_start_grace_min", 0),
        "eq_efficiency":              state.get("eq_efficiency", {}),
        "patients": [
            {
                "patient_id":  p.patient_id,
                "priority":    p.priority,
                "order_id":    p.order_id,
                "incubator_id": p.incubator_id,
                "status":      p.status,
                "notes":       p.notes,
            }
            for p in state.get("patients", [])
        ],
        "sequences": {
            name: _ser_sequence(seq)
            for name, seq in state.get("sequences", {}).items()
        },
        "equipment": [
            {
                "equipment_id":   e.equipment_id,
                "equipment_type": e.equipment_type.value,
                "display_name":   e.display_name,
                "is_available":   e.is_available,
            }
            for e in state.get("equipment", [])
        ],
        "schedule":   [_ser_batch(b) for b in state.get("schedule", [])],
        "sim_events": json.loads(state["sim"].export_json()) if state.get("sim") else [],
    }


# ── Deserialise ────────────────────────────────────────────────────────────────

def _de_segment(d: dict) -> Segment:
    return Segment(
        segment_id=d["segment_id"],
        segment_name=d["segment_name"],
        target_duration_min=d["target_duration_min"],
        sequence=d["sequence"],
        robot_types=d.get("robot_types", []),
        robot_duration_min=d.get("robot_duration_min", 0),
        max_duration_min=d.get("max_duration_min", 0),
        overlap_next_step=d.get("overlap_next_step", False),
        std_dev_sec=int(d.get("std_dev_sec", 0) or 0),
        max_duration_type=str(d.get("max_duration_type", "fixed") or "fixed"),
        actual_start=_dt(d.get("actual_start")),
        actual_end=_dt(d.get("actual_end")),
        status=d.get("status", "Pending"),
    )


def _de_batch(d: dict) -> ScheduledBatch:
    return ScheduledBatch(
        batch_id=d["batch_id"],
        patient_id=d["patient_id"],
        phase_name=d["phase_name"],
        phase_label=d["phase_label"],
        phase_key=d["phase_key"],
        step_index=d["step_index"],
        equipment_id=d["equipment_id"],
        equipment_type=EquipmentType(d["equipment_type"]),
        scheduled_start=datetime.fromisoformat(d["scheduled_start"]),
        scheduled_end=datetime.fromisoformat(d["scheduled_end"]),
        target_duration_min=d["target_duration_min"],
        actual_start=_dt(d.get("actual_start")),
        actual_end=_dt(d.get("actual_end")),
        status=BatchStatus(d["status"]),
        # JSON lists → tuples
        robot_offsets=[tuple(t) for t in d.get("robot_offsets", [])],
        segments=[_de_segment(s) for s in d.get("segments", [])],
    )


def _de_sequence(seq: list) -> list:
    result = []
    for step in seq:
        s = dict(step)
        s["equipment_type"] = EquipmentType(step["equipment_type"])
        s["segments"] = [dict(seg) for seg in step.get("segments", [])]
        result.append(s)
    return result


def load_session(data: dict) -> Dict[str, Any]:
    """
    Reconstruct session state fields from the saved dict.
    Returns a plain dict — caller merges into st.session_state.
    """
    patients = [
        Patient(
            patient_id=p["patient_id"],
            priority=p["priority"],
            order_id=p.get("order_id", ""),
            incubator_id=p.get("incubator_id", ""),
            status=p.get("status", "Pending"),
            notes=p.get("notes", ""),
        )
        for p in data.get("patients", [])
    ]

    sequences = {
        name: _de_sequence(seq)
        for name, seq in data.get("sequences", {}).items()
    }

    equipment = [
        Equipment(
            equipment_id=e["equipment_id"],
            equipment_type=EquipmentType(e["equipment_type"]),
            display_name=e["display_name"],
            is_available=e.get("is_available", True),
        )
        for e in data.get("equipment", [])
    ]

    schedule = [_de_batch(b) for b in data.get("schedule", [])]

    active_sequence = data.get("active_sequence", "Default CAR-T")
    if active_sequence not in sequences and sequences:
        active_sequence = next(iter(sequences))

    schedule_start_raw = data.get("schedule_start")
    schedule_start = (
        datetime.fromisoformat(schedule_start_raw)
        if schedule_start_raw
        else datetime.now(tz=__import__('zoneinfo').ZoneInfo("America/New_York")).replace(tzinfo=None, hour=6, minute=0, second=0, microsecond=0)
    )

    # Rebuild engine if there is a schedule
    engine = None
    if schedule and active_sequence in sequences:
        from .engine import SchedulingEngine
        engine = SchedulingEngine(equipment, sequences[active_sequence])

    # SimulationEngine — schedule state (actual_start/end, status) is already fully
    # restored on each batch/segment above; sim_events are audit-trail only.
    from .simulation import SimulationEngine
    sim = SimulationEngine()

    return {
        "patients":                  patients,
        "sequences":                 sequences,
        "equipment":                 equipment,
        "schedule":                  schedule,
        "schedule_start":            schedule_start,
        "active_sequence":           active_sequence,
        "engine":                    engine,
        "sim":                       sim,
        "reschedule_threshold_min":  data.get("reschedule_threshold_min", 0),
        "auto_start_grace_min":      data.get("auto_start_grace_min", 0),
        "eq_efficiency":             data.get("eq_efficiency", {}),
    }


# ── File helpers ───────────────────────────────────────────────────────────────

def save_to_file(state, path: Path = SESSION_FILE) -> None:
    data = dump_session(state)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_from_file(path: Path = SESSION_FILE) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return load_session(data)
    except Exception:
        return None
