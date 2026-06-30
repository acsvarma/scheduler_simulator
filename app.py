"""Production Scheduler — Streamlit application — BMS Theme."""

import copy
import io
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scheduler.models import Patient, Equipment, EquipmentType, ScheduledBatch, BatchStatus
from scheduler.master_data import DEFAULT_EQUIPMENT, PROCESS_SEQUENCE, PHASE_COLORS, ROBOT_ROW_LABELS, ROBOT_TYPES_ALL
from scheduler.engine import SchedulingEngine
from scheduler.simulation import SimulationEngine
from scheduler.interfaces.sap import SAPInterface
from scheduler.interfaces.deltav import DeltaVInterface
from scheduler.session_io import save_to_file, load_from_file, dump_session, SESSION_FILE

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Scheduler Simulator",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── SIRIUS Theme CSS (matches BMS SIRIUS MES UI) ──────────────────────────────
BMS_CSS = """
<style>
/* ── BMS Brand Palette (from styleguide V6 / bookmarks-shareable) ── */
/* --bms-purple: #BE2BBB  --bms-purple-hover: #9E1F9A
   --bms-white: #FFFFFF   --bms-light-gray: #EEE7E7
   --bms-gray: #A69F9F    --bms-dark-gray: #595454      */

/* ── Global ── */
html, body, [class*="css"] {
    font-family: "Trebuchet MS", "Lucida Sans Unicode", "Segoe UI", Tahoma, Verdana, sans-serif !important;
}

/* ── App background ── */
.stApp { background: linear-gradient(135deg, #f8f6f6 0%, #ffffff 100%) !important; }
.main .block-container {
    padding-top: 0.75rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
}

/* ── Top header bar ── */
[data-testid="stHeader"] {
    background-color: #BE2BBB !important;
    border-bottom: 1px solid #9E1F9A !important;
}

/* ── Sidebar — white panel ── */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid rgba(89,84,84,0.15) !important;
}
section[data-testid="stSidebar"] * { color: #595454 !important; }
section[data-testid="stSidebar"] hr { border-color: #EEE7E7 !important; }

/* Nav radio items */
section[data-testid="stSidebar"] .stRadio label {
    padding: 5px 8px !important;
    border-radius: 6px !important;
    transition: background 0.15s !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(238,231,231,0.7) !important;
}
/* Active nav item — purple left border */
section[data-testid="stSidebar"] .stRadio label:has(input:checked) {
    background: rgba(190,43,187,0.08) !important;
    border-left: 3px solid #BE2BBB !important;
    border-radius: 0 6px 6px 0 !important;
}
section[data-testid="stSidebar"] .stRadio label:has(input:checked) * {
    color: #BE2BBB !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {
    font-size: 13px !important;
}

/* Sidebar metrics */
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #BE2BBB !important;
    font-size: 1.3rem !important;
    font-weight: 700 !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    color: #A69F9F !important;
    font-size: 0.73rem !important;
}
section[data-testid="stSidebar"] [data-testid="metric-container"] {
    background: #EEE7E7 !important;
    border-left: 3px solid #BE2BBB !important;
    border-radius: 0 6px 6px 0 !important;
}

/* ── Page titles (h1) ── */
h1 {
    color: #BE2BBB !important;
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    border-bottom: 3px solid #BE2BBB !important;
    padding-bottom: 6px !important;
    margin-bottom: 1rem !important;
    letter-spacing: 0.3px !important;
}

/* ── Section headers ── */
h2 { color: #595454 !important; font-size: 1.05rem !important; font-weight: 700 !important; }
h3 { color: #595454 !important; font-size: 0.95rem !important; font-weight: 600 !important; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: white !important;
    border: 1px solid rgba(89,84,84,0.15) !important;
    border-left: 5px solid #BE2BBB !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 10px 14px !important;
    box-shadow: 0 3px 12px rgba(89,84,84,0.08) !important;
}
[data-testid="stMetricValue"] { color: #BE2BBB !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #A69F9F !important; font-size: 0.75rem !important; text-transform: uppercase !important; letter-spacing: 0.8px !important; }

/* ── Buttons ── */
.stButton > button {
    border-radius: 6px !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 0.4px !important;
    text-transform: uppercase !important;
    transition: all 0.15s ease !important;
    height: 34px !important;
    padding: 0 16px !important;
}
/* Primary — BMS purple */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background-color: #BE2BBB !important;
    border: 1px solid #BE2BBB !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="baseButton-primary"]:hover {
    background-color: #9E1F9A !important;
    border-color: #9E1F9A !important;
    box-shadow: 0 4px 12px rgba(190,43,187,0.30) !important;
}
/* Secondary — white outlined */
.stButton > button[kind="secondary"],
.stButton > button[data-testid="baseButton-secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid rgba(89,84,84,0.25) !important;
    color: #595454 !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: rgba(190,43,187,0.06) !important;
    border-color: #BE2BBB !important;
    color: #BE2BBB !important;
    box-shadow: 0 2px 8px rgba(190,43,187,0.10) !important;
}

/* ── Download buttons ── */
.stDownloadButton > button {
    background: #FFFFFF !important;
    border: 1px solid rgba(89,84,84,0.25) !important;
    color: #595454 !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 0.4px !important;
    text-transform: uppercase !important;
    height: 34px !important;
}
.stDownloadButton > button:hover {
    border-color: #BE2BBB !important;
    color: #BE2BBB !important;
    background: rgba(190,43,187,0.06) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: white !important;
    border-bottom: 2px solid rgba(89,84,84,0.15) !important;
    padding: 0 4px !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    color: #A69F9F !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    padding: 8px 18px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important;
    letter-spacing: 0.4px !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #BE2BBB !important;
    background: rgba(190,43,187,0.06) !important;
}
.stTabs [aria-selected="true"] {
    color: #BE2BBB !important;
    font-weight: 700 !important;
    background: white !important;
}
.stTabs [data-baseweb="tab-highlight"] { background-color: #BE2BBB !important; height: 2px !important; }

/* ── Expanders ── */
[data-testid="stExpander"] {
    border: 1px solid rgba(89,84,84,0.15) !important;
    border-radius: 8px !important;
    background: white !important;
    margin-bottom: 6px !important;
    box-shadow: 0 3px 12px rgba(89,84,84,0.08) !important;
}
[data-testid="stExpander"] summary {
    background-color: #EEE7E7 !important;
    border-left: 5px solid #BE2BBB !important;
    color: #595454 !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.6px !important;
    text-transform: uppercase !important;
    padding: 10px 16px !important;
    border-radius: 8px 8px 0 0 !important;
}
[data-testid="stExpander"] summary:hover { background-color: rgba(238,231,231,0.7) !important; }

/* ── Alerts ── */
.stAlert { border-radius: 8px !important; font-size: 13px !important; }

/* ── Inputs & Selects ── */
[data-baseweb="select"] > div:first-child,
[data-baseweb="input"] > div:first-child,
[data-baseweb="textarea"] > div:first-child {
    border-radius: 6px !important;
    border-color: rgba(89,84,84,0.25) !important;
    background: white !important;
    font-size: 13px !important;
}
[data-baseweb="select"] > div:first-child:focus-within,
[data-baseweb="input"] > div:first-child:focus-within {
    border-color: #BE2BBB !important;
    box-shadow: 0 0 0 2px rgba(190,43,187,0.12) !important;
}

/* ── Data tables ── */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(89,84,84,0.15) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    box-shadow: 0 3px 12px rgba(89,84,84,0.08) !important;
}
[data-testid="stDataFrame"] thead tr th {
    background-color: #BE2BBB !important;
    color: white !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 0.8px !important;
    padding: 8px 10px !important;
    text-transform: uppercase !important;
}
[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
    background-color: #EEE7E7 !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background-color: rgba(190,43,187,0.06) !important;
}

/* ── Dividers ── */
hr { border-color: rgba(89,84,84,0.15) !important; margin: 10px 0 !important; }

/* ── Sidebar logo block ── */
.bms-logo-bar {
    background: #BE2BBB;
    margin: -1rem -1rem 0 -1rem;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
    box-shadow: 0 2px 8px rgba(190,43,187,0.30);
}
.bms-logo-text {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    color: white !important;
}
.bms-logo-sub {
    font-size: 9px;
    color: rgba(255,255,255,0.75) !important;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    display: block;
    line-height: 1.2;
}
.sirius-badge {
    background: rgba(255,255,255,0.20);
    color: white !important;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 3px 8px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.35);
}
.nav-section-label {
    font-size: 10px;
    font-weight: 700;
    color: #A69F9F !important;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    padding: 4px 0 2px 0;
}

/* ── Status chips ── */
.chip-effective  { background:#D1FAE5; color:#065F46; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:0.4px; }
.chip-draft      { background:rgba(190,43,187,0.10); color:#BE2BBB; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:0.4px; }
.chip-archived   { background:#EEE7E7; color:#A69F9F; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:0.4px; }
.chip-delayed    { background:#FEF3C7; color:#92400E; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:0.4px; }
.chip-active     { background:rgba(190,43,187,0.15); color:#9E1F9A; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:0.4px; }
</style>
"""
st.markdown(BMS_CSS, unsafe_allow_html=True)

# ── Password gate ──────────────────────────────────────────────────────────────
def _check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown(
        "<div style='max-width:360px;margin:80px auto 0;padding:32px;background:white;"
        "border-radius:12px;box-shadow:0 4px 24px rgba(89,84,84,0.12);"
        "border-top:4px solid #BE2BBB'>"
        "<div style='text-align:center;margin-bottom:24px'>"
        "<span style='font-size:2rem'>💊</span>"
        "<h2 style='color:#BE2BBB;margin:8px 0 4px;font-size:1.2rem'>Scheduler Simulator</h2>"
        "<p style='color:#A69F9F;font-size:12px;margin:0'>Bristol-Myers Squibb</p>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    pwd = st.text_input("Password", type="password", placeholder="Enter access password")
    if st.button("Sign In", type="primary", use_container_width=True):
        expected = st.secrets.get("APP_PASSWORD", "sirius2025")
        if pwd == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not _check_password():
    st.stop()

# ── Equipment type options ──────────────────────────────────────────────────────
EQ_TYPE_OPTIONS = [e.value for e in EquipmentType]
EQ_TYPE_MAP = {e.value: e for e in EquipmentType}

# ── Sequence helpers ───────────────────────────────────────────────────────────

def _new_step(index: int) -> dict:
    return {
        "step": index,
        "phase": f"PHASE_{index+1}",
        "phase_label": f"Phase {index+1}",
        "phase_key": f"PHASE_{index+1}",
        "equipment_type": EquipmentType.ROMAG,
        "duration_min": 240,
        "segments": [{"name": "Main Operation", "duration_min": 240, "robot_types": [], "robot_duration_min": 0, "max_duration_min": 0, "overlap_next_step": False}],
    }


_ROBOT_ICONS = {"Romag Robot": "🦾", "Incubation Robot": "🔬", "Fill Robot": "💊"}


def _renumber(steps: list) -> list:
    for i, s in enumerate(steps):
        s["step"] = i
    return steps


def _deep_copy_seq(seq: list) -> list:
    return copy.deepcopy(seq)

# ── Session-state bootstrap ────────────────────────────────────────────────────
_DEFAULTS = {
    "patients": [],
    "schedule": [],
    "equipment": list(DEFAULT_EQUIPMENT),
    "sequences": {"Default CAR-T": _deep_copy_seq(PROCESS_SEQUENCE)},
    "active_sequence": "Default CAR-T",
    "sap": SAPInterface(),
    "deltav": DeltaVInterface(),
    "sim": SimulationEngine(),
    "engine": None,
    "schedule_start": datetime.now().replace(hour=6, minute=0, second=0, microsecond=0),
    "_seq_edit_name": "",   # name being edited in Master Data
    # ── Equipment efficiency (%) per type — 100 = ideal, lower = slower/more downtime ──
    "eq_efficiency": {
        "Romag":       100,
        "Incubator":   100,
        "BSD Sampling":100,
        "BSD Weighing":100,
        "Fill":        100,
    },
    # ── Scheduling policy controls ─────────────────────────────────────────────
    "reschedule_threshold_min": 0,   # delay threshold before auto-reschedule fires
    "auto_start_grace_min": 0,       # minutes past scheduled_start to auto-mark IN_PROGRESS
    "live_mode": False,              # drive status from system clock automatically
    "_live_auto_batches": set(),     # batch IDs already auto-rescheduled in live mode
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Auto-load from disk on first render ───────────────────────────────────────
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    loaded = load_from_file(SESSION_FILE)
    if loaded:
        for k, v in loaded.items():
            st.session_state[k] = v

# Ensure active sequence still exists after session reload
if st.session_state.active_sequence not in st.session_state.sequences:
    st.session_state.active_sequence = next(iter(st.session_state.sequences))

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # SIRIUS-style header bar inside sidebar
    st.markdown(
        '<div class="bms-logo-bar">'
        '  <div>'
        '    <span class="bms-logo-text">BMS</span>'
        '    <span class="bms-logo-sub">Bristol-Myers Squibb</span>'
        '  </div>'
        '  <div style="margin-left:auto"><span class="sirius-badge">SCHEDULER</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="nav-section-label">Navigation</div>', unsafe_allow_html=True)
    PAGE = st.radio(
        "nav",
        [
            "📊 Dashboard",
            "👥 Patient Orders",
            "📅 Generate Schedule",
            "🔍 Monitor Batches",
            "⏱️ Simulation",
            "⚙️ Master Data",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")

    st.markdown('<div class="nav-section-label">Live Status</div>', unsafe_allow_html=True)
    n_pts     = len(st.session_state.patients)
    n_sched   = len(st.session_state.schedule)
    n_active  = sum(1 for b in st.session_state.schedule if b.status == BatchStatus.IN_PROGRESS)
    n_delayed = sum(1 for b in st.session_state.schedule if b.delay_min > 0)
    c1, c2 = st.columns(2)
    c1.metric("Patients",  n_pts)
    c2.metric("Batches",   n_sched)
    c1.metric("▶ Active",  n_active)
    c2.metric("⚠ Delayed", n_delayed)
    st.markdown("---")
    st.markdown('<div class="nav-section-label">Scheduling Controls</div>', unsafe_allow_html=True)

    st.session_state.live_mode = st.toggle(
        "🟢 Live Clock Mode",
        value=st.session_state.live_mode,
        help="Automatically advance batch status and reschedule based on system clock.",
    )
    st.session_state.reschedule_threshold_min = st.number_input(
        "Reschedule if delay >",
        min_value=0, max_value=240, step=5,
        value=int(st.session_state.reschedule_threshold_min),
        format="%d",
        help="Min delay (min) required to trigger auto-reschedule. 0 = reschedule for any delay.",
    )
    st.session_state.auto_start_grace_min = st.number_input(
        "Auto-start grace (min)",
        min_value=0, max_value=60, step=5,
        value=int(st.session_state.auto_start_grace_min),
        format="%d",
        help="In Live Clock Mode: auto-mark batch IN_PROGRESS this many minutes after scheduled start.",
    )
    st.markdown("---")
    st.markdown('<div class="nav-section-label">Session</div>', unsafe_allow_html=True)

    # Download current session as a shareable file
    session_json = json.dumps(dump_session(st.session_state), indent=2)
    st.download_button(
        "📥 Export session",
        data=session_json,
        file_name="scheduler_session.json",
        mime="application/json",
        use_container_width=True,
        help="Download a file that preserves all patients, schedule, and simulation data. Share it or reload it later.",
    )

    # Upload / restore a session file
    uploaded = st.file_uploader("📂 Import session", type=["json"], label_visibility="collapsed")
    if uploaded:
        try:
            data   = json.loads(uploaded.read().decode("utf-8"))
            from scheduler.session_io import load_session
            loaded = load_session(data)
            for k, v in loaded.items():
                st.session_state[k] = v
            save_to_file(st.session_state, SESSION_FILE)
            st.toast("Session imported.", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Import failed: {exc}")

    st.caption(f"Sequence: **{st.session_state.active_sequence}**")

# ── Shared helpers ─────────────────────────────────────────────────────────────

def _schedule_df() -> pd.DataFrame:
    rows = []
    for b in st.session_state.schedule:
        rows.append({
            "Batch ID":     b.batch_id,
            "Patient":      b.patient_id,
            "Phase":        b.phase_label,
            "Equipment":    b.equipment_id,
            "Sched Start":  b.scheduled_start.strftime("%Y-%m-%d %H:%M"),
            "Sched End":    b.scheduled_end.strftime("%Y-%m-%d %H:%M"),
            "Duration (h)": round(b.target_duration_min / 60, 1),
            "Status":       b.status.value,
            "Delay (min)":  b.delay_min,
            "Actual Start": b.actual_start.strftime("%Y-%m-%d %H:%M") if b.actual_start else "",
            "Actual End":   b.actual_end.strftime("%Y-%m-%d %H:%M")   if b.actual_end   else "",
        })
    return pd.DataFrame(rows)


def _new_order_id() -> str:
    return f"ORD-{datetime.now().year}-{random.randint(1000, 9999)}"


def _gantt(batches: List[ScheduledBatch], y_col: str, color_col: str, color_map=None, show_robot: bool = True, xaxis_range=None, show_segments: bool = False) -> go.Figure:
    if not batches:
        fig = go.Figure()
        fig.update_layout(title="No schedule data yet", paper_bgcolor="#F5F6FA", plot_bgcolor="#F5F6FA")
        return fig

    rows = []
    seg_boundaries = []  # (y_value, x_datetime) for vertical divider lines

    for b in batches:
        seg_summary = (
            " | ".join(s.segment_name for s in sorted(b.segments, key=lambda s: s.sequence))
            if show_segments and b.segments else b.phase_label
        )
        rows.append({
            "Equipment":    b.equipment_id,
            "Patient":      b.patient_id,
            "Phase":        b.phase_label,
            "Phase Key":    b.phase_key,
            "Segment":      seg_summary,
            "Start":        b.effective_start,
            "End":          b.effective_end,
            "Status":       b.status.value,
            "Delay (min)":  b.delay_min,
            "Batch ID":     b.batch_id,
            "Duration (h)": round(b.target_duration_min / 60, 1),
        })
        # Collect internal segment boundary times for vertical divider lines
        if show_segments and b.segments:
            y_val = b.equipment_id if y_col == "Equipment" else b.patient_id
            cursor = b.effective_start
            for seg in sorted(b.segments, key=lambda s: s.sequence)[:-1]:
                cursor += timedelta(minutes=seg.target_duration_min)
                seg_boundaries.append((y_val, cursor))

    # Robot rows (one per robot type) — only on equipment view
    if show_robot and y_col == "Equipment":
        for b in batches:
            for rs, re, seg_name, rtype in b.robot_windows:
                rows.append({
                    "Equipment":    ROBOT_ROW_LABELS.get(rtype, f"🤖 {rtype}"),
                    "Patient":      b.patient_id,
                    "Phase":        f"{b.phase_label} / {seg_name}",
                    "Phase Key":    b.phase_key,
                    "Segment":      seg_name,
                    "Start":        rs,
                    "End":          re,
                    "Status":       b.status.value,
                    "Delay (min)":  0,
                    "Batch ID":     b.batch_id,
                    "Duration (h)": round((re - rs).total_seconds() / 3600, 3),
                })

    df = pd.DataFrame(rows)
    # Preserve insertion order of y categories to match Plotly's axis ordering
    y_order = df[y_col].drop_duplicates().tolist()

    kwargs = dict(
        x_start="Start", x_end="End", y=y_col, color=color_col,
        text="Phase",
        hover_data=["Batch ID", "Phase", "Segment", "Status", "Delay (min)", "Duration (h)"],
        height=max(420, df[y_col].nunique() * 46 + 130),
    )
    if color_map:
        kwargs["color_discrete_map"] = color_map
    fig = px.timeline(df, **kwargs)
    fig.update_traces(textposition="inside", insidetextanchor="middle",
                      textfont=dict(size=11, color="white"))

    # Fix category order so shape y-indices reliably match the rendered row positions
    fig.update_yaxes(categoryorder="array", categoryarray=y_order, autorange="reversed")

    # Draw solid black vertical lines at each segment boundary within the UP bar
    if show_segments and seg_boundaries:
        n = len(y_order)
        for y_val, x_time in seg_boundaries:
            if y_val in y_order:
                y_idx = y_order.index(y_val)
                fig.add_shape(
                    type="line",
                    x0=x_time, x1=x_time,
                    y0=y_idx - 0.45, y1=y_idx + 0.45,
                    xref="x", yref="y",
                    line=dict(color="black", width=2),
                    layer="above",
                )
    xaxis_cfg = dict(gridcolor="#F0F0F0")
    if xaxis_range:
        xaxis_cfg["range"] = xaxis_range
    fig.update_layout(
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        font=dict(family='"Trebuchet MS", "Segoe UI", Arial', color="#595454"),
        xaxis=xaxis_cfg,
    )
    return fig


def _autosave():
    """Write current session to disk silently. Called after every state-changing action."""
    try:
        save_to_file(st.session_state, SESSION_FILE)
    except Exception:
        pass  # never block the UI on a save failure


def _do_generate():
    if not st.session_state.patients:
        st.error("Add at least one patient first.")
        return
    active_seq = st.session_state.sequences[st.session_state.active_sequence]
    engine = SchedulingEngine(st.session_state.equipment, active_seq)
    batches = engine.schedule(
        st.session_state.patients,
        st.session_state.schedule_start,
        eq_efficiency=st.session_state.get("eq_efficiency", {}),
    )
    st.session_state.schedule = batches
    st.session_state.engine  = engine
    st.session_state.sim     = SimulationEngine()
    _autosave()


def _auto_clock_reschedule() -> int:
    """
    Called on every page render when live_mode is on.
    Uses datetime.now() to advance batch status and trigger rescheduling — no user input.
    Returns number of auto-reschedule events fired this call.
    """
    engine = st.session_state.engine
    if not st.session_state.schedule or engine is None:
        return 0

    now       = datetime.now()
    threshold = int(st.session_state.reschedule_threshold_min)
    grace     = int(st.session_state.auto_start_grace_min)
    seen      = st.session_state._live_auto_batches   # set of batch_ids already rescheduled
    fired     = 0

    for b in st.session_state.schedule:
        # ── Auto-start: SCHEDULED → IN_PROGRESS after grace period ──────────────
        if b.status == BatchStatus.SCHEDULED and b.actual_start is None:
            if now >= b.scheduled_start + timedelta(minutes=grace):
                b.actual_start = b.scheduled_start
                b.status       = BatchStatus.IN_PROGRESS

        # ── Auto-reschedule: IN_PROGRESS batch running past scheduled_end ───────
        if b.status == BatchStatus.IN_PROGRESS and b.actual_end is None:
            clock_overrun = int((now - b.scheduled_end).total_seconds() / 60)
            if clock_overrun > threshold:
                # Use current time as projected end so delay_min computes correctly,
                # then call reschedule. Batch stays IN_PROGRESS (not marked complete).
                prev_actual_end = b.actual_end
                b.actual_end    = now
                delay            = b.delay_min
                b.actual_end    = prev_actual_end   # restore — batch still running
                if delay > threshold and b.batch_id not in seen:
                    seen.add(b.batch_id)
                    # Temporarily set for reschedule calculation
                    b.actual_end = now
                    b.status     = BatchStatus.IN_PROGRESS   # keep as in-progress
                    engine.reschedule_from_delay(st.session_state.schedule, b.batch_id)
                    b.actual_end = None   # clear — batch still running
                    fired += 1

    return fired


def _robot_efficiency(batches, span_min: float) -> dict:
    from collections import defaultdict

    if not batches:
        return {}

    # Global schedule start — "ready time" for a patient's very first step
    global_start = min(b.effective_start for b in batches)

    rw_by_type: dict = defaultdict(list)   # rtype -> [(start, end, batch_id)]
    for b in batches:
        for rs, re, _, rtype in b.robot_windows:
            rw_by_type[rtype].append((rs, re, b.batch_id))
    for lst in rw_by_type.values():
        lst.sort()

    by_patient: dict = defaultdict(list)
    for b in batches:
        by_patient[b.patient_id].append(b)
    for pid in by_patient:
        by_patient[pid].sort(key=lambda b: b.step_index)

    def _ready_time(batch):
        """Earliest the patient could have used the robot if it were free."""
        steps = by_patient[batch.patient_id]
        idx = next((i for i, b in enumerate(steps) if b.batch_id == batch.batch_id), -1)
        if idx > 0:
            return steps[idx - 1].effective_end
        # First step: patient is "ready" from the global schedule start.
        # Detecting a gap here reveals that patient introduction was delayed by the robot.
        return global_start

    def _robot_busy(rtype, t_from, t_to, exclude_bid):
        return any(
            rs < t_to and re > t_from
            for rs, re, bid in rw_by_type[rtype]
            if bid != exclude_bid
        )

    result = {}
    for rtype, windows in rw_by_type.items():
        busy_min = sum((re - rs).total_seconds() / 60 for rs, re, _ in windows)
        util_pct = busy_min / span_min * 100 if span_min > 0 else 0

        contention_events = 0
        intro_delays      = 0   # patients whose START was delayed by this robot
        total_wait_min    = 0.0

        seen_bids: set = set()
        for ws, we, bid in windows:
            if bid in seen_bids:
                continue
            seen_bids.add(bid)
            batch = next((b for b in batches if b.batch_id == bid), None)
            if batch is None:
                continue

            ready      = _ready_time(batch)
            step_start = batch.effective_start

            if step_start <= ready:
                continue   # no gap — robot was not a constraint here

            if _robot_busy(rtype, ready, step_start, bid):
                contention_events += 1
                total_wait_min += (step_start - ready).total_seconds() / 60
                if batch.step_index == 0:
                    intro_delays += 1

        avg_wait    = total_wait_min / contention_events if contention_events > 0 else 0.0
        n_patients  = len(by_patient)

        # Influence label — normalised by patient count so it scales correctly
        intro_frac = intro_delays / max(n_patients - 1, 1)   # fraction of patients whose intro was delayed
        if contention_events == 0:
            influence = "Not a constraint"
        elif intro_frac >= 0.5:
            influence = "Bottleneck for patient introduction"
        elif contention_events <= 3:
            influence = "Minor influence"
        elif contention_events <= 8:
            influence = "Moderate bottleneck"
        else:
            influence = "Major bottleneck"

        result[rtype] = {
            "util_pct":          round(util_pct, 1),
            "idle_pct":          round(max(0.0, 100.0 - util_pct), 1),
            "contention_events": contention_events,
            "intro_delays":      intro_delays,
            "total_wait_min":    round(total_wait_min, 1),
            "avg_wait_min":      round(avg_wait, 1),
            "influence":         influence,
        }

    return result


def _throughput_metrics(batches, equipment_list):
    """Compute cycle-time, utilisation, and annual throughput from the schedule."""
    if not batches:
        return {}

    # ── Per-patient cycle time ────────────────────────────────────────────────
    from collections import defaultdict
    pat_starts: dict = defaultdict(list)
    pat_ends:   dict = defaultdict(list)
    for b in batches:
        pat_starts[b.patient_id].append(b.effective_start)
        pat_ends[b.patient_id].append(b.effective_end)

    cycle_mins = {
        pid: (max(pat_ends[pid]) - min(pat_starts[pid])).total_seconds() / 60
        for pid in pat_starts
    }
    avg_cycle_min  = sum(cycle_mins.values()) / len(cycle_mins)
    avg_cycle_days = avg_cycle_min / 1440

    # ── Schedule span and actual throughput ───────────────────────────────────
    all_starts  = [b.effective_start for b in batches]
    all_ends    = [b.effective_end   for b in batches]
    span_min    = (max(all_ends) - min(all_starts)).total_seconds() / 60
    span_days   = span_min / 1440
    n_patients  = len(pat_starts)
    actual_ppy  = (n_patients / span_days * 365) if span_days > 0 else 0

    # ── Equipment utilisation ─────────────────────────────────────────────────
    eq_busy_min: dict = defaultdict(float)
    for b in batches:
        eq_busy_min[b.equipment_id] += b.target_duration_min
    eq_util = {
        eid: min(100.0, busy / span_min * 100)
        for eid, busy in eq_busy_min.items()
        if span_min > 0
    }

    # Robot utilisation
    robot_busy_min: dict = defaultdict(float)
    for b in batches:
        for rs, re, _, rtype in b.robot_windows:
            robot_busy_min[rtype] += (re - rs).total_seconds() / 60
    robot_util = {
        rtype: min(100.0, busy / span_min * 100)
        for rtype, busy in robot_busy_min.items()
        if span_min > 0
    }

    # ── Theoretical max throughput (bottleneck analysis) ─────────────────────
    # For each shared equipment type, compute: (n_units * MINUTES_PER_YEAR) / time_per_patient
    MINS_PER_YEAR = 365 * 24 * 60
    sample_pid   = next(iter(pat_starts))   # use first patient as template
    type_mins: dict = defaultdict(float)    # equipment_type_value → total mins for one patient
    for b in batches:
        if b.patient_id == sample_pid:
            type_mins[b.equipment_type.value] += b.target_duration_min

    n_by_type: dict = defaultdict(int)
    for eq in equipment_list:
        if eq.is_available:
            n_by_type[eq.equipment_type.value] += 1

    theoretical: dict = {}  # type → ppy
    for eq_type_val, mins_per_pt in type_mins.items():
        if mins_per_pt > 0:
            n_units = n_by_type.get(eq_type_val, 1)
            theoretical[eq_type_val] = n_units * MINS_PER_YEAR / mins_per_pt

    bottleneck_type = min(theoretical, key=theoretical.get) if theoretical else "—"
    theoretical_ppy = theoretical.get(bottleneck_type, 0)

    # ── AMS throughput ────────────────────────────────────────────────────────
    # Assumes patients are always available (AMS keeps the queue full).
    # Uses average utilisation of the bottleneck equipment type to scale the
    # theoretical max — reflects real scheduling patterns (shifts, gaps, setup)
    # without being distorted by the small sample window in actual_ppy.
    bn_eqs = [
        eid for eid, _ in eq_util.items()
        if any(
            eq.equipment_id == eid and eq.equipment_type.value == bottleneck_type
            for eq in equipment_list
        )
    ]
    if bn_eqs:
        bn_avg_util = sum(eq_util.get(eid, 0) for eid in bn_eqs) / len(bn_eqs)
    elif eq_util:
        bn_avg_util = sum(eq_util.values()) / len(eq_util)
    else:
        bn_avg_util = 0.0
    ams_ppy = theoretical_ppy * bn_avg_util / 100.0

    # ── Incubator throughput (patients/week) ──────────────────────────────────
    # Incubator is allocated from UP_TSA start → UP_DHWF start (no other patient
    # may use it during this window). Weekly intake = n_incubators / occupancy_days * 7
    by_patient: dict = defaultdict(list)
    for b in batches:
        by_patient[b.patient_id].append(b)

    inc_wall_days = {}
    for pid, pt_batches in by_patient.items():
        tsa  = next((b for b in pt_batches if b.phase_name == "UP_TSA"),  None)
        dhwf = next((b for b in pt_batches if b.phase_name == "UP_DHWF"), None)
        if tsa and dhwf:
            inc_wall_days[pid] = (
                dhwf.effective_start - tsa.effective_start
            ).total_seconds() / 86400
    avg_inc_wall_days = (sum(inc_wall_days.values()) / len(inc_wall_days)) if inc_wall_days else 0.0
    n_incubators = sum(
        1 for eq in equipment_list
        if eq.equipment_type == EquipmentType.INCUBATOR and eq.is_available
    )
    weekly_intake = (n_incubators / avg_inc_wall_days * 7) if avg_inc_wall_days > 0 else 0.0

    return {
        "n_patients":          n_patients,
        "avg_cycle_days":      avg_cycle_days,
        "actual_ppy":          actual_ppy,
        "ams_ppy":             ams_ppy,
        "bn_avg_util":         bn_avg_util,
        "theoretical_ppy":     theoretical_ppy,
        "bottleneck_type":     bottleneck_type,
        "span_days":           span_days,
        "cycle_mins":          cycle_mins,
        "eq_util":             eq_util,
        "robot_util":          robot_util,
        "theoretical":         theoretical,
        "n_incubators":        n_incubators,
        "avg_inc_wall_days":   avg_inc_wall_days,
        "weekly_intake":       weekly_intake,
    }


def _max_efficiency_metrics(equipment_list, process_sequence, eq_efficiency=None):
    """
    Compute theoretical maximum patients/week for each shared resource,
    independent of the simulated schedule.

    Incubator occupancy uses the FULL reservation window (TSA start → DHWF start)
    rather than just INC step durations, because the incubator is locked for the
    entire upstream period.

    Returns (rows, binding_constraint_row) where rows are sorted by max_ppw ascending.
    """
    from collections import defaultdict as _dd

    eff  = eq_efficiency or {}
    MINS = 7 * 24 * 60   # minutes per week (10 080)

    def _eff_dur(nominal, eq_type_val):
        pct = max(1.0, float(eff.get(eq_type_val, 100)))
        return nominal * 100.0 / pct

    # ── Equipment constraints ───────────────────────────────────────────────
    rows = []

    # Find DHWF step index so we can compute full incubator reservation window
    dhwf_idx = next(
        (i for i, s in enumerate(process_sequence) if s.get("phase") == "UP_DHWF"), None
    )

    eq_time: dict = _dd(float)    # eq_type_val → effective min/patient (sum of steps on that type)
    for step in process_sequence:
        et_val = step["equipment_type"].value
        eq_time[et_val] += _eff_dur(step["duration_min"], et_val)

    # Incubator: use the FULL upstream reservation (TSA → DHWF start), not just INC steps
    if dhwf_idx is not None:
        inc_reservation = sum(
            _eff_dur(process_sequence[i]["duration_min"],
                     process_sequence[i]["equipment_type"].value)
            for i in range(dhwf_idx)
        )
        eq_time["Incubator_reservation"] = inc_reservation

    n_by_type: dict = _dd(int)
    for eq in equipment_list:
        if eq.is_available:
            n_by_type[eq.equipment_type.value] += 1

    eq_type_labels = {
        "Romag":               "ROMAG",
        "Incubator":           "Incubator (INC steps only)",
        "Incubator_reservation": "Incubator (full reservation: TSA→DHWF)",
        "BSD Sampling":        "BSD Sampling",
        "BSD Weighing":        "BSD Weighing",
        "Fill":                "Fill Station",
    }

    for et_val, total_min in sorted(eq_time.items()):
        if total_min <= 0:
            continue
        base_val = "Incubator" if et_val == "Incubator_reservation" else et_val
        n_units  = n_by_type.get(base_val, 1)
        ppw      = n_units * MINS / total_min
        rows.append({
            "Resource":            eq_type_labels.get(et_val, et_val),
            "Units":               n_units,
            "Min / Patient":       round(total_min),
            "Max Patients / Week": round(ppw, 1),
            "_sort":               ppw,
            "_is_inc_reservation": et_val == "Incubator_reservation",
        })

    # Remove the "INC steps only" incubator row — the reservation row is the correct one
    rows = [r for r in rows if r["Resource"] != "Incubator (INC steps only)"]

    # ── Robot constraints ───────────────────────────────────────────────────
    robot_time: dict = _dd(float)
    for step in process_sequence:
        for seg in step.get("segments", []):
            for rtype in (seg.get("robot_types") or []):
                robot_time[rtype] += seg.get("robot_duration_min", 0)

    for rtype, total_min in sorted(robot_time.items()):
        if total_min <= 0:
            continue
        ppw = MINS / total_min   # 1 robot per type
        rows.append({
            "Resource":            f"{_ROBOT_ICONS.get(rtype, '🤖')} {rtype}",
            "Units":               1,
            "Min / Patient":       round(total_min),
            "Max Patients / Week": round(ppw, 1),
            "_sort":               ppw,
            "_is_inc_reservation": False,
        })

    rows.sort(key=lambda r: r["_sort"])
    binding = rows[0] if rows else None
    return rows, binding


SAMPLE_PATIENTS = [
    ("PT-001", 1, "ORD-2024-001"),
    ("PT-002", 2, "ORD-2024-002"),
    ("PT-003", 3, "ORD-2024-003"),
]

# ── Live clock auto-reschedule (runs on every render when enabled) ─────────────
if st.session_state.live_mode and st.session_state.schedule and st.session_state.engine:
    _auto_clock_reschedule()

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if PAGE == "📊 Dashboard":
    st.title("Production Schedule Dashboard")

    if not st.session_state.schedule:
        st.info(
            "No schedule yet.  \n"
            "1. **👥 Patient Orders** — add patients  \n"
            "2. **📅 Generate Schedule** — build the plan"
        )
        st.stop()

    batches = st.session_state.schedule
    delayed  = [b for b in batches if b.delay_min > 0]
    complete = [b for b in batches if b.status == BatchStatus.COMPLETE]
    active   = [b for b in batches if b.status == BatchStatus.IN_PROGRESS]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Patients",      len(st.session_state.patients))
    c2.metric("▶ Active",      len(active))
    c3.metric("✅ Completed",  len(complete))
    c4.metric("⚠ Delayed",    len(delayed))

    all_s = [b.effective_start for b in batches]
    all_e = [b.effective_end   for b in batches]
    span  = (max(all_e) - min(all_s)).days + 1
    st.caption(
        f"Schedule: **{min(all_s).strftime('%Y-%m-%d')}** → "
        f"**{max(all_e).strftime('%Y-%m-%d')}**  ({span} days)  |  "
        f"Sequence: **{st.session_state.active_sequence}**"
    )

    tab_eq, tab_pt, tab_tp = st.tabs(["Equipment View", "Patient View", "📈 Throughput"])

    # ── Shared Gantt controls ─────────────────────────────────────────────────
    ctrl_l, ctrl_r = st.columns([4, 1])
    sched_min = min(all_s).replace(second=0, microsecond=0)
    sched_max = max(all_e).replace(second=0, microsecond=0) + timedelta(minutes=1)
    with ctrl_l:
        g_start, g_end = st.slider(
            "Gantt window",
            min_value=sched_min,
            max_value=sched_max,
            value=(sched_min, sched_max),
            step=timedelta(hours=1),
            format="MM/DD HH:mm",
            label_visibility="collapsed",
        )
    with ctrl_r:
        show_segs = st.toggle("Show segments", key="gantt_show_segments", value=False)
    xrange = [g_start, g_end]

    with tab_eq:
        used = {b.equipment_id for b in batches}
        fig = _gantt(
            [b for b in batches if b.equipment_id in used],
            "Equipment", "Patient",
            xaxis_range=xrange, show_segments=show_segs,
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_pt:
        fig = _gantt(
            batches, "Patient", "Phase Key", PHASE_COLORS,
            xaxis_range=xrange, show_segments=show_segs,
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_tp:
        tm = _throughput_metrics(batches, st.session_state.equipment)
        if not tm:
            st.info("No schedule data.")
        else:
            # ── Key metrics ───────────────────────────────────────────────────
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Avg Cycle Time",   f"{tm['avg_cycle_days']:.1f} days")
            m2.metric(
                "Patients / Week",
                f"{tm['weekly_intake']:.1f}",
                help=(
                    f"Max patients that can be introduced per week assuming AMS keeps the queue full. "
                    f"Incubator held from UP_TSA start → UP_DHWF start per patient. "
                    f"Based on {tm['n_incubators']} incubators ÷ "
                    f"{tm['avg_inc_wall_days']:.1f} day avg occupancy × 7."
                ),
            )
            m3.metric(
                "AMS Throughput / Yr",
                f"{tm['ams_ppy']:.0f} pts/yr",
                help=(
                    f"Annual throughput assuming patients are always available (AMS). "
                    f"Based on {tm['bn_avg_util']:.1f}% avg utilisation of the bottleneck "
                    f"({tm['bottleneck_type']}) scaled against theoretical max."
                ),
            )
            m4.metric("Theoretical Max",  f"{tm['theoretical_ppy']:.0f} pts/yr",
                      help=f"Bottleneck: {tm['bottleneck_type']} (100% utilisation, 24/7)")
            m5.metric("Schedule Span",    f"{tm['span_days']:.1f} days")

            st.info(
                f"**Incubator constraint:** {tm['n_incubators']} incubators → max "
                f"**{tm['n_incubators']} concurrent patients**. "
                f"Each patient holds their incubator slot for ~**{tm['avg_inc_wall_days']:.1f} days** "
                f"(UP_TSA start → UP_DHWF start). "
                f"New patient introduced when an incubator **and** Romag Robot are both free — "
                f"others queue automatically."
            )
            st.caption(
                f"Bottleneck: **{tm['bottleneck_type']}** at **{tm['bn_avg_util']:.1f}%** avg utilisation — "
                f"AMS estimate **{tm['ams_ppy']:.0f} pts/yr** "
                f"(theoretical max at 100%: {tm['theoretical_ppy']:.0f} pts/yr)."
            )

            # ── Robot utilisation + efficiency ────────────────────────────────
            re_data = _robot_efficiency(batches, tm["span_days"] * 1440)
            if re_data:
                st.markdown("**Robot Utilisation & Scheduling Influence**")
                rb_cols = st.columns(len(re_data))
                for col, (rtype, rd) in zip(rb_cols, sorted(re_data.items())):
                    icon = _ROBOT_ICONS.get(rtype, "🤖")
                    col.metric(
                        f"{icon} {rtype.replace(' Robot','')}",
                        f"{rd['util_pct']:.1f}%",
                        help=(
                            f"Idle: {rd['idle_pct']:.1f}%  |  "
                            f"Contention events: {rd['contention_events']}  |  "
                            f"Total wait caused: {rd['total_wait_min']:.0f} min"
                        ),
                    )
                    infl_color = {
                        "Not a constraint":                 "green",
                        "Minor influence":                  "orange",
                        "Moderate bottleneck":              "red",
                        "Major bottleneck":                 "red",
                        "Bottleneck for patient introduction": "#BE2BBB",
                    }.get(rd["influence"], "gray")
                    intro_txt = (
                        f" · {rd['intro_delays']} patient intros delayed"
                        if rd["intro_delays"] > 0 else ""
                    )
                    col.markdown(
                        f"<small style='color:{infl_color}'>"
                        f"{rd['influence']} · {rd['contention_events']} events"
                        f"{intro_txt} · avg {rd['avg_wait_min']:.0f} min/event</small>",
                        unsafe_allow_html=True,
                    )

                # Robot efficiency table
                eff_rows = [
                    {
                        "Robot":                   f"{_ROBOT_ICONS.get(rt,'🤖')} {rt}",
                        "Utilisation (%)":         rd["util_pct"],
                        "Idle (%)":                rd["idle_pct"],
                        "Contention Events":       rd["contention_events"],
                        "Patient Intros Delayed":  rd["intro_delays"],
                        "Total Wait (min)":        rd["total_wait_min"],
                        "Avg Wait / Event":        f"{rd['avg_wait_min']:.0f} min",
                        "Scheduling Influence":    rd["influence"],
                    }
                    for rt, rd in sorted(re_data.items())
                ]
                st.dataframe(pd.DataFrame(eff_rows), use_container_width=True, hide_index=True)

            # ── Maximum efficiency analysis ───────────────────────────────────
            st.markdown("---")
            st.markdown("**Maximum Efficiency — Patients / Week by Resource**")
            st.caption(
                "Theoretical ceiling if each resource ran at 100% utilisation 24/7. "
                "The lowest value is the **binding constraint** — adding capacity to any "
                "other resource won't improve throughput until this one is addressed. "
                "Equipment efficiency factors are applied."
            )
            eff_rows, binding = _max_efficiency_metrics(
                st.session_state.equipment,
                st.session_state.sequences[st.session_state.active_sequence],
                st.session_state.get("eq_efficiency", {}),
            )
            if eff_rows:
                bn_ppw = binding["Max Patients / Week"] if binding else 0

                # Metric cards — one per resource, colour-coded by proximity to binding
                eff_cols = st.columns(len(eff_rows))
                for col, row in zip(eff_cols, eff_rows):
                    ppw   = row["Max Patients / Week"]
                    ratio = ppw / bn_ppw if bn_ppw > 0 else 1.0
                    if ratio <= 1.05:
                        badge = "🔴 Binding constraint"
                        color = "#e74c3c"
                    elif ratio <= 1.5:
                        badge = "🟠 Near-bottleneck"
                        color = "#e67e22"
                    else:
                        badge = "🟢 Not constraining"
                        color = "#27ae60"
                    col.metric(
                        label=row["Resource"],
                        value=f"{ppw:.1f} /wk",
                        help=f"{row['Units']} unit(s) × {row['Min / Patient']} min/patient",
                    )
                    col.markdown(
                        f"<small style='color:{color}'>{badge}</small>",
                        unsafe_allow_html=True,
                    )

                # Detail table (hide internal sort key columns)
                display_rows = [
                    {k: v for k, v in r.items() if not k.startswith("_")}
                    for r in eff_rows
                ]
                st.dataframe(
                    pd.DataFrame(display_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                if binding:
                    # Sensitivity: what does adding 1 unit of the binding resource give?
                    n_now  = binding["Units"]
                    min_pp = binding["Min / Patient"]
                    MINS   = 7 * 24 * 60
                    ppw_plus1 = round((n_now + 1) * MINS / min_pp, 1)
                    st.info(
                        f"**Binding constraint: {binding['Resource']}**  "
                        f"({n_now} unit(s), {min_pp} min/patient → **{bn_ppw:.1f} patients/week**).  "
                        f"Adding 1 more unit would raise the ceiling to **{ppw_plus1} patients/week** "
                        f"(+{ppw_plus1 - bn_ppw:.1f}/week, "
                        f"+{round((ppw_plus1 - bn_ppw) * 52)}/year)."
                    )

            col_eq, col_rb = st.columns(2)

            # ── Equipment utilisation ─────────────────────────────────────────
            with col_eq:
                st.markdown("**Equipment Utilisation**")
                eq_rows = sorted(
                    [{"Equipment": eid, "Utilisation (%)": round(u, 1)}
                     for eid, u in tm["eq_util"].items()],
                    key=lambda r: -r["Utilisation (%)"],
                )
                eq_df = pd.DataFrame(eq_rows)
                fig_eq = px.bar(
                    eq_df, x="Utilisation (%)", y="Equipment", orientation="h",
                    color="Utilisation (%)",
                    color_continuous_scale=[[0,"#EEE7E7"],[0.6,"#BE2BBB"],[1,"#7B1878"]],
                    range_x=[0, 100],
                    height=max(300, len(eq_rows) * 22 + 80),
                )
                fig_eq.update_layout(
                    margin=dict(l=0, r=10, t=10, b=10),
                    coloraxis_showscale=False,
                    paper_bgcolor="white", plot_bgcolor="white",
                    font=dict(family='"Trebuchet MS",Arial', size=11),
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            # ── Robot utilisation ─────────────────────────────────────────────
            with col_rb:
                st.markdown("**Robot Utilisation**")
                rb_rows = [
                    {"Robot": rtype, "Utilisation (%)": round(u, 1)}
                    for rtype, u in sorted(tm["robot_util"].items(), key=lambda x: -x[1])
                ]
                if rb_rows:
                    rb_df = pd.DataFrame(rb_rows)
                    fig_rb = px.bar(
                        rb_df, x="Utilisation (%)", y="Robot", orientation="h",
                        color="Utilisation (%)",
                        color_continuous_scale=[[0,"#EEE7E7"],[0.6,"#BE2BBB"],[1,"#7B1878"]],
                        range_x=[0, 100],
                        height=max(200, len(rb_rows) * 50 + 80),
                    )
                    fig_rb.update_layout(
                        margin=dict(l=0, r=10, t=10, b=10),
                        coloraxis_showscale=False,
                        paper_bgcolor="white", plot_bgcolor="white",
                        font=dict(family='"Trebuchet MS",Arial', size=11),
                    )
                    st.plotly_chart(fig_rb, use_container_width=True)

            # ── Throughput by equipment type ──────────────────────────────────
            st.markdown("**Capacity by Equipment Type** *(24/7, all available units)*")
            th_rows = sorted(
                [{"Equipment Type": etype, "Max Patients/Year": round(ppy)}
                 for etype, ppy in tm["theoretical"].items()],
                key=lambda r: r["Max Patients/Year"],
            )
            th_df = pd.DataFrame(th_rows)
            fig_th = px.bar(
                th_df, x="Max Patients/Year", y="Equipment Type", orientation="h",
                color="Max Patients/Year",
                color_continuous_scale=[[0,"#BE2BBB"],[1,"#2ecc71"]],
                height=max(200, len(th_rows) * 42 + 80),
            )
            fig_th.add_vline(
                x=tm["theoretical_ppy"], line_dash="dash", line_color="#E74C3C",
                annotation_text=f"Bottleneck: {tm['theoretical_ppy']:.0f}",
                annotation_position="top right",
            )
            fig_th.update_layout(
                margin=dict(l=0, r=20, t=10, b=10),
                coloraxis_showscale=False,
                paper_bgcolor="white", plot_bgcolor="white",
                font=dict(family='"Trebuchet MS",Arial', size=11),
            )
            st.plotly_chart(fig_th, use_container_width=True)

            # ── Per-patient cycle time table ──────────────────────────────────
            st.markdown("**Patient Cycle Times**")
            ct_rows = [
                {"Patient": pid, "Cycle Time (days)": round(mins / 1440, 1),
                 "Cycle Time (hours)": round(mins / 60, 1)}
                for pid, mins in sorted(tm["cycle_mins"].items())
            ]
            st.dataframe(pd.DataFrame(ct_rows), use_container_width=True, hide_index=True)

    if delayed:
        st.markdown("### ⚠️ Delay Alerts")
        for b in delayed:
            st.warning(
                f"**{b.batch_id}** — {b.phase_label} | {b.patient_id} | "
                f"{b.equipment_id}  →  Delay: **{b.delay_min} min** ({b.delay_min/60:.1f} h)"
            )

    st.markdown("### Schedule Table")
    df = _schedule_df()
    st.dataframe(
        df.style.apply(
            lambda r: ["background-color:#FFE8E8" if r["Delay (min)"] > 0 else "" for _ in r],
            axis=1,
        ),
        use_container_width=True, hide_index=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PATIENT ORDERS
# ══════════════════════════════════════════════════════════════════════════════
elif PAGE == "👥 Patient Orders":
    st.title("Patient Orders")

    col_form, col_list = st.columns([1, 2])

    with col_form:
        st.subheader("Add Patient")
        with st.form("add_patient", clear_on_submit=True):
            pid      = st.text_input("Patient ID *", placeholder="PT-001")
            priority = st.number_input("Priority (1 = highest)", min_value=1, max_value=999, value=1)
            order_id = st.text_input("SAP Order ID", placeholder="ORD-2024-001")
            notes    = st.text_area("Notes", height=60)
            taken    = {p.incubator_id for p in st.session_state.patients if p.incubator_id}
            free_inc = ["Auto-assign"] + [
                eq.equipment_id for eq in st.session_state.equipment
                if eq.equipment_type == EquipmentType.INCUBATOR and eq.equipment_id not in taken
            ]
            inc_choice = st.selectbox("Assign Incubator", free_inc)
            if st.form_submit_button("➕ Add Patient", type="primary"):
                if not pid:
                    st.error("Patient ID is required.")
                elif any(p.patient_id == pid for p in st.session_state.patients):
                    st.error(f"Patient {pid} already exists.")
                else:
                    st.session_state.patients.append(Patient(
                        patient_id=pid, priority=priority,
                        order_id=order_id or _new_order_id(),
                        incubator_id="" if inc_choice == "Auto-assign" else inc_choice,
                        notes=notes,
                    ))
                    _autosave()
                    st.rerun()

        st.markdown("---")
        st.subheader("Bulk Add")
        with st.form("bulk_add_patients", clear_on_submit=True):
            n_bulk   = st.number_input("Number of patients", min_value=1, max_value=100, value=3, step=1)
            id_prefix = st.text_input("Patient ID prefix", value="PT-")
            existing_nums = []
            for p in st.session_state.patients:
                suffix = p.patient_id.replace(id_prefix, "")
                if suffix.isdigit():
                    existing_nums.append(int(suffix))
            start_num = (max(existing_nums) + 1) if existing_nums else 1
            start_num = st.number_input("Starting number", min_value=1, value=start_num, step=1)
            base_priority = st.number_input(
                "Starting priority",
                min_value=1,
                value=(max(p.priority for p in st.session_state.patients) + 1)
                      if st.session_state.patients else 1,
                step=1,
            )
            if st.form_submit_button("➕ Add Patients", type="primary"):
                added = 0
                for i in range(int(n_bulk)):
                    pid = f"{id_prefix}{int(start_num) + i:03d}"
                    if not any(p.patient_id == pid for p in st.session_state.patients):
                        st.session_state.patients.append(Patient(
                            patient_id=pid,
                            priority=int(base_priority) + i,
                            order_id=_new_order_id(),
                        ))
                        added += 1
                if added:
                    _autosave()
                    st.toast(f"Added {added} patients.")
                    st.rerun()
                else:
                    st.warning("All generated IDs already exist.")

        st.markdown("---")
        if st.button("Load 3 sample patients"):
            for s_pid, s_pri, s_oid in SAMPLE_PATIENTS:
                if not any(p.patient_id == s_pid for p in st.session_state.patients):
                    st.session_state.patients.append(
                        Patient(patient_id=s_pid, priority=s_pri, order_id=s_oid)
                    )
            _autosave()
            st.rerun()

        st.markdown("---")
        st.subheader("SAP Mock Orders")
        with st.form("sap_add", clear_on_submit=True):
            s_oid  = st.text_input("Order ID")
            s_pid  = st.text_input("Patient ID")
            s_pri  = st.number_input("Priority", min_value=1, value=1)
            s_prod = st.text_input("Product", value="CAR-T")
            if st.form_submit_button("Add to SAP"):
                if s_oid and s_pid:
                    st.session_state.sap.add_order(s_oid, s_pid, s_prod, s_pri)
                    st.success("Added")
        if st.button("Import All Released SAP Orders"):
            for order in st.session_state.sap.get_released_orders():
                if not any(p.patient_id == order.patient_id for p in st.session_state.patients):
                    st.session_state.patients.append(
                        Patient(patient_id=order.patient_id, priority=order.priority, order_id=order.order_id)
                    )
            _autosave()
            st.rerun()

    with col_list:
        n_pts = len(st.session_state.patients)
        hdr_col, reset_col = st.columns([3, 1])
        hdr_col.subheader(f"Patients ({n_pts})")

        # ── Reset All ─────────────────────────────────────────────────────────
        if n_pts > 0:
            if not st.session_state.get("_confirm_reset_patients"):
                if reset_col.button("🗑 Reset All", type="secondary", use_container_width=True,
                                    help="Remove all patients from the list"):
                    st.session_state["_confirm_reset_patients"] = True
                    st.rerun()
            else:
                reset_col.warning("Are you sure?")
                c_yes, c_no = reset_col.columns(2)
                if c_yes.button("Yes", type="primary", key="reset_yes", use_container_width=True):
                    st.session_state.patients = []
                    st.session_state.schedule = []
                    st.session_state["_confirm_reset_patients"] = False
                    _autosave()
                    st.rerun()
                if c_no.button("No", key="reset_no", use_container_width=True):
                    st.session_state["_confirm_reset_patients"] = False
                    st.rerun()

        if not st.session_state.patients:
            st.info("No patients yet.")
        else:
            # Header row
            h1, h2, h3, h4, h5 = st.columns([1, 2, 2, 2, 1])
            h1.caption("Pri")
            h2.caption("Patient ID")
            h3.caption("Order")
            h4.caption("Status")
            h5.caption("")
            st.divider()

            for p in sorted(st.session_state.patients, key=lambda x: x.priority):
                c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 1])
                c1.write(str(p.priority))
                c2.write(p.patient_id)
                c3.write(p.order_id or "—")
                c4.write(p.status)
                if c5.button("🗑", key=f"rm_{p.patient_id}", help=f"Delete {p.patient_id}"):
                    st.session_state.patients = [
                        x for x in st.session_state.patients
                        if x.patient_id != p.patient_id
                    ]
                    # Remove related schedule batches too
                    st.session_state.schedule = [
                        b for b in st.session_state.schedule
                        if b.patient_id != p.patient_id
                    ]
                    _autosave()
                    st.rerun()
                # Show notes as a small caption under the row if present
                if p.notes:
                    st.caption(f"  ↳ {p.patient_id}: {p.notes}")
                if p.incubator_id:
                    pass  # incubator shown in schedule view, not needed here


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE SCHEDULE
# ══════════════════════════════════════════════════════════════════════════════
elif PAGE == "📅 Generate Schedule":
    st.title("Generate Schedule")

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Parameters")

        # Sequence selector
        seq_names = list(st.session_state.sequences.keys())
        sel_seq = st.selectbox(
            "Process Sequence",
            seq_names,
            index=seq_names.index(st.session_state.active_sequence),
        )
        if sel_seq != st.session_state.active_sequence:
            st.session_state.active_sequence = sel_seq

        active_seq_steps = st.session_state.sequences[st.session_state.active_sequence]
        st.caption(f"{len(active_seq_steps)} steps  |  "
                   f"Total: {sum(s['duration_min'] for s in active_seq_steps)//60}h "
                   f"{sum(s['duration_min'] for s in active_seq_steps)%60}m")

        if st.button("🕐 Use current time", use_container_width=True):
            st.session_state.schedule_start = datetime.now().replace(second=0, microsecond=0)
            st.rerun()
        s_date = st.date_input("Start date", value=st.session_state.schedule_start.date())
        s_time = st.time_input("Start time", value=st.session_state.schedule_start.time())
        st.session_state.schedule_start = datetime.combine(s_date, s_time)

        st.markdown("---")
        st.write(f"**Patients queued:** {len(st.session_state.patients)}")
        for p in sorted(st.session_state.patients, key=lambda x: x.priority):
            st.write(f"  {p.priority}. {p.patient_id}")

        st.markdown("---")
        if st.button("🚀 Generate Schedule", type="primary", use_container_width=True):
            with st.spinner("Scheduling…"):
                _do_generate()
            st.success(f"Done — {len(st.session_state.schedule)} batches scheduled.")
            st.rerun()

        if st.session_state.schedule:
            if st.button("🗑 Clear Schedule", use_container_width=True):
                st.session_state.schedule = []
                st.session_state.engine = None
                st.rerun()
            df = _schedule_df()
            st.download_button("📥 Export CSV",  df.to_csv(index=False), "schedule.csv",  "text/csv", use_container_width=True)
            st.download_button("📥 Export JSON", df.to_json(orient="records", indent=2), "schedule.json", "application/json", use_container_width=True)

    with right:
        if st.session_state.schedule:
            fig = _gantt(st.session_state.schedule, "Equipment", "Patient")
            st.plotly_chart(fig, use_container_width=True)
            st.subheader("Batch Details")
            st.dataframe(_schedule_df(), use_container_width=True, hide_index=True)
        else:
            st.info("Set parameters and click **Generate Schedule**.")


# ══════════════════════════════════════════════════════════════════════════════
# MONITOR BATCHES
# ══════════════════════════════════════════════════════════════════════════════
elif PAGE == "🔍 Monitor Batches":
    st.title("Monitor Batches")

    if not st.session_state.schedule:
        st.info("No schedule yet.")
        st.stop()

    top_l, top_r = st.columns([2, 1])
    with top_l:
        pt_filter = st.selectbox(
            "Filter by Patient",
            ["All"] + sorted({b.patient_id for b in st.session_state.schedule}),
        )
    with top_r:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    batches = st.session_state.schedule
    if pt_filter != "All":
        batches = [b for b in batches if b.patient_id == pt_filter]

    STATUS_ICON = {
        BatchStatus.COMPLETE:    "✅",
        BatchStatus.IN_PROGRESS: "▶️",
        BatchStatus.DELAYED:     "⚠️",
        BatchStatus.SCHEDULED:   "📅",
        BatchStatus.PENDING:     "⏳",
    }

    for pid in sorted({b.patient_id for b in batches}):
        pt_obj = next((p for p in st.session_state.patients if p.patient_id == pid), None)
        st.markdown(
            f"### {pid}  —  Priority {pt_obj.priority if pt_obj else '?'}"
            f"  |  Incubator: **{pt_obj.incubator_id if pt_obj else '?'}**"
        )
        for b in sorted([x for x in batches if x.patient_id == pid], key=lambda x: x.step_index):
            icon  = STATUS_ICON.get(b.status, "❓")
            delay = f" ⚠️ +{b.delay_min} min" if b.delay_min > 0 else ""
            with st.expander(
                f"{icon}  Step {b.step_index+1}: **{b.phase_label}** → {b.equipment_id}"
                f"  |  {b.scheduled_start.strftime('%m/%d %H:%M')} – "
                f"{b.scheduled_end.strftime('%H:%M')}{delay}"
            ):
                r1, r2, r3 = st.columns(3)
                r1.write(f"**Status:** {b.status.value}")
                r1.write(f"**Equipment:** {b.equipment_id}")
                r2.write(f"**Sched Start:** {b.scheduled_start.strftime('%Y-%m-%d %H:%M')}")
                r2.write(f"**Sched End:**   {b.scheduled_end.strftime('%Y-%m-%d %H:%M')}")
                r3.write(f"**Actual Start:** {b.actual_start.strftime('%Y-%m-%d %H:%M') if b.actual_start else '—'}")
                r3.write(f"**Actual End:**   {b.actual_end.strftime('%Y-%m-%d %H:%M')   if b.actual_end   else '—'}")
                if b.delay_min > 0:
                    st.error(f"⚠️ Delay: **{b.delay_min} min** ({b.delay_min/60:.1f} h)")
                if b.segments:
                    st.dataframe(
                        pd.DataFrame([{
                            "Segment":        s.segment_name,
                            "Target (min)":   s.target_duration_min,
                            "Max (min)":      s.max_duration_min if s.max_duration_min > 0 else None,
                            "Max Type":       s.max_duration_type if s.max_duration_type != "fixed" else None,
                            "Overlap":        "Yes" if s.overlap_next_step else None,
                            "Robot":          " ".join(_ROBOT_ICONS.get(r, "🤖") + " " + r for r in s.robot_types) + f" ({s.robot_duration_min}m)" if s.robot_types else None,
                            "Act. Start":     s.actual_start.strftime("%H:%M") if s.actual_start else None,
                            "Act. End":       s.actual_end.strftime("%H:%M")   if s.actual_end   else None,
                            "Actual (min)":   s.actual_duration_min if s.actual_duration_min else None,
                            "Delay (min)":    s.delay_min if s.delay_min > 0 else None,
                            "Status":         s.status,
                        } for s in b.segments]),
                        use_container_width=True, hide_index=True,
                    )
        st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION LOG  (formerly Simulation — manual time entry for MES feed / testing)
# ══════════════════════════════════════════════════════════════════════════════
elif PAGE == "⏱️ Simulation":
    st.title("Execution Log")
    st.caption(
        "Log actual timestamps from equipment/MES. "
        "Rescheduling fires automatically based on the **Scheduling Controls** configured in the sidebar — "
        "no manual confirmation required."
    )

    if not st.session_state.schedule:
        st.warning("Generate a schedule first.")
        st.stop()

    sim: SimulationEngine    = st.session_state.sim
    engine: SchedulingEngine = st.session_state.engine
    _thr = int(st.session_state.reschedule_threshold_min)

    tab_b, tab_s, tab_bulk, tab_io = st.tabs(["Batch Times", "Segment Times", "Bulk CSV", "Export / Import"])

    # ── Batch times ────────────────────────────────────────────────────────────
    with tab_b:
        st.subheader("Log Batch Actual Times")
        sel_id = st.selectbox("Select batch", [b.batch_id for b in st.session_state.schedule])
        batch  = next(b for b in st.session_state.schedule if b.batch_id == sel_id)
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Phase",       batch.phase_label)
        i2.metric("Equipment",   batch.equipment_id)
        i3.metric("Sched Start", batch.scheduled_start.strftime("%m/%d %H:%M"))
        i4.metric("Status",      batch.status.value)

        cs, ce = st.columns(2)
        with cs:
            st.markdown("**Actual Start**")
            d_as = batch.actual_start or batch.scheduled_start
            as_d = st.date_input("Date", value=d_as.date(), key="as_d")
            as_t = st.time_input("Time", value=d_as.time(), key="as_t")
            if st.button("Log Start", type="primary"):
                sim.apply_batch_start(st.session_state.schedule, sel_id, datetime.combine(as_d, as_t))
                _autosave()
                st.rerun()
        with ce:
            st.markdown("**Actual End**")
            d_ae = batch.actual_end or batch.scheduled_end
            ae_d = st.date_input("Date", value=d_ae.date(), key="ae_d")
            ae_t = st.time_input("Time", value=d_ae.time(), key="ae_t")
            if st.button("Log End", type="primary"):
                sim.apply_batch_end(
                    st.session_state.schedule, sel_id,
                    datetime.combine(ae_d, ae_t), engine, _thr,
                )
                st.session_state._live_auto_batches.discard(sel_id)
                _autosave()
                st.rerun()

        if batch.delay_min > 0:
            st.info(f"ℹ️ {batch.batch_id} — delay: **{batch.delay_min} min**. "
                    f"Downstream rescheduled automatically "
                    f"(threshold: {_thr} min).")

    # ── Segment times ──────────────────────────────────────────────────────────
    with tab_s:
        st.subheader("Log Segment Actual Times")
        seg_batches = [b for b in st.session_state.schedule if b.segments]
        if not seg_batches:
            st.info("No batches with segments.")
        else:
            sb_id   = st.selectbox("Select batch",   [b.batch_id    for b in seg_batches], key="seg_b")
            sb      = next(b for b in seg_batches if b.batch_id == sb_id)
            seg_nm  = st.selectbox("Select segment", [s.segment_name for s in sb.segments])
            seg     = next(s for s in sb.segments if s.segment_name == seg_nm)
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Target (min)", seg.target_duration_min)
            s2.metric("Max Duration", f"{seg.max_duration_min} min" if seg.max_duration_min > 0 else "No limit")
            s3.metric("Actual (min)", seg.actual_duration_min if seg.actual_duration_min else "—")
            s4.metric("Delay (min)",  seg.delay_min if seg.delay_min else "—")
            if seg.max_duration_min > 0 and seg.actual_duration_min and seg.actual_duration_min > seg.max_duration_min:
                st.info(f"ℹ️ Segment exceeded max duration "
                        f"({seg.actual_duration_min} min > {seg.max_duration_min} min) — "
                        "downstream rescheduled automatically.")
            css, cse = st.columns(2)
            with css:
                st.markdown("**Segment Start**")
                def_ss = seg.actual_start or sb.effective_start
                ss_d = st.date_input("Date", value=def_ss.date(), key="ss_d")
                ss_t = st.time_input("Time", value=def_ss.time(), key="ss_t")
                if st.button("Log Start", key="seg_start_btn"):
                    sim.apply_segment_start(st.session_state.schedule, sb_id, seg_nm, datetime.combine(ss_d, ss_t))
                    _autosave()
                    st.rerun()
            with cse:
                st.markdown("**Segment End**")
                def_se = seg.actual_end or (def_ss + timedelta(minutes=seg.target_duration_min))
                se_d = st.date_input("Date", value=def_se.date(), key="se_d")
                se_t = st.time_input("Time", value=def_se.time(), key="se_t")
                if st.button("Log End", type="primary", key="seg_end_btn"):
                    sim.apply_segment_end(
                        st.session_state.schedule, sb_id, seg_nm,
                        datetime.combine(se_d, se_t), engine, _thr,
                    )
                    st.session_state._live_auto_batches.discard(sb_id)
                    _autosave()
                    st.rerun()

    # ── Bulk CSV ───────────────────────────────────────────────────────────────
    with tab_bulk:
        st.subheader("Bulk Timestamp Entry via CSV")
        tmpl = _schedule_df()[["Batch ID","Phase","Equipment","Sched Start","Sched End"]].copy()
        tmpl["Actual Start"] = ""
        tmpl["Actual End"]   = ""
        st.dataframe(tmpl, use_container_width=True, hide_index=True)
        csv_in = st.text_area(
            "Paste filled CSV (Batch ID, Actual Start, Actual End)",
            height=160,
            placeholder="Batch ID,Actual Start,Actual End\nPT-001__UP_TSA,2024-01-10 06:00,2024-01-10 10:15",
        )
        if st.button("Apply Bulk Timestamps", type="primary"):
            try:
                in_df   = pd.read_csv(io.StringIO(csv_in))
                applied = 0
                for _, row in in_df.iterrows():
                    bid = str(row.get("Batch ID","")).strip()
                    a_s = str(row.get("Actual Start","")).strip()
                    a_e = str(row.get("Actual End","")).strip()
                    if bid and a_s:
                        sim.apply_batch_start(st.session_state.schedule, bid, datetime.strptime(a_s,"%Y-%m-%d %H:%M"))
                        applied += 1
                    if bid and a_e:
                        sim.apply_batch_end(
                            st.session_state.schedule, bid,
                            datetime.strptime(a_e,"%Y-%m-%d %H:%M"), engine, _thr,
                        )
                        st.session_state._live_auto_batches.discard(bid)
                _autosave()
                st.success(f"Applied {applied} timestamps — schedule updated automatically.")
                st.rerun()
            except Exception as exc:
                st.error(f"Parse error: {exc}")

    # ── Export / Import ────────────────────────────────────────────────────────
    with tab_io:
        st.subheader("Export / Import Execution Events")
        c_exp, c_imp = st.columns(2)
        with c_exp:
            ev_json = sim.export_json()
            st.download_button("📥 Download events.json", ev_json, "simulation_events.json", "application/json", use_container_width=True)
            if st.checkbox("Preview JSON"):
                st.code(ev_json, language="json")
        with c_imp:
            up = st.file_uploader("Upload events.json", type=["json"])
            if up and st.button("Apply Imported Events", type="primary"):
                sim.import_json(up.read().decode(), st.session_state.schedule, engine, _thr)
                _autosave()
                st.success("Events imported — schedule updated automatically.")
                st.rerun()
        if st.button("🗑 Reset Execution Log"):
            sim.clear()
            st.session_state._live_auto_batches.clear()
            for b in st.session_state.schedule:
                b.actual_start = b.actual_end = None
                b.status = BatchStatus.SCHEDULED
                for s in b.segments:
                    s.actual_start = s.actual_end = None
                    s.status = "Pending"
            _autosave()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MASTER DATA
# ══════════════════════════════════════════════════════════════════════════════
elif PAGE == "⚙️ Master Data":
    st.title("Master Data Configuration")

    tab_seq, tab_eq = st.tabs(["Process Sequences", "Equipment"])

    # ══ PROCESS SEQUENCES ═════════════════════════════════════════════════════
    with tab_seq:
        col_list, col_edit = st.columns([1, 3])

        # ── Left: sequence list ────────────────────────────────────────────────
        with col_list:
            st.subheader("Sequences")
            seq_names = list(st.session_state.sequences.keys())

            for name in seq_names:
                is_active = name == st.session_state.active_sequence
                btn_label = f"{'▶ ' if is_active else ''}{name}"
                if st.button(btn_label, key=f"sel_seq_{name}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.active_sequence = name
                    st.rerun()

            st.markdown("---")

            # Create new sequence
            with st.expander("➕ Create New Sequence"):
                new_name = st.text_input("Sequence name", key="new_seq_name", placeholder="My Custom Sequence")
                copy_from = st.selectbox("Copy steps from", ["(blank)"] + seq_names, key="new_seq_copy")
                if st.button("Create", type="primary", key="btn_create_seq"):
                    if not new_name.strip():
                        st.error("Name required.")
                    elif new_name in st.session_state.sequences:
                        st.error("Name already exists.")
                    else:
                        if copy_from == "(blank)":
                            st.session_state.sequences[new_name] = []
                        else:
                            st.session_state.sequences[new_name] = _deep_copy_seq(
                                st.session_state.sequences[copy_from]
                            )
                        st.session_state.active_sequence = new_name
                        st.rerun()

            # Duplicate active
            if st.button("⧉ Duplicate Active", use_container_width=True):
                base = st.session_state.active_sequence
                new  = f"{base} (copy)"
                i    = 1
                while new in st.session_state.sequences:
                    i += 1
                    new = f"{base} (copy {i})"
                st.session_state.sequences[new] = _deep_copy_seq(st.session_state.sequences[base])
                st.session_state.active_sequence = new
                st.rerun()

            # Delete active
            if len(st.session_state.sequences) > 1:
                if st.button("🗑 Delete Active", use_container_width=True):
                    del st.session_state.sequences[st.session_state.active_sequence]
                    st.session_state.active_sequence = next(iter(st.session_state.sequences))
                    st.rerun()

        # ── Right: sequence editor ─────────────────────────────────────────────
        with col_edit:
            active_name = st.session_state.active_sequence
            steps = st.session_state.sequences[active_name]

            st.subheader(f"Editing: {active_name}")

            # Rename sequence
            with st.expander("✏️ Rename this sequence"):
                rename_val = st.text_input("New name", value=active_name, key="rename_input")
                if st.button("Apply Rename", key="btn_rename"):
                    if rename_val.strip() and rename_val != active_name:
                        if rename_val in st.session_state.sequences:
                            st.error("Name already exists.")
                        else:
                            st.session_state.sequences[rename_val] = st.session_state.sequences.pop(active_name)
                            st.session_state.active_sequence = rename_val
                            st.rerun()

            if not steps:
                st.info("No steps yet. Add the first step below.")

            # Step list
            for i, step in enumerate(steps):
                eq_display = step["equipment_type"].value if hasattr(step["equipment_type"], "value") else step["equipment_type"]
                with st.expander(
                    f"**Step {i+1}:** {step['phase_label']}  ·  {eq_display}  ·  "
                    f"{step['duration_min'] * 60:,} sec ({step['duration_min']//60}h {step['duration_min']%60}m)"
                ):
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        new_label = st.text_input("Display Label", value=step["phase_label"], key=f"lbl_{i}")
                        new_phase = st.text_input("Internal Key (no spaces)", value=step["phase"], key=f"ph_{i}")
                        new_key   = st.text_input("Color Key (e.g. UP_INC)", value=step["phase_key"], key=f"pk_{i}")
                    with sc2:
                        cur_type   = step["equipment_type"].value if hasattr(step["equipment_type"], "value") else step["equipment_type"]
                        new_eq_val = st.selectbox("Equipment Type", EQ_TYPE_OPTIONS, index=EQ_TYPE_OPTIONS.index(cur_type), key=f"eq_{i}")
                        new_dur_sec = st.number_input("Duration (sec)", min_value=60, step=60,
                                                      value=int(step["duration_min"]) * 60, key=f"dur_{i}")
                        new_dur = new_dur_sec // 60

                    # Segments editor
                    _ROBOT_ICONS = {"Romag Robot": "🦾", "Incubation Robot": "🔬", "Fill Robot": "💊"}
                    segs_with_robot = [s for s in step.get("segments", []) if s.get("robot_types")]
                    used_icons = "".join(sorted({_ROBOT_ICONS.get(r, "🤖") for s in segs_with_robot for r in s["robot_types"]}))
                    robot_badge = f" {used_icons}" if used_icons else ""
                    st.markdown(f"**Segments{robot_badge}:**")
                    _MAX_TYPES = ["fixed", "1σ", "2σ", "3σ"]
                    seg_df = pd.DataFrame([
                        {
                            "Segment Name":        s.get("name", ""),
                            "Duration (sec)":      s.get("duration_min", 60) * 60,
                            "Std Dev (sec)":       int(s.get("std_dev_sec", 0) or 0),
                            "Max Type":            s.get("max_duration_type", "fixed") or "fixed",
                            "Max Duration (sec)":  s.get("max_duration_min", 0) * 60,
                            "⏭ Overlap Next":      bool(s.get("overlap_next_step", False)),
                            "🦾 Romag":            "Romag Robot"      in (s.get("robot_types") or []),
                            "🔬 Incubation":       "Incubation Robot" in (s.get("robot_types") or []),
                            "💊 Fill":             "Fill Robot"       in (s.get("robot_types") or []),
                            "Robot Dur (sec)":     s.get("robot_duration_min", 0) * 60,
                        }
                        for s in step.get("segments", [])
                    ])
                    edited_segs = st.data_editor(
                        seg_df,
                        use_container_width=True,
                        num_rows="dynamic",
                        key=f"segs_{i}",
                        column_config={
                            "Duration (sec)":      st.column_config.NumberColumn("Duration (sec)", min_value=60, step=60, default=3600),
                            "Std Dev (sec)":       st.column_config.NumberColumn("Std Dev σ (sec)", min_value=0, default=0,
                                                       help="Standard deviation in seconds. Used when Max Type is σ-based."),
                            "Max Type":            st.column_config.SelectboxColumn("Max Type", options=_MAX_TYPES, default="fixed",
                                                       help="fixed = use Max Duration (sec); 1σ/2σ/3σ = target + N×std_dev"),
                            "Max Duration (sec)":  st.column_config.NumberColumn("Max Dur (sec)", min_value=0, default=0,
                                                       help="Used only when Max Type = fixed. 0 = no limit."),
                            "⏭ Overlap Next":      st.column_config.CheckboxColumn("⏭ Overlap Next", default=False,
                                                       help="Next step can start once this segment begins."),
                            "🦾 Romag":            st.column_config.CheckboxColumn("🦾 Romag",      default=False),
                            "🔬 Incubation":       st.column_config.CheckboxColumn("🔬 Incubation", default=False),
                            "💊 Fill":             st.column_config.CheckboxColumn("💊 Fill",       default=False),
                            "Robot Dur (sec)":     st.column_config.NumberColumn("Robot (sec)", min_value=0, default=0, step=60),
                        },
                    )

                    # Action row
                    ba, bb, bc, bd = st.columns(4)
                    if ba.button("💾 Save", key=f"save_{i}", type="primary"):
                        step["phase_label"]    = new_label.strip()
                        step["phase"]          = new_phase.strip().replace(" ", "_")
                        step["phase_key"]      = new_key.strip().replace(" ", "_")
                        step["equipment_type"] = EQ_TYPE_MAP[new_eq_val]
                        _sigma_map = {"1σ": 1, "2σ": 2, "3σ": 3}
                        new_segs = []
                        for _, r in edited_segs.iterrows():
                            if not str(r["Segment Name"]).strip():
                                continue
                            rtypes = [
                                rt for rt, col in [
                                    ("Romag Robot",      "🦾 Romag"),
                                    ("Incubation Robot", "🔬 Incubation"),
                                    ("Fill Robot",       "💊 Fill"),
                                ] if bool(r.get(col, False))
                            ]
                            dur_min     = max(1, int(r.get("Duration (sec)", 60) or 60) // 60)
                            std_dev_sec = int(r.get("Std Dev (sec)", 0) or 0)
                            max_type    = str(r.get("Max Type", "fixed") or "fixed")
                            n_sigma     = _sigma_map.get(max_type, 0)
                            if n_sigma > 0 and std_dev_sec > 0:
                                # Compute fixed max from sigma so engine uses it as fallback too
                                max_dur_min = int(dur_min + n_sigma * std_dev_sec / 60.0 + 0.999)
                            else:
                                max_dur_min = max(0, int(r.get("Max Duration (sec)", 0) or 0) // 60)
                            new_segs.append({
                                "name":               str(r["Segment Name"]),
                                "duration_min":       dur_min,
                                "max_duration_min":   max_dur_min,
                                "max_duration_type":  max_type,
                                "std_dev_sec":        std_dev_sec,
                                "overlap_next_step":  bool(r.get("⏭ Overlap Next", False)),
                                "robot_types":        rtypes,
                                "robot_duration_min": max(0, int(r.get("Robot Dur (sec)", 0) or 0) // 60) if rtypes else 0,
                            })
                        step["segments"]      = new_segs
                        seg_total = sum(s["duration_min"] for s in new_segs)
                        step["duration_min"]  = seg_total if seg_total > 0 else new_dur
                        # Clear data_editor state so it reloads from the just-saved segments
                        st.session_state.pop(f"segs_{i}", None)
                        _autosave()
                        st.toast(f"Step {i+1} — {step['phase_label']} saved.", icon="✅")
                        st.rerun()

                    if i > 0:
                        if bb.button("⬆ Up", key=f"up_{i}"):
                            steps[i], steps[i-1] = steps[i-1], steps[i]
                            _renumber(steps)
                            st.rerun()
                    if i < len(steps) - 1:
                        if bc.button("⬇ Down", key=f"dn_{i}"):
                            steps[i], steps[i+1] = steps[i+1], steps[i]
                            _renumber(steps)
                            st.rerun()
                    if bd.button("🗑 Delete", key=f"del_{i}"):
                        steps.pop(i)
                        _renumber(steps)
                        st.rerun()

            # Add step button
            st.markdown("---")
            c_add, c_reset = st.columns(2)
            if c_add.button("➕ Add Step", type="primary", use_container_width=True):
                steps.append(_new_step(len(steps)))
                st.rerun()
            if c_reset.button("↩ Reset to Default CAR-T", use_container_width=True):
                st.session_state.sequences[active_name] = _deep_copy_seq(PROCESS_SEQUENCE)
                st.rerun()

            # Summary
            if steps:
                st.markdown("---")
                _tot_min = sum(s["duration_min"] for s in steps)
                st.markdown(f"**{len(steps)} steps**  |  "
                            f"Total: **{_tot_min * 60:,} sec** ({_tot_min//60}h {_tot_min%60}m)")
                def _overlap_tail(step_cfg):
                    tail = 0
                    for seg in reversed(step_cfg.get("segments", [])):
                        if seg.get("overlap_next_step"):
                            tail += seg["duration_min"]
                        else:
                            break
                    return tail

                summary_df = pd.DataFrame([{
                    "Step":              s["step"] + 1,
                    "Phase":             s["phase_label"],
                    "Equipment":         s["equipment_type"].value if hasattr(s["equipment_type"], "value") else s["equipment_type"],
                    "Duration (sec)":    s["duration_min"] * 60,
                    "Duration":          f"{s['duration_min']//60}h {s['duration_min']%60}m",
                    "Overlap Tail (sec)": _overlap_tail(s) * 60 or "—",
                    "Segments":          len(s.get("segments", [])),
                    "Robot Segs":        sum(1 for seg in s.get("segments", []) if seg.get("robot_types")),
                    "Robots Used":       ", ".join(sorted({r for seg in s.get("segments", []) for r in (seg.get("robot_types") or [])})) or "—",
                } for s in steps])
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # ══ EQUIPMENT ═════════════════════════════════════════════════════════════
    with tab_eq:
        st.subheader("Equipment Configuration")
        st.info("Toggle availability to exclude equipment from scheduling.")
        eq_by_type: Dict[EquipmentType, list] = {}
        for eq in st.session_state.equipment:
            eq_by_type.setdefault(eq.equipment_type, []).append(eq)

        for eq_type, eqs in eq_by_type.items():
            label = f"**{eq_type.value}** — {len(eqs)} unit(s)"
            if eq_type != EquipmentType.INCUBATOR:
                st.markdown(label)
                eq_df = pd.DataFrame([{"ID": e.equipment_id, "Name": e.display_name, "Available": e.is_available} for e in eqs])
                edited = st.data_editor(eq_df, use_container_width=True, key=f"eq_{eq_type.value}")
                if st.button("💾 Save", key=f"sav_eq_{eq_type.value}"):
                    for _, row in edited.iterrows():
                        for eq in st.session_state.equipment:
                            if eq.equipment_id == row["ID"]:
                                eq.is_available = bool(row["Available"])
                    st.success("Updated.")
                st.markdown("")
            else:
                with st.expander(label):
                    eq_df = pd.DataFrame([{"ID": e.equipment_id, "Name": e.display_name, "Available": e.is_available} for e in eqs])
                    st.dataframe(eq_df, use_container_width=True, hide_index=True)

        # ── Equipment Efficiency ───────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Equipment Efficiency")
        st.caption(
            "Efficiency (%) represents how productively each equipment type operates — "
            "accounting for downtime, cleaning, maintenance, and setup losses. "
            "A step with 80% efficiency will be scheduled as **nominal ÷ 0.80** (25% longer). "
            "Affects both the generated schedule and throughput calculations. "
            "Regenerate the schedule after changing these values."
        )

        eff_state = st.session_state.eq_efficiency
        eq_type_order = ["Romag", "Incubator", "BSD Sampling", "BSD Weighing", "Fill"]
        eff_cols = st.columns(len(eq_type_order))
        new_eff: dict = {}
        for col, type_val in zip(eff_cols, eq_type_order):
            current = eff_state.get(type_val, 100)
            val = col.number_input(
                f"{type_val} (%)",
                min_value=1,
                max_value=100,
                value=int(current),
                step=1,
                key=f"eff_{type_val}",
            )
            new_eff[type_val] = val
            # Visual indicator
            color = "#2ecc71" if val >= 90 else ("#e67e22" if val >= 70 else "#e74c3c")
            col.markdown(
                f"<div style='height:6px;border-radius:3px;"
                f"background:linear-gradient(to right,{color} {val}%,#eee {val}%)'></div>",
                unsafe_allow_html=True,
            )

        if st.button("💾 Save Efficiency", type="primary", key="btn_save_eff"):
            st.session_state.eq_efficiency = new_eff
            _autosave()
            st.success("Equipment efficiency saved. Regenerate the schedule to apply.")
