"""Simulation engine — apply actual timestamps to scheduled batches for testing."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, TYPE_CHECKING

from .models import ScheduledBatch, BatchStatus

if TYPE_CHECKING:
    from .engine import SchedulingEngine


def _auto_complete_segments(
    batch: ScheduledBatch,
    actual_start: datetime,
    actual_end: datetime,
) -> None:
    """
    When a batch is marked complete, auto-complete every segment within it.
    Actual times are distributed proportionally to planned segment durations so
    that robot_windows on the batch will reflect real utilisation.
    Segments already assigned actual_end are left untouched.
    """
    if not batch.segments:
        return
    planned_dur = batch.target_duration_min
    actual_dur  = (actual_end - actual_start).total_seconds() / 60
    scale       = (actual_dur / planned_dur) if planned_dur > 0 else 1.0
    cumulative  = 0.0
    for seg in batch.segments:
        if seg.actual_end is None:
            seg.actual_start = actual_start + timedelta(minutes=cumulative * scale)
            seg.actual_end   = actual_start + timedelta(minutes=(cumulative + seg.target_duration_min) * scale)
            seg.status       = "Complete"
        cumulative += seg.target_duration_min


@dataclass
class SimEvent:
    event_type: str          # "batch_start" | "batch_end" | "seg_start" | "seg_end"
    batch_id: str
    timestamp: datetime
    segment_name: Optional[str] = None
    notes: str = ""


class SimulationEngine:
    def __init__(self):
        self.events: List[SimEvent] = []

    # ── Batch-level ────────────────────────────────────────────────────────────

    def apply_batch_start(
        self,
        batches: List[ScheduledBatch],
        batch_id: str,
        actual_start: datetime,
    ) -> List[ScheduledBatch]:
        batch = self._get(batches, batch_id)
        if batch:
            batch.actual_start = actual_start
            batch.status = BatchStatus.IN_PROGRESS
            self.events.append(SimEvent("batch_start", batch_id, actual_start))
        return batches

    def apply_batch_end(
        self,
        batches: List[ScheduledBatch],
        batch_id: str,
        actual_end: datetime,
        engine: Optional["SchedulingEngine"] = None,
        reschedule_threshold_min: int = 0,
    ) -> List[ScheduledBatch]:
        batch = self._get(batches, batch_id)
        if batch:
            batch.actual_end = actual_end
            batch.status = BatchStatus.COMPLETE
            # Auto-complete all segments proportionally so robot_windows reflects
            # real utilisation and freed slots are visible during rescheduling.
            _auto_complete_segments(
                batch,
                batch.actual_start or batch.scheduled_start,
                actual_end,
            )
            self.events.append(SimEvent("batch_end", batch_id, actual_end))
            if engine:
                if batch.delay_min > reschedule_threshold_min:
                    # Finished late — cascade delay and push other patients
                    batches = engine.reschedule_from_delay(batches, batch_id)
                elif actual_end < batch.scheduled_end:
                    # Finished early — pull downstream forward and free slots for others
                    batches = engine.reschedule_from_early_completion(batches, batch_id)
        return batches

    # ── Segment-level ──────────────────────────────────────────────────────────

    def apply_segment_start(
        self,
        batches: List[ScheduledBatch],
        batch_id: str,
        segment_name: str,
        actual_start: datetime,
    ) -> List[ScheduledBatch]:
        batch = self._get(batches, batch_id)
        if batch:
            seg = next((s for s in batch.segments if s.segment_name == segment_name), None)
            if seg:
                seg.actual_start = actual_start
                seg.status = "In Progress"
                self.events.append(SimEvent("seg_start", batch_id, actual_start, segment_name))
        return batches

    def apply_segment_end(
        self,
        batches: List[ScheduledBatch],
        batch_id: str,
        segment_name: str,
        actual_end: datetime,
        engine: Optional["SchedulingEngine"] = None,
        reschedule_threshold_min: int = 0,
    ) -> List[ScheduledBatch]:
        batch = self._get(batches, batch_id)
        if batch:
            seg = next((s for s in batch.segments if s.segment_name == segment_name), None)
            if seg:
                seg.actual_end = actual_end
                seg.status = "Complete"
                self.events.append(SimEvent("seg_end", batch_id, actual_end, segment_name))
                if engine and batch.delay_min > reschedule_threshold_min:
                    batches = engine.reschedule_from_delay(batches, batch_id)
        return batches

    # ── Export / Import ────────────────────────────────────────────────────────

    def export_json(self) -> str:
        return json.dumps(
            [
                {
                    "event_type": e.event_type,
                    "batch_id": e.batch_id,
                    "timestamp": e.timestamp.isoformat(),
                    "segment_name": e.segment_name,
                    "notes": e.notes,
                }
                for e in self.events
            ],
            indent=2,
        )

    def import_json(
        self,
        json_str: str,
        batches: List[ScheduledBatch],
        engine: Optional["SchedulingEngine"] = None,
        reschedule_threshold_min: int = 0,
    ) -> List[ScheduledBatch]:
        for ev in json.loads(json_str):
            ts = datetime.fromisoformat(ev["timestamp"])
            et = ev["event_type"]
            bid = ev["batch_id"]
            seg = ev.get("segment_name")
            if et == "batch_start":
                self.apply_batch_start(batches, bid, ts)
            elif et == "batch_end":
                self.apply_batch_end(batches, bid, ts, engine, reschedule_threshold_min)
            elif et == "seg_start" and seg:
                self.apply_segment_start(batches, bid, seg, ts)
            elif et == "seg_end" and seg:
                self.apply_segment_end(batches, bid, seg, ts, engine, reschedule_threshold_min)
        return batches

    def clear(self):
        self.events.clear()

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _get(batches: List[ScheduledBatch], batch_id: str) -> Optional[ScheduledBatch]:
        return next((b for b in batches if b.batch_id == batch_id), None)
