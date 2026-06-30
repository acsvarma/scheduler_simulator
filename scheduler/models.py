from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Tuple


class BatchStatus(str, Enum):
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"
    DELAYED = "Delayed"


class EquipmentType(str, Enum):
    ROMAG = "Romag"
    INCUBATOR = "Incubator"
    BSD_SAMPLING = "BSD Sampling"
    BSD_WEIGHING = "BSD Weighing"
    FILL = "Fill"


class RobotType(str, Enum):
    ROMAG      = "Romag Robot"
    INCUBATION = "Incubation Robot"
    FILL       = "Fill Robot"


@dataclass
class Equipment:
    equipment_id: str
    equipment_type: EquipmentType
    display_name: str
    is_available: bool = True

    def __hash__(self):
        return hash(self.equipment_id)

    def __eq__(self, other):
        return isinstance(other, Equipment) and self.equipment_id == other.equipment_id


@dataclass
class Segment:
    segment_id: str
    segment_name: str
    target_duration_min: int
    sequence: int
    robot_types: List[str] = field(default_factory=list)  # RobotType value strings
    robot_duration_min: int = 0
    max_duration_min: int = 0       # 0 = no limit; if set, actual > max triggers reschedule
    overlap_next_step: bool = False  # next patient step may start when this segment begins
    std_dev_sec: int = 0            # standard deviation in seconds for variability-based max
    max_duration_type: str = "fixed"  # "fixed" | "1σ" | "2σ" | "3σ"
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    status: str = "Pending"

    @property
    def actual_duration_min(self) -> Optional[int]:
        if self.actual_start and self.actual_end:
            return max(0, int((self.actual_end - self.actual_start).total_seconds() / 60))
        return None

    @property
    def _max_threshold_min(self) -> float:
        """Effective max duration threshold in minutes, accounting for sigma-based types."""
        _sigma_map = {"1σ": 1, "2σ": 2, "3σ": 3}
        n = _sigma_map.get(self.max_duration_type, 0)
        if n > 0 and self.std_dev_sec > 0:
            return self.target_duration_min + n * self.std_dev_sec / 60.0
        if self.max_duration_min > 0:
            return float(self.max_duration_min)
        return float(self.target_duration_min)

    @property
    def delay_min(self) -> int:
        actual = self.actual_duration_min
        if actual is not None:
            return max(0, int(actual - self._max_threshold_min))
        return 0


@dataclass
class ScheduledBatch:
    batch_id: str
    patient_id: str
    phase_name: str       # Internal key e.g. "UP_INC_1"
    phase_label: str      # Display label e.g. "UP_INC (1st)"
    phase_key: str        # Base key for coloring e.g. "UP_INC"
    step_index: int       # Position in process sequence 0-9
    equipment_id: str
    equipment_type: EquipmentType
    scheduled_start: datetime
    scheduled_end: datetime
    target_duration_min: int
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    status: BatchStatus = BatchStatus.SCHEDULED
    segments: List[Segment] = field(default_factory=list)
    # (start_offset_min, end_offset_min, segment_name, robot_type) relative to batch start
    robot_offsets: List[Tuple[int, int, str, str]] = field(default_factory=list)

    @property
    def robot_windows(self) -> List[Tuple[datetime, datetime, str, str]]:
        """
        Robot usage windows (start, end, seg_name, robot_type).
        When a segment has actual times (e.g. auto-completed on batch close),
        uses those instead of the scheduled offsets so the robot calendar reflects
        real utilisation and freed slots are visible to the rescheduler.
        """
        seg_by_name = {s.segment_name: s for s in self.segments}
        base = self.effective_start
        result = []
        for s_off, e_off, seg_name, rtype in self.robot_offsets:
            seg = seg_by_name.get(seg_name)
            if seg and seg.actual_start and seg.robot_duration_min > 0:
                # Cap robot duration to the segment's actual duration
                actual_seg_min = (
                    (seg.actual_end - seg.actual_start).total_seconds() / 60
                    if seg.actual_end else None
                )
                robot_min = (
                    min(seg.robot_duration_min, actual_seg_min)
                    if actual_seg_min is not None
                    else seg.robot_duration_min
                )
                result.append((
                    seg.actual_start,
                    seg.actual_start + timedelta(minutes=robot_min),
                    seg_name, rtype,
                ))
            else:
                result.append((
                    base + timedelta(minutes=s_off),
                    base + timedelta(minutes=e_off),
                    seg_name, rtype,
                ))
        return result

    @property
    def delay_min(self) -> int:
        if self.actual_end and self.actual_end > self.scheduled_end:
            return int((self.actual_end - self.scheduled_end).total_seconds() / 60)
        seg_delay = sum(s.delay_min for s in self.segments)
        return seg_delay

    @property
    def projected_end(self) -> datetime:
        if self.actual_end:
            return self.actual_end
        d = self.delay_min
        if d > 0:
            return self.scheduled_end + timedelta(minutes=d)
        return self.scheduled_end

    @property
    def effective_start(self) -> datetime:
        return self.actual_start or self.scheduled_start

    @property
    def effective_end(self) -> datetime:
        return self.projected_end


@dataclass
class Patient:
    patient_id: str
    priority: int   # 1 = highest priority
    order_id: str = ""
    incubator_id: str = ""
    status: str = "Pending"
    notes: str = ""
