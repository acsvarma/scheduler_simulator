import math
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

from .models import Equipment, EquipmentType, ScheduledBatch, Segment, Patient, BatchStatus
from .master_data import PROCESS_SEQUENCE

# Three independent robot resources:
#   Romag Robot      — used by Romag primary operations
#   Incubation Robot — used by material-transfer segments (some Romag segs, BSD, INC)
#   Fill Robot       — used by Fill station operations
# Each robot calendar is tracked separately; segments declare which robot they need.


class SchedulingEngine:
    def __init__(self, equipment_list: List[Equipment], process_sequence=None):
        self.equipment_list   = equipment_list
        self.process_sequence = process_sequence or PROCESS_SEQUENCE
        self._eq_by_type: Dict[EquipmentType, List[Equipment]] = {}
        for eq in equipment_list:
            self._eq_by_type.setdefault(eq.equipment_type, []).append(eq)

    # ── Equipment calendar helpers ─────────────────────────────────────────────

    def _next_available(
        self,
        eq: Equipment,
        calendar: Dict[str, List[Tuple[datetime, datetime]]],
        earliest: datetime,
        duration_min: int,
    ) -> datetime:
        occupied = sorted(calendar.get(eq.equipment_id, []))
        dur = timedelta(minutes=duration_min)
        candidate = earliest
        for slot_start, slot_end in occupied:
            if candidate + dur <= slot_start:
                break
            if slot_end > candidate:
                candidate = slot_end
        return candidate

    def _book(
        self,
        eq: Equipment,
        calendar: Dict,
        start: datetime,
        end: datetime,
    ):
        calendar.setdefault(eq.equipment_id, []).append((start, end))
        calendar[eq.equipment_id].sort()

    def _rebook_end(
        self,
        eq: Equipment,
        calendar: Dict,
        slot_start: datetime,
        old_end: datetime,
        new_end: datetime,
    ):
        """Extend an existing calendar slot's end time in-place."""
        slots = calendar.get(eq.equipment_id, [])
        for j, (s, e) in enumerate(slots):
            if s == slot_start and e == old_end:
                slots[j] = (s, new_end)
                slots.sort()
                return

    # ── Robot helpers ──────────────────────────────────────────────────────────

    def _robot_offsets(self, step_config: dict) -> List[Tuple[int, int, str, str]]:
        """
        Return (start_offset_min, end_offset_min, segment_name, robot_type) for every
        robot used by every segment in a step, relative to batch start.
        A segment requiring multiple robots produces one entry per robot.
        """
        offsets: List[Tuple[int, int, str, str]] = []
        cumulative = 0
        for seg in step_config.get("segments", []):
            rtypes = seg.get("robot_types") or []
            if rtypes:
                rdur = seg.get("robot_duration_min") or seg["duration_min"]
                for rtype in rtypes:
                    offsets.append((cumulative, cumulative + rdur, seg["name"], rtype))
            cumulative += seg["duration_min"]
        return offsets

    def _robot_conflict_push(
        self,
        candidate: datetime,
        robot_offsets: List[Tuple[int, int, str, str]],
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]],
    ) -> Optional[datetime]:
        """
        Check all robot windows for candidate start against each typed robot calendar.
        Returns the earliest required new candidate start if there is any conflict, else None.
        """
        push_to: Optional[datetime] = None
        for s_off, e_off, _, rtype in robot_offsets:
            win_s = candidate + timedelta(minutes=s_off)
            win_e = candidate + timedelta(minutes=e_off)
            for rs, re in robot_cals.get(rtype, []):
                if win_s < re and win_e > rs:           # overlap
                    needed = re - timedelta(minutes=s_off)
                    if push_to is None or needed > push_to:
                        push_to = needed
        return push_to

    def _find_valid_start_with_robot(
        self,
        eq: Equipment,
        eq_cal: Dict,
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]],
        earliest: datetime,
        step_config: dict,
    ) -> datetime:
        """
        Find earliest start for a batch on `eq` that satisfies both the equipment
        calendar and all required robot calendars for this step's segments.
        """
        duration      = step_config["duration_min"]
        robot_offsets = self._robot_offsets(step_config)
        candidate     = self._next_available(eq, eq_cal, earliest, duration)

        if not robot_offsets:
            return candidate

        for _ in range(200):
            push_to = self._robot_conflict_push(candidate, robot_offsets, robot_cals)
            if push_to is None:
                break
            candidate = self._next_available(eq, eq_cal, push_to, duration)

        return candidate

    def _best_romag(
        self,
        eq_cal: Dict,
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]],
        earliest: datetime,
        step_config: dict,
    ) -> Tuple[Equipment, datetime]:
        """Among all available Romags, pick the one giving earliest valid start."""
        best_eq: Optional[Equipment] = None
        best_start: Optional[datetime] = None
        for eq in self._eq_by_type.get(EquipmentType.ROMAG, []):
            if not eq.is_available:
                continue
            start = self._find_valid_start_with_robot(eq, eq_cal, robot_cals, earliest, step_config)
            if best_start is None or start < best_start:
                best_start = start
                best_eq    = eq
        if best_eq is None:
            raise RuntimeError("No Romag equipment available")
        return best_eq, best_start

    def _book_robot(
        self,
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]],
        batch_start: datetime,
        step_config: dict,
    ):
        for s_off, e_off, _, rtype in self._robot_offsets(step_config):
            robot_cals.setdefault(rtype, []).append((
                batch_start + timedelta(minutes=s_off),
                batch_start + timedelta(minutes=e_off),
            ))
            robot_cals[rtype].sort()

    # ── Overlap-next-step helper ───────────────────────────────────────────────

    @staticmethod
    def _step_overlap_tail_min(step_config: dict) -> int:
        """
        Sum of durations of trailing segments marked overlap_next_step=True.
        Only a contiguous run from the END counts — a non-overlap segment stops
        the count so that mid-step overlap flags have no effect.
        """
        total = 0
        for seg in reversed(step_config.get("segments", [])):
            if seg.get("overlap_next_step"):
                total += seg["duration_min"]
            else:
                break
        return total

    # ── DHWF → FILL chained scheduling ───────────────────────────────────────

    def _schedule_chained(
        self,
        step: dict,
        next_step: dict,
        eq_cal: Dict,
        robot_cals: Dict,
        earliest: datetime,
        fill_gap_max_min: int = 0,
        dhwf_deadline: Optional[datetime] = None,
    ) -> Tuple[Equipment, datetime]:
        """
        Schedule DHWF so the gap between DHWF end and FILL start is within
        fill_gap_max_min (0 = must chain immediately).  Iterates until
        Romag + Fill availability align within the allowed window.

        dhwf_deadline caps how late DHWF may start (INC4 timing constraint).
        When Fill alignment would push DHWF past the deadline, we stop there
        and accept the Fill gap rather than violating the INC4 deadline.
        """
        dur = step["duration_min"]
        next_eqs = [e for e in self._eq_by_type.get(next_step["equipment_type"], []) if e.is_available]
        if not next_eqs:
            return self._best_romag(eq_cal, robot_cals, earliest, step)

        candidate = earliest
        for _ in range(50):
            eq, start = self._best_romag(eq_cal, robot_cals, candidate, step)

            # Never push DHWF past the INC4 deadline
            if dhwf_deadline is not None and start > dhwf_deadline:
                eq, start = self._best_romag(eq_cal, robot_cals, earliest, step)
                return eq, min(start, dhwf_deadline) if False else (eq, start)

            dhwf_end = start + timedelta(minutes=dur)

            # Earliest time Fill (including its robots) is available after dhwf_end
            fill_start = min(
                self._find_valid_start_with_robot(nq, eq_cal, robot_cals, dhwf_end, next_step)
                for nq in next_eqs
            )

            # Compliant: Fill starts within allowed gap
            if fill_start <= dhwf_end + timedelta(minutes=fill_gap_max_min):
                return eq, start

            # Fill is delayed beyond the allowed window.
            # Push DHWF later so it ends right when Fill becomes free.
            desired = fill_start - timedelta(minutes=dur)

            # Don't push past the INC4→DHWF deadline
            if dhwf_deadline is not None and desired > dhwf_deadline:
                return eq, start  # accept Fill gap — INC4 deadline takes priority

            if desired <= candidate:
                return eq, start  # no progress possible — accept current timing
            candidate = desired

        eq, start = self._best_romag(eq_cal, robot_cals, candidate, step)
        return eq, start

    # ── Incubator assignment ───────────────────────────────────────────────────

    def _assign_incubator(
        self,
        patient: Patient,
        assigned: Dict[str, str],
        eq_cal: Dict[str, List[Tuple[datetime, datetime]]],
        earliest: datetime,
    ) -> Equipment:
        if patient.incubator_id:
            eq = next((e for e in self.equipment_list if e.equipment_id == patient.incubator_id), None)
            if eq:
                return eq
        taken  = set(assigned.values())
        avail  = [e for e in self._eq_by_type.get(EquipmentType.INCUBATOR, []) if e.is_available]
        if not avail:
            raise RuntimeError(f"No incubator equipment available for patient {patient.patient_id}")
        # Prefer a completely unassigned incubator first
        free = [e for e in avail if e.equipment_id not in taken]
        if free:
            return free[0]
        # All 47 slots already assigned in this scheduling run.
        # Pick the one whose last booked slot ends soonest — the patient's INC steps
        # will naturally be pushed to after that slot via _find_valid_start_with_robot.
        def _last_end(eq: Equipment) -> datetime:
            slots = eq_cal.get(eq.equipment_id, [])
            return max((s[1] for s in slots), default=earliest)
        return min(avail, key=_last_end)

    # ── Joint incubator + ROMAG optimisation for patient introduction ─────────

    def _joint_tsa_start(
        self,
        patient: Patient,
        eq_cal: Dict[str, List[Tuple[datetime, datetime]]],
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]],
        assigned_incubators: Dict[str, str],
        earliest: datetime,
        tsa_step: dict,
    ) -> Tuple:
        """Return (incubator, romag_equipment, start_dt) for the earliest UP_TSA start.

        Co-optimises the incubator and ROMAG assignment: for each candidate
        incubator, find the earliest ROMAG+robot slot after the incubator is free,
        then pick whichever (incubator, ROMAG) pair gives the smallest start time.
        This prevents the common failure where the incubator frees at T+10h but the
        ROMAG is free at T+0 (or vice versa), causing an unnecessary wait.
        """
        if patient.incubator_id:
            fixed = next(
                (e for e in self.equipment_list if e.equipment_id == patient.incubator_id), None
            )
            candidates = [fixed] if fixed else []
        else:
            taken      = set(assigned_incubators.values())
            all_incs   = [e for e in self._eq_by_type.get(EquipmentType.INCUBATOR, []) if e.is_available]
            candidates = [e for e in all_incs if e.equipment_id not in taken]

        if not candidates:
            # All incubators assigned — pick the one that will free up soonest.
            # Phase A only books Romag (not incubators), so eq_cal has no incubator
            # entries yet.  Fall back to assignment-order as a proxy: the incubator
            # assigned to the earliest-introduced patient frees first (same cycle time).
            all_incs = [e for e in self._eq_by_type.get(EquipmentType.INCUBATOR, []) if e.is_available]
            if not all_incs:
                raise RuntimeError(f"No incubator available for patient {patient.patient_id}")
            # Build free-time estimate: eq_cal booking end if known, else assignment order
            inc_order = {inc_id: i for i, inc_id in enumerate(assigned_incubators.values())}
            # Estimate time-to-DHWF from process sequence so we push patient intro
            # to after the incubator will actually be free
            dhwf_idx = next(
                (i for i, s in enumerate(self.process_sequence) if s.get("phase") == "UP_DHWF"), -1
            )
            est_occupancy = sum(
                s["duration_min"] for s in (self.process_sequence[:dhwf_idx] if dhwf_idx >= 0 else [])
            )

            def _est_free(inc_eq: Equipment) -> datetime:
                slots = eq_cal.get(inc_eq.equipment_id, [])
                if slots:
                    return max(s[1] for s in slots)
                order = inc_order.get(inc_eq.equipment_id, 9999)
                return earliest + timedelta(minutes=order * est_occupancy)

            candidates = [min(all_incs, key=_est_free)]

        best: Optional[Tuple] = None   # (incubator, romag_eq, start_dt)
        for inc in candidates:
            slots    = eq_cal.get(inc.equipment_id, [])
            inc_free = max((s[1] for s in slots), default=earliest)
            eff_t    = max(earliest, inc_free)
            eq, start = self._best_romag(eq_cal, robot_cals, eff_t, tsa_step)
            if best is None or start < best[2]:
                best = (inc, eq, start)

        return best   # always non-None: candidates is guaranteed non-empty

    # ── Primary schedule builder ───────────────────────────────────────────────

    def schedule(
        self,
        patients: List[Patient],
        schedule_start: datetime,
        eq_efficiency: Optional[Dict[str, float]] = None,
        min_intro_interval_min: int = 0,
        inc4_to_dhwf_max_min: int = 0,
        fill_gap_max_min: int = 0,
    ) -> List[ScheduledBatch]:
        eff = eq_efficiency or {}

        def _effective_duration(nominal_min: int, eq_type: EquipmentType) -> int:
            pct = max(1.0, float(eff.get(eq_type.value, 100)))
            return int(math.ceil(nominal_min * 100.0 / pct))

        def _make_segments(patient: Patient, step: dict) -> List[Segment]:
            return [
                Segment(
                    segment_id=f"{patient.patient_id}_{step['phase']}_S{i}",
                    segment_name=s["name"],
                    target_duration_min=s["duration_min"],
                    sequence=i,
                    robot_types=list(s.get("robot_types") or []),
                    robot_duration_min=s.get("robot_duration_min", 0),
                    max_duration_min=s.get("max_duration_min", 0),
                    overlap_next_step=bool(s.get("overlap_next_step", False)),
                    std_dev_sec=int(s.get("std_dev_sec", 0) or 0),
                    max_duration_type=str(s.get("max_duration_type", "fixed") or "fixed"),
                )
                for i, s in enumerate(step.get("segments", []))
            ]

        sorted_patients = sorted(patients, key=lambda p: p.priority)
        eq_cal:    Dict[str, List[Tuple[datetime, datetime]]] = {}
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]] = {}
        assigned_incubators: Dict[str, str] = {}
        all_batches: List[ScheduledBatch] = []

        tsa_step    = self.process_sequence[0]
        tsa_eff_dur = _effective_duration(tsa_step["duration_min"], EquipmentType.ROMAG)

        # ── PHASE A: Plan all patient introductions before scheduling any other steps ──
        #
        # By pre-booking every patient's UP_TSA (ROMAG + Romag Robot) now, Phase B's
        # TxD and DHWF steps automatically yield to upcoming introduction windows
        # rather than blocking them.  This is the key change from reactive
        # ("wait until free") to proactive ("plan introductions first, fit other
        # work around them").
        #
        intro_plan: Dict[str, Tuple] = {}   # patient_id → (incubator, romag_eq, start, end)
        last_intro_start: Optional[datetime] = None
        for patient in sorted_patients:
            earliest_intro = schedule_start
            if min_intro_interval_min > 0 and last_intro_start is not None:
                earliest_intro = max(schedule_start, last_intro_start + timedelta(minutes=min_intro_interval_min))
            inc, romag_eq, start = self._joint_tsa_start(
                patient, eq_cal, robot_cals, assigned_incubators, earliest_intro, tsa_step
            )
            last_intro_start = start
            end = start + timedelta(minutes=tsa_eff_dur)
            assigned_incubators[patient.patient_id] = inc.equipment_id
            patient.incubator_id = inc.equipment_id
            intro_plan[patient.patient_id] = (inc, romag_eq, start, end)
            # Commit introduction into the shared calendars so future introductions
            # and all Phase B steps respect this window.
            self._book(romag_eq, eq_cal, start, end)
            self._book_robot(robot_cals, start, tsa_step)

        # ── PHASE B: Schedule remaining steps (INC → FILL) for each patient ──────────
        #
        # For TxD and DHWF (ROMAG steps), _best_romag now sees Phase A's bookings in
        # eq_cal / robot_cals and naturally defers to after any planned introduction
        # window — no explicit logic needed.
        #
        for patient in sorted_patients:
            incubator, romag_eq_0, tsa_start, tsa_end = intro_plan[patient.patient_id]
            current_time   = schedule_start
            patient_batches: List[ScheduledBatch] = []
            prev_inc_info:  Optional[Tuple] = None   # (batch, eq, step_cfg)
            inc4_min_end:   Optional[datetime] = None

            for step_idx, step in enumerate(self.process_sequence):
                eq_type  = step["equipment_type"]
                duration = _effective_duration(step["duration_min"], eq_type)
                min_dur  = step.get("min_duration_min", duration)

                # ── Find start, equipment, booked_end ─────────────────────────
                if step_idx == 0:
                    # Introduction already committed in Phase A — reuse without re-booking.
                    equipment  = romag_eq_0
                    start_step = tsa_start
                    booked_end = tsa_end
                    # skip _book / _book_robot — Phase A already did them

                elif step.get("chain_to_next") and step_idx + 1 < len(self.process_sequence):
                    # Compute INC4→DHWF deadline so _schedule_chained won't chase Fill
                    # alignment past it
                    _dhwf_deadline = None
                    if inc4_to_dhwf_max_min > 0 and inc4_min_end is not None:
                        _dhwf_deadline = inc4_min_end + timedelta(minutes=inc4_to_dhwf_max_min)
                    equipment, start_step = self._schedule_chained(
                        step, self.process_sequence[step_idx + 1],
                        eq_cal, robot_cals, current_time,
                        fill_gap_max_min=fill_gap_max_min,
                        dhwf_deadline=_dhwf_deadline,
                    )
                    booked_end = start_step + timedelta(minutes=duration)
                    self._book(equipment, eq_cal, start_step, booked_end)
                    self._book_robot(robot_cals, start_step, step)

                elif eq_type == EquipmentType.ROMAG:
                    # _best_romag respects Phase A windows because they are already
                    # in eq_cal/robot_cals — TxD/DHWF are planned around introductions.
                    equipment, start_step = self._best_romag(eq_cal, robot_cals, current_time, step)
                    booked_end = start_step + timedelta(minutes=duration)
                    self._book(equipment, eq_cal, start_step, booked_end)
                    self._book_robot(robot_cals, start_step, step)

                elif eq_type == EquipmentType.INCUBATOR:
                    equipment  = incubator
                    start_step = self._find_valid_start_with_robot(
                        equipment, eq_cal, robot_cals, current_time, step
                    )
                    booked_end = start_step + timedelta(minutes=min_dur)
                    self._book(equipment, eq_cal, start_step, booked_end)
                    self._book_robot(robot_cals, start_step, step)

                else:
                    eqs = self._eq_by_type.get(eq_type, [])
                    if not eqs:
                        continue
                    equipment  = eqs[0]
                    start_step = self._find_valid_start_with_robot(
                        equipment, eq_cal, robot_cals, current_time, step
                    )
                    booked_end = start_step + timedelta(minutes=duration)
                    self._book(equipment, eq_cal, start_step, booked_end)
                    self._book_robot(robot_cals, start_step, step)

                # ── Retroactively extend previous INC to cover waiting time ──
                if prev_inc_info is not None and eq_type != EquipmentType.INCUBATOR:
                    prev_batch, prev_eq, prev_step_cfg = prev_inc_info
                    if start_step > prev_batch.scheduled_end:
                        new_end = start_step
                        # Cap extension at step-level max_duration_min if set
                        max_inc_min = prev_step_cfg.get("max_duration_min", 0)
                        if max_inc_min > 0:
                            hard_cap = prev_batch.scheduled_start + timedelta(minutes=max_inc_min)
                            new_end = min(new_end, hard_cap)
                        self._rebook_end(
                            prev_eq, eq_cal,
                            prev_batch.scheduled_start,
                            prev_batch.scheduled_end,
                            new_end,
                        )
                        prev_batch.scheduled_end       = new_end
                        prev_batch.target_duration_min = int(
                            (new_end - prev_batch.scheduled_start).total_seconds() / 60
                        )
                    prev_inc_info = None

                # ── Create and register batch ─────────────────────────────────
                batch = ScheduledBatch(
                    batch_id=f"{patient.patient_id}__{step['phase']}",
                    patient_id=patient.patient_id,
                    phase_name=step["phase"],
                    phase_label=step["phase_label"],
                    phase_key=step["phase_key"],
                    step_index=step["step"],
                    equipment_id=equipment.equipment_id,
                    equipment_type=eq_type,
                    scheduled_start=start_step,
                    scheduled_end=booked_end,
                    target_duration_min=min_dur if eq_type == EquipmentType.INCUBATOR else duration,
                    segments=_make_segments(patient, step),
                    robot_offsets=self._robot_offsets(step),
                )
                all_batches.append(batch)
                patient_batches.append(batch)

                if eq_type == EquipmentType.INCUBATOR:
                    prev_inc_info = (batch, equipment, step)
                    # Track when INC_4 minimum incubation time completes (DHWF deadline anchor)
                    if step["phase"] == "UP_INC_4":
                        inc4_min_end = start_step + timedelta(minutes=step.get("min_duration_min", min_dur))

                # ── Advance current_time ──────────────────────────────────────
                if eq_type == EquipmentType.INCUBATOR:
                    current_time = start_step + timedelta(minutes=min_dur)
                else:
                    overlap_min  = self._step_overlap_tail_min(step)
                    current_time = booked_end - timedelta(minutes=overlap_min)

            # ── Reserve incubator as one continuous block (TSA start → DHWF start) ──
            dhwf_batch = next((b for b in patient_batches if b.phase_name == "UP_DHWF"), None)
            if patient_batches and dhwf_batch:
                inc_block_start = patient_batches[0].scheduled_start
                inc_block_end   = dhwf_batch.scheduled_start
                inc_starts = {
                    b.scheduled_start for b in patient_batches
                    if b.equipment_type == EquipmentType.INCUBATOR
                }
                eq_cal[incubator.equipment_id] = sorted([
                    (s, e) for (s, e) in eq_cal.get(incubator.equipment_id, [])
                    if s not in inc_starts
                ])
                self._book(incubator, eq_cal, inc_block_start, inc_block_end)

            patient.status = "Scheduled"

        # ── Store calendar state for next_intro_windows() ────────────────────
        self._eq_cal             = eq_cal
        self._robot_cals         = robot_cals
        self._assigned_incubators = assigned_incubators

        return all_batches

    # ── Next available introduction windows ────────────────────────────────────

    def next_intro_windows(
        self,
        n: int = 8,
        after_time: Optional[datetime] = None,
        min_interval_min: int = 0,
    ) -> List[datetime]:
        """
        Project the next N patient introduction windows beyond the current schedule.
        Uses the calendar state saved by the last call to schedule().
        Returns a list of datetime objects (TSA start times).
        """
        import copy as _copy
        if not hasattr(self, "_eq_cal"):
            return []

        eq_cal_w     = _copy.deepcopy(self._eq_cal)
        robot_cals_w = _copy.deepcopy(self._robot_cals)
        assigned_w   = dict(self._assigned_incubators)

        tsa_step = self.process_sequence[0]
        tsa_dur  = tsa_step["duration_min"]

        windows: List[datetime] = []
        earliest = after_time or datetime.now()

        for i in range(n):
            if min_interval_min > 0 and windows:
                earliest = max(earliest, windows[-1] + timedelta(minutes=min_interval_min))

            from .models import Patient as _Patient
            dummy = _Patient(f"__SLOT_{i}", i + 9000, "")
            result = self._joint_tsa_start(dummy, eq_cal_w, robot_cals_w, assigned_w, earliest, tsa_step)
            if result is None:
                break
            inc, romag_eq, start = result

            end = start + timedelta(minutes=tsa_dur)
            self._book(romag_eq, eq_cal_w, start, end)
            self._book_robot(robot_cals_w, start, tsa_step)
            assigned_w[dummy.patient_id] = inc.equipment_id

            windows.append(start)
            earliest = start

        return windows

    # ── Reschedule on delay ────────────────────────────────────────────────────

    def _get_step(self, phase_name: str) -> Optional[dict]:
        return next((s for s in self.process_sequence if s["phase"] == phase_name), None)

    def reschedule_from_delay(
        self,
        all_batches: List[ScheduledBatch],
        delayed_batch_id: str,
    ) -> List[ScheduledBatch]:
        """
        1. Cascade the delay to the same patient's downstream scheduled batches.
        2. Detect equipment conflicts caused by the cascade and push other patients.
        3. Rebuild per-type robot calendars from committed batches, then re-resolve
           robot conflicts for all pending batches that use any robot — enabling
           squeeze-in when a delay frees a robot slot.
        """
        delayed = next((b for b in all_batches if b.batch_id == delayed_batch_id), None)
        if delayed is None:
            return all_batches

        delay_min = delayed.delay_min
        if delay_min <= 0:
            return all_batches

        delta     = timedelta(minutes=delay_min)
        patient_id = delayed.patient_id
        step_idx   = delayed.step_index

        # Step 1 — cascade to same patient's downstream batches
        for b in all_batches:
            if (b.patient_id == patient_id
                    and b.step_index > step_idx
                    and b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)):
                b.scheduled_start += delta
                b.scheduled_end   += delta

        # Step 2 — resolve equipment conflicts across patients (up to 3 passes)
        shared = {EquipmentType.ROMAG, EquipmentType.BSD_SAMPLING, EquipmentType.FILL}
        for _ in range(3):
            any_conflict = False
            by_eq: Dict[str, List[ScheduledBatch]] = {}
            for b in all_batches:
                if b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING):
                    by_eq.setdefault(b.equipment_id, []).append(b)

            for eq_batches in by_eq.values():
                if not eq_batches or eq_batches[0].equipment_type not in shared:
                    continue
                sorted_eq = sorted(eq_batches, key=lambda b: b.scheduled_start)
                for i in range(1, len(sorted_eq)):
                    prev, curr = sorted_eq[i - 1], sorted_eq[i]
                    if curr.scheduled_start < prev.scheduled_end:
                        push = prev.scheduled_end - curr.scheduled_start
                        curr.scheduled_start += push
                        curr.scheduled_end   += push
                        for b in all_batches:
                            if (b.patient_id == curr.patient_id
                                    and b.step_index > curr.step_index
                                    and b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)):
                                b.scheduled_start += push
                                b.scheduled_end   += push
                        any_conflict = True
            if not any_conflict:
                break

        # Step 3 — re-resolve robot conflicts for all pending batches with robot usage.
        # Rebuild robot calendars from committed (in-progress / complete) batches only,
        # across ALL equipment types.
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]] = {}
        for b in all_batches:
            if b.status in (BatchStatus.IN_PROGRESS, BatchStatus.COMPLETE):
                for rs, re, _, rtype in b.robot_windows:
                    robot_cals.setdefault(rtype, []).append((rs, re))
        for rtype in robot_cals:
            robot_cals[rtype].sort()

        # Equipment calendar from committed batches
        eq_cal: Dict[str, List[Tuple[datetime, datetime]]] = {}
        for b in all_batches:
            if b.status in (BatchStatus.IN_PROGRESS, BatchStatus.COMPLETE):
                eq_cal.setdefault(b.equipment_id, []).append(
                    (b.effective_start, b.effective_end)
                )

        # Re-slot all pending batches that have any robot usage, in schedule order
        pending_robot = sorted(
            [b for b in all_batches
             if b.robot_offsets
             and b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)],
            key=lambda b: b.scheduled_start,
        )

        for b in pending_robot:
            step = self._get_step(b.phase_name)
            if step is None:
                continue
            eq = next((e for e in self.equipment_list if e.equipment_id == b.equipment_id), None)
            if eq is None:
                continue

            new_start = self._find_valid_start_with_robot(
                eq, eq_cal, robot_cals, b.scheduled_start, step
            )

            if new_start != b.scheduled_start:
                push = new_start - b.scheduled_start
                b.scheduled_start = new_start
                b.scheduled_end   = new_start + timedelta(minutes=step["duration_min"])
                for downstream in all_batches:
                    if (downstream.patient_id == b.patient_id
                            and downstream.step_index > b.step_index
                            and downstream.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)):
                        downstream.scheduled_start += push
                        downstream.scheduled_end   += push

            self._book(eq, eq_cal, b.scheduled_start, b.scheduled_end)
            self._book_robot(robot_cals, b.scheduled_start, step)

        return all_batches

    # ── Full re-slot of pending batches ────────────────────────────────────────

    def _resolve_pending_batches(
        self,
        all_batches: List[ScheduledBatch],
    ) -> List[ScheduledBatch]:
        """
        Rebuild equipment + robot calendars from committed batches, then find the
        earliest valid start for EVERY pending batch in (patient priority, step) order.

        - Batches that can move earlier (freed slots) are pulled forward.
        - Batches that conflict are pushed out.
        - Equipment assignments are preserved; only timing changes.
        """
        # Rebuild calendars from committed work
        eq_cal: Dict[str, List[Tuple[datetime, datetime]]] = {}
        robot_cals: Dict[str, List[Tuple[datetime, datetime]]] = {}
        for b in all_batches:
            if b.status in (BatchStatus.IN_PROGRESS, BatchStatus.COMPLETE):
                eq_cal.setdefault(b.equipment_id, []).append(
                    (b.effective_start, b.effective_end)
                )
                for rs, re, _, rtype in b.robot_windows:
                    robot_cals.setdefault(rtype, []).append((rs, re))
        for lst in eq_cal.values():
            lst.sort()
        for lst in robot_cals.values():
            lst.sort()

        # Patient priority proxy: earliest first-batch start across ALL batches
        patient_first: Dict[str, datetime] = {}
        for b in all_batches:
            if b.patient_id not in patient_first or b.scheduled_start < patient_first[b.patient_id]:
                patient_first[b.patient_id] = b.scheduled_start

        # Sort pending: highest-priority patient first, then step order within patient
        pending = sorted(
            [b for b in all_batches if b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)],
            key=lambda b: (patient_first.get(b.patient_id, b.scheduled_start), b.step_index),
        )

        for b in pending:
            step = self._get_step(b.phase_name)
            if step is None:
                continue
            eq = next((e for e in self.equipment_list if e.equipment_id == b.equipment_id), None)
            if eq is None:
                continue

            new_start = self._find_valid_start_with_robot(
                eq, eq_cal, robot_cals, b.scheduled_start, step
            )
            new_end = new_start + timedelta(minutes=step["duration_min"])

            if new_start != b.scheduled_start:
                push = new_start - b.scheduled_start
                b.scheduled_start = new_start
                b.scheduled_end   = new_end
                if push > timedelta(0):
                    # A positive push must cascade to this patient's later steps
                    for ds in all_batches:
                        if (ds.patient_id == b.patient_id
                                and ds.step_index > b.step_index
                                and ds.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)):
                            ds.scheduled_start += push
                            ds.scheduled_end   += push
                # Negative push (pull-forward) does NOT cascade — each downstream
                # batch is individually advanced when its turn comes in this loop.
            else:
                b.scheduled_end = new_end

            self._book(eq, eq_cal, b.scheduled_start, b.scheduled_end)
            self._book_robot(robot_cals, b.scheduled_start, step)

        return all_batches

    # ── Reschedule on early completion ─────────────────────────────────────────

    def reschedule_from_early_completion(
        self,
        all_batches: List[ScheduledBatch],
        completed_batch_id: str,
    ) -> List[ScheduledBatch]:
        """
        When a batch finishes earlier than scheduled:
        1. Tentatively pull the same patient's downstream batches forward.
        2. Re-resolve ALL pending batches against the actual calendars so freed
           equipment/robot slots benefit the highest-priority work and other patients
           are pushed out only where there is a genuine conflict.
        """
        completed = next((b for b in all_batches if b.batch_id == completed_batch_id), None)
        if completed is None or completed.actual_end is None:
            return all_batches

        early_min = int((completed.scheduled_end - completed.actual_end).total_seconds() / 60)
        if early_min <= 0:
            return all_batches

        delta      = timedelta(minutes=early_min)
        patient_id = completed.patient_id
        step_idx   = completed.step_index

        # Advance same-patient downstream batches — floor each at actual_end so we
        # never schedule a step before its predecessor actually finished.
        prev_earliest = completed.actual_end
        downstream = sorted(
            [b for b in all_batches
             if b.patient_id == patient_id
             and b.step_index > step_idx
             and b.status in (BatchStatus.SCHEDULED, BatchStatus.PENDING)],
            key=lambda x: x.step_index,
        )
        for b in downstream:
            new_start = max(b.scheduled_start - delta, prev_earliest)
            b.scheduled_start = new_start
            b.scheduled_end   = new_start + timedelta(minutes=b.target_duration_min)
            prev_earliest     = b.scheduled_end   # next step floored by this one's end

        # Re-resolve everything: pulls forward other patients where possible,
        # pushes them out only when a real conflict exists.
        return self._resolve_pending_batches(all_batches)
