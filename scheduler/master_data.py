from .models import Equipment, EquipmentType

# ── Equipment ──────────────────────────────────────────────────────────────────
DEFAULT_EQUIPMENT: list[Equipment] = (
    [
        Equipment("ROMAG_1", EquipmentType.ROMAG, "Romag 1"),
        Equipment("ROMAG_2", EquipmentType.ROMAG, "Romag 2"),
        Equipment("ROMAG_3", EquipmentType.ROMAG, "Romag 3"),
        Equipment("FILL_1",  EquipmentType.FILL,  "Fill Station"),
        Equipment("BSD_SAMP_1",  EquipmentType.BSD_SAMPLING, "BSD Sampling"),
        Equipment("BSD_WEIGH_1", EquipmentType.BSD_WEIGHING, "BSD Weighing"),
    ]
    + [
        Equipment(f"INC_{i:02d}", EquipmentType.INCUBATOR, f"Incubator {i:02d}")
        for i in range(1, 48)
    ]
)

# ── Process Sequence ───────────────────────────────────────────────────────────
# 10 steps per patient.  duration_min values are defaults editable in Master Data UI.
# robot_types is a list — a segment can require multiple robots simultaneously.
PROCESS_SEQUENCE = [
    {
        "step": 0,
        "phase": "UP_TSA",
        "phase_label": "UP_TSA",
        "phase_key": "UP_TSA",
        "equipment_type": EquipmentType.ROMAG,
        "duration_min": 240,
        # Seg 1: Romag robot. Seg 3 & 5: Incubation robot (material transfer).
        # Seg 5 (Transfer/Unloading): overlap_next_step=True — UP_INC can start as soon as Seg 5 begins.
        "segments": [
            {"name": "Seg 1 – Cell Labelling", "duration_min": 50, "robot_types": ["Romag Robot"],       "robot_duration_min": 5,  "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 2 – Incubation",     "duration_min": 40, "robot_types": [],                   "robot_duration_min": 0,  "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 3 – Wash",           "duration_min": 50, "robot_types": ["Incubation Robot"],  "robot_duration_min": 3,  "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 4 – Resuspension",   "duration_min": 50, "robot_types": [],                   "robot_duration_min": 0,  "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 5 – Transfer",       "duration_min": 50, "robot_types": ["Incubation Robot"],  "robot_duration_min": 10, "max_duration_min": 0, "overlap_next_step": True},
        ],
    },
    {
        "step": 1,
        "phase": "UP_INC_1",
        "phase_label": "UP_INC (1st)",
        "phase_key": "UP_INC",
        "equipment_type": EquipmentType.INCUBATOR,
        "duration_min": 2880,   # 48 h planned; scheduler uses min_duration_min then extends to next step
        "min_duration_min": 120,  # 2 h minimum before patient can move if equipment is available
        "segments": [
            {"name": "Incubation Day 1", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Incubation Day 2", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 2,
        "phase": "UP_BSD_1",
        "phase_label": "UP_BSD (1st)",
        "phase_key": "UP_BSD",
        "equipment_type": EquipmentType.BSD_SAMPLING,
        "duration_min": 120,
        "segments": [
            {"name": "Sample Collection", "duration_min": 60, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Bead Selection",    "duration_min": 60, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 3,
        "phase": "UP_INC_2",
        "phase_label": "UP_INC (2nd)",
        "phase_key": "UP_INC",
        "equipment_type": EquipmentType.INCUBATOR,
        "duration_min": 1440,   # 24 h planned
        "min_duration_min": 120,
        "segments": [
            {"name": "Incubation", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 4,
        "phase": "UP_TxD",
        "phase_label": "UP_TxD",
        "phase_key": "UP_TxD",
        "equipment_type": EquipmentType.ROMAG,
        "duration_min": 360,    # 6 h
        # Seg 1 & 4: Romag robot (5 min each)
        "segments": [
            {"name": "Seg 1 – Transduction Prep", "duration_min": 90, "robot_types": ["Romag Robot"], "robot_duration_min": 5, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 2 – Transduction",      "duration_min": 90, "robot_types": [],             "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 3 – Media Exchange",    "duration_min": 90, "robot_types": [],             "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 4 – Post-Transduction", "duration_min": 90, "robot_types": ["Romag Robot"], "robot_duration_min": 5, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 5,
        "phase": "UP_INC_3",
        "phase_label": "UP_INC (3rd)",
        "phase_key": "UP_INC",
        "equipment_type": EquipmentType.INCUBATOR,
        "duration_min": 2880,   # 48 h planned
        "min_duration_min": 120,
        "segments": [
            {"name": "Incubation Day 1", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Incubation Day 2", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 6,
        "phase": "UP_BSD_2",
        "phase_label": "UP_BSD (2nd)",
        "phase_key": "UP_BSD",
        "equipment_type": EquipmentType.BSD_SAMPLING,
        "duration_min": 120,
        "segments": [
            {"name": "Sample Collection", "duration_min": 60, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Bead Selection",    "duration_min": 60, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 7,
        "phase": "UP_INC_4",
        "phase_label": "UP_INC (4th)",
        "phase_key": "UP_INC",
        "equipment_type": EquipmentType.INCUBATOR,
        "duration_min": 1440,   # 24 h planned
        "min_duration_min": 120,
        "segments": [
            {"name": "Incubation", "duration_min": 1440, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 8,
        "phase": "UP_DHWF",
        "phase_label": "UP_DHWF",
        "phase_key": "UP_DHWF",
        "equipment_type": EquipmentType.ROMAG,
        "duration_min": 480,    # 8 h
        "chain_to_next": True,  # must flow directly into FILL — no holding gap allowed
        # Seg 1: Romag robot. Seg 5 (Final Transfer): Incubation robot.
        "segments": [
            {"name": "Seg 1 – Harvest Prep",   "duration_min": 96, "robot_types": ["Romag Robot"],      "robot_duration_min": 5, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 2 – Cell Harvest",   "duration_min": 96, "robot_types": [],                   "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 3 – Wash",           "duration_min": 96, "robot_types": [],                   "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 4 – Formulation",    "duration_min": 96, "robot_types": [],                   "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seg 5 – Final Transfer", "duration_min": 96, "robot_types": ["Incubation Robot"], "robot_duration_min": 5, "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
    {
        "step": 9,
        "phase": "UP_FILL",
        "phase_label": "UP_FILL",
        "phase_key": "UP_FILL",
        "equipment_type": EquipmentType.FILL,
        "duration_min": 180,    # 3 h
        "segments": [
            {"name": "Fill Setup",   "duration_min": 30,  "robot_types": [],             "robot_duration_min": 0,   "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Filling",      "duration_min": 120, "robot_types": ["Fill Robot"], "robot_duration_min": 120, "max_duration_min": 0, "overlap_next_step": False},
            {"name": "Seal & Label", "duration_min": 30,  "robot_types": [],             "robot_duration_min": 0,   "max_duration_min": 0, "overlap_next_step": False},
        ],
    },
]

# Phase color palette for Gantt charts
PHASE_COLORS = {
    "UP_TSA":  "#2ecc71",
    "UP_INC":  "#3498db",
    "UP_BSD":  "#e67e22",
    "UP_TxD":  "#9b59b6",
    "UP_DHWF": "#1abc9c",
    "UP_FILL": "#e74c3c",
}

# Robot row labels per robot type (shown separately in Gantt)
ROBOT_ROW_LABELS = {
    "Romag Robot":      "🦾 Romag Robot",
    "Incubation Robot": "🔬 Incubation Robot",
    "Fill Robot":       "💊 Fill Robot",
}

# Ordered list used for checkbox columns in the segment editor UI
ROBOT_TYPES_ALL = ["Romag Robot", "Incubation Robot", "Fill Robot"]
