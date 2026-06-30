"""Mock DeltaV interface. Replace method bodies with real DeltaV API calls."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class DVBatch:
    batch_id: str
    phase: str
    equipment: str
    unit_procedure: str
    status: str = "Created"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    segments: Dict[str, str] = field(default_factory=dict)  # name -> status


class DeltaVInterface:
    def __init__(self):
        self._batches: Dict[str, DVBatch] = {}

    def launch_batch(self, batch_id: str, phase: str, equipment: str, unit_procedure: str) -> DVBatch:
        dv = DVBatch(batch_id=batch_id, phase=phase, equipment=equipment, unit_procedure=unit_procedure)
        self._batches[batch_id] = dv
        return dv

    def get_batch(self, batch_id: str) -> Optional[DVBatch]:
        return self._batches.get(batch_id)

    def update_batch(
        self,
        batch_id: str,
        status: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        b = self._batches.get(batch_id)
        if b:
            b.status = status
            if start_time:
                b.start_time = start_time
            if end_time:
                b.end_time = end_time

    def update_segment(self, batch_id: str, segment_name: str, status: str):
        b = self._batches.get(batch_id)
        if b:
            b.segments[segment_name] = status

    def active_batches(self) -> List[DVBatch]:
        return [b for b in self._batches.values() if b.status in ("Running", "Paused")]

    def all_batches(self) -> List[DVBatch]:
        return list(self._batches.values())
