from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DragDropTk = TkinterDnD.Tk
    DRAG_DROP_AVAILABLE = True
except ImportError:
    DND_FILES = "DND_Files"
    DragDropTk = tk.Tk
    DRAG_DROP_AVAILABLE = False


APP_TITLE = "Video Codec Scanner"
APP_VERSION = "1.0"
APP_AUTHOR = "RodneyASL"
APP_WEBSITE = "https://rodneyswelten.de"
VIDEO_TYPES = [
    ("Videodateien", "*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.wmv *.ts *.mts *.m2ts *.mpg *.mpeg *.flv"),
    ("Alle Dateien", "*.*"),
]


def first(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "", "N/A")), None)


def as_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(number) if number is not None else None


def parse_rate(value: Any) -> float | None:
    if value in (None, "", "0/0", "N/A"):
        return None
    text = str(value)
    if "/" in text:
        left, right = text.split("/", 1)
        denominator = as_float(right)
        numerator = as_float(left)
        return numerator / denominator if numerator is not None and denominator else None
    return as_float(text)


def format_bytes(value: int | float | None) -> str:
    if value is None:
        return "–"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            digits = 0 if unit == "B" else 2
            return f"{size:.{digits}f} {unit}".replace(".", ",")
        size /= 1024
    return "–"


def format_bitrate(value: int | float | None) -> str:
    if value is None:
        return "–"
    value = float(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} Mbit/s".replace(".", ",")
    return f"{value / 1_000:.0f} kbit/s".replace(".", ",")


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_decimal(value: float | None, decimals: int = 2, suffix: str = "") -> str:
    if value is None or not math.isfinite(value):
        return "–"
    return f"{value:.{decimals}f}{suffix}".replace(".", ",")


def codec_label(codec: Any, long_name: Any = None, profile: Any = None) -> str:
    parts = [str(item) for item in (codec, long_name, profile) if item not in (None, "", "N/A")]
    unique: list[str] = []
    for part in parts:
        if not any(part.casefold() == existing.casefold() for existing in unique):
            unique.append(part)
    return " · ".join(unique) if unique else "–"


@dataclass
class StreamInfo:
    kind: str
    index: int
    codec: str = "–"
    language: str = "–"
    title: str = "–"
    bitrate: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaReport:
    path: Path
    analyzer: str
    container: str = "–"
    duration: float | None = None
    size: int | None = None
    overall_bitrate: int | None = None
    streams: list[StreamInfo] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def videos(self) -> list[StreamInfo]:
        return [stream for stream in self.streams if stream.kind == "Video"]

    @property
    def audios(self) -> list[StreamInfo]:
        return [stream for stream in self.streams if stream.kind == "Audio"]

    @property
    def subtitles(self) -> list[StreamInfo]:
        return [stream for stream in self.streams if stream.kind == "Untertitel"]


def find_analyzer() -> tuple[str, str] | None:
    app_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    candidates = [
        ("MediaInfo", app_dir / "MediaInfo.exe"),
        ("MediaInfo", app_dir / "mediainfo.exe"),
        ("ffprobe", app_dir / "ffprobe.exe"),
    ]
    for name, candidate in candidates:
        if candidate.is_file():
            return name, str(candidate)
    for name, command in (("MediaInfo", "mediainfo"), ("ffprobe", "ffprobe")):
        found = shutil.which(command)
        if found:
            return name, found
    return None


def run_json(command: list[str]) -> dict[str, Any]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        timeout=90,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip() or "Der Analysedienst hat einen Fehler gemeldet."
        raise RuntimeError(reason)
    try:
        return json.loads(completed.stdout.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Die Analyse lieferte keine gültigen JSON-Daten.") from exc


def analyze(path: Path) -> MediaReport:
    analyzer = find_analyzer()
    if not analyzer:
        raise FileNotFoundError(
            "Weder MediaInfo CLI noch ffprobe wurde gefunden. Installieren Sie eines der Programme "
            "oder legen Sie MediaInfo.exe/ffprobe.exe neben dieses Tool."
        )
    name, executable = analyzer
    if name == "MediaInfo":
        data = run_json([executable, "--Output=JSON", str(path)])
        return parse_mediainfo(path, data)
    data = run_json([
        executable,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path),
    ])
    return parse_ffprobe(path, data)


def parse_mediainfo(path: Path, data: dict[str, Any]) -> MediaReport:
    tracks = data.get("media", {}).get("track", [])
    general = next((track for track in tracks if track.get("@type") == "General"), {})
    report = MediaReport(
        path=path,
        analyzer="MediaInfo",
        container=str(first(general.get("Format_Commercial_IfAny"), general.get("Format"), "–")),
        duration=as_float(general.get("Duration")),
        size=as_int(general.get("FileSize")) or (path.stat().st_size if path.exists() else None),
        overall_bitrate=as_int(general.get("OverallBitRate")),
        raw=data,
    )
    counters = {"Video": 0, "Audio": 0, "Text": 0}
    for track in tracks:
        source_kind = track.get("@type")
        if source_kind not in counters:
            continue
        counters[source_kind] += 1
        kind = "Untertitel" if source_kind == "Text" else source_kind
        details: dict[str, Any] = {}
        if kind == "Video":
            width = as_int(track.get("Width"))
            height = as_int(track.get("Height"))
            details = {
                "Breite": width,
                "Höhe": height,
                "Bildformat": first(track.get("DisplayAspectRatio_String"), track.get("DisplayAspectRatio")),
                "Framerate": as_float(track.get("FrameRate")),
                "Framerate-Modus": track.get("FrameRate_Mode"),
                "Farbraum": track.get("ColorSpace"),
                "Chroma-Subsampling": track.get("ChromaSubsampling"),
                "Bittiefe": as_int(track.get("BitDepth")),
                "Scanart": track.get("ScanType"),
                "Frames": as_int(track.get("FrameCount")),
            }
        elif kind == "Audio":
            details = {
                "Kanäle": as_int(track.get("Channels")),
                "Kanalanordnung": first(track.get("ChannelLayout"), track.get("ChannelPositions")),
                "Abtastrate": as_int(track.get("SamplingRate")),
                "Bittiefe": as_int(track.get("BitDepth")),
                "Bitratenmodus": track.get("BitRate_Mode"),
            }
        else:
            details = {
                "Format": track.get("Format"),
                "Erzwungen": first(track.get("Forced"), track.get("Forced_String")),
                "Standard": first(track.get("Default"), track.get("Default_String")),
            }
        report.streams.append(StreamInfo(
            kind=kind,
            index=counters[source_kind],
            codec=codec_label(first(track.get("Format_Commercial_IfAny"), track.get("Format")), track.get("CodecID"), track.get("Format_Profile")),
            language=str(first(track.get("Language_String"), track.get("Language"), "–")),
            title=str(first(track.get("Title"), "–")),
            bitrate=as_int(track.get("BitRate")),
            details=details,
        ))
    return report


def parse_ffprobe(path: Path, data: dict[str, Any]) -> MediaReport:
    fmt = data.get("format", {})
    tags = fmt.get("tags", {}) or {}
    report = MediaReport(
        path=path,
        analyzer="ffprobe",
        container=str(first(fmt.get("format_long_name"), fmt.get("format_name"), "–")),
        duration=as_float(fmt.get("duration")),
        size=as_int(fmt.get("size")) or (path.stat().st_size if path.exists() else None),
        overall_bitrate=as_int(fmt.get("bit_rate")),
        raw=data,
    )
    counters = {"video": 0, "audio": 0, "subtitle": 0}
    for stream in data.get("streams", []):
        source_kind = stream.get("codec_type")
        if source_kind not in counters:
            continue
        counters[source_kind] += 1
        kind = {"video": "Video", "audio": "Audio", "subtitle": "Untertitel"}[source_kind]
        stream_tags = stream.get("tags", {}) or {}
        disposition = stream.get("disposition", {}) or {}
        if kind == "Video":
            details = {
                "Breite": as_int(stream.get("width")),
                "Höhe": as_int(stream.get("height")),
                "Bildformat": first(stream.get("display_aspect_ratio"), stream.get("sample_aspect_ratio")),
                "Framerate": first(parse_rate(stream.get("avg_frame_rate")), parse_rate(stream.get("r_frame_rate"))),
                "Framerate-Modus": None,
                "Pixelformat": stream.get("pix_fmt"),
                "Farbraum": first(stream.get("color_space"), stream.get("color_primaries")),
                "Bittiefe": as_int(stream.get("bits_per_raw_sample")),
                "Frames": as_int(stream.get("nb_frames")),
            }
        elif kind == "Audio":
            details = {
                "Kanäle": as_int(stream.get("channels")),
                "Kanalanordnung": stream.get("channel_layout"),
                "Abtastrate": as_int(stream.get("sample_rate")),
                "Bittiefe": first(as_int(stream.get("bits_per_raw_sample")), as_int(stream.get("bits_per_sample"))),
            }
        else:
            details = {
                "Format": first(stream.get("codec_long_name"), stream.get("codec_name")),
                "Erzwungen": "Ja" if disposition.get("forced") else "Nein",
                "Standard": "Ja" if disposition.get("default") else "Nein",
            }
        report.streams.append(StreamInfo(
            kind=kind,
            index=counters[source_kind],
            codec=codec_label(stream.get("codec_name"), stream.get("codec_long_name"), stream.get("profile")),
            language=str(first(stream_tags.get("language"), "–")),
            title=str(first(stream_tags.get("title"), "–")),
            bitrate=as_int(stream.get("bit_rate")),
            details=details,
        ))
    return report


def metrics(report: MediaReport) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    duration = report.duration
    if report.size and duration and duration > 0:
        rows.append(("Speicherbedarf pro Minute", format_bytes(report.size / duration * 60), "Aus Dateigröße und Dauer berechnet"))
    if report.overall_bitrate:
        rows.append(("Gesamtbitrate", format_bitrate(report.overall_bitrate), "Containerwert; enthält alle Spuren und Overhead"))
    elif report.size and duration and duration > 0:
        calculated = report.size * 8 / duration
        rows.append(("Gesamtbitrate (berechnet)", format_bitrate(calculated), "Aus Dateigröße ÷ Dauer berechnet"))

    if report.videos:
        video = report.videos[0]
        width = as_int(video.details.get("Breite"))
        height = as_int(video.details.get("Höhe"))
        fps = as_float(video.details.get("Framerate"))
        bitrate = video.bitrate
        if bitrate and width and height:
            rows.append(("Bitrate je Megapixel", format_decimal(bitrate / (width * height), 2, " Mbit/s/MP"), "Vergleichswert für die räumliche Kompression"))
        if bitrate and width and height and fps:
            bpppf = bitrate / (width * height * fps)
            rows.append(("Bits pro Pixel und Bild", format_decimal(bpppf, 4, " bit/(Pixel·Bild)"), "Kleiner bedeutet meist stärkere Kompression; Inhalte/Codecs bleiben entscheidend"))
        if report.size and duration and width and height and fps:
            estimated_raw_video = width * height * 3 * fps * duration
            if estimated_raw_video > 0:
                ratio = estimated_raw_video / report.size
                rows.append((
                    "Kompressionsverhältnis (Schätzung)",
                    f"ca. {format_decimal(ratio, 1)} : 1",
                    "Klar gekennzeichnete Schätzung: unkomprimiertes RGB24-Video als Referenz; Dateigröße enthält auch Audio/Untertitel",
                ))
    return rows


class ScannerApp(DragDropTk):
    BG = "#10151f"
    PANEL = "#18202d"
    PANEL_2 = "#202b3a"
    TEXT = "#eef3f8"
    MUTED = "#9facbd"
    ACCENT = "#4fd1c5"
    ACCENT_DARK = "#153f41"
    WARNING = "#f7c96b"

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x740")
        self.minsize(880, 620)
        self.configure(bg=self.BG)
        self.report: MediaReport | None = None
        self.selected_path = tk.StringVar()
        self.status = tk.StringVar(value="Bereit – wählen Sie eine Videodatei aus.")
        self.analyzer_status = tk.StringVar(value="Analysedienst wird gesucht …")
        self._setup_style()
        self._build_ui()
        self._setup_drag_and_drop()
        self.after(100, self._refresh_analyzer_status)
        self.after(250, self._read_startup_argument)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground=self.TEXT)
        style.configure("Subtitle.TLabel", foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=self.PANEL, foreground=self.TEXT)
        style.configure("Metric.TLabel", background=self.PANEL, foreground=self.ACCENT, font=("Segoe UI Semibold", 12))
        style.configure("Muted.Panel.TLabel", background=self.PANEL, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#092224", borderwidth=0, padding=(18, 10), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#6ee7dc"), ("disabled", "#446c6d")])
        style.configure("Secondary.TButton", background=self.PANEL_2, foreground=self.TEXT, borderwidth=0, padding=(14, 9))
        style.map("Secondary.TButton", background=[("active", "#2b394b")])
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.PANEL, foreground=self.MUTED, padding=(18, 10), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.PANEL_2)], foreground=[("selected", self.TEXT)])
        style.configure("Treeview", background=self.PANEL, fieldbackground=self.PANEL, foreground=self.TEXT, rowheight=30, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=self.PANEL_2, foreground=self.TEXT, relief="flat", font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", self.ACCENT_DARK)])
        style.configure("Horizontal.TProgressbar", troughcolor=self.PANEL, background=self.ACCENT, borderwidth=0)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=(26, 22, 26, 18))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Codecs, Spuren und Kompression verständlich auf einen Blick", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        badge = tk.Label(header, textvariable=self.analyzer_status, bg=self.ACCENT_DARK, fg=self.ACCENT, font=("Segoe UI Semibold", 9), padx=12, pady=7)
        badge.pack(side="right", anchor="n")

        picker = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        picker.pack(fill="x", pady=(20, 14))
        self.path_entry = tk.Entry(picker, textvariable=self.selected_path, bg="#111824", fg=self.TEXT, insertbackground=self.TEXT, relief="flat", font=("Segoe UI", 10))
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        ttk.Button(picker, text="Datei wählen", style="Secondary.TButton", command=self.choose_file).pack(side="left", padx=(0, 8))
        self.scan_button = ttk.Button(picker, text="Jetzt scannen", style="Accent.TButton", command=self.start_scan)
        self.scan_button.pack(side="left")

        self.drop_zone = tk.Label(
            outer,
            text="⇩  Videodatei hier ablegen\noder klicken, um eine Datei auszuwählen",
            bg=self.PANEL,
            fg=self.MUTED,
            activebackground=self.PANEL_2,
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            pady=12,
        )
        self.drop_zone.pack(fill="x", pady=(0, 10))
        self.drop_zone.bind("<Button-1>", lambda _event: self.choose_file())

        self.progress = ttk.Progressbar(outer, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(0, 10))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self.overview_tab = ttk.Frame(self.notebook, padding=4)
        self.streams_tab = ttk.Frame(self.notebook, padding=4)
        self.details_tab = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.overview_tab, text="Übersicht")
        self.notebook.add(self.streams_tab, text="Alle Spuren")
        self.notebook.add(self.details_tab, text="Technische Rohdaten")
        self._build_overview()
        self._build_streams()
        self._build_details()

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(12, 0))
        ttk.Label(status_bar, textvariable=self.status, style="Subtitle.TLabel").pack(side="left", fill="x", expand=True)
        author = ttk.Label(status_bar, text=f"© 2026 {APP_AUTHOR} · rodneyswelten.de", style="Subtitle.TLabel", cursor="hand2")
        author.pack(side="right", padx=(12, 10))
        author.bind("<Button-1>", lambda _event: webbrowser.open(APP_WEBSITE))
        ttk.Button(status_bar, text="Bericht kopieren", style="Secondary.TButton", command=self.copy_report).pack(side="right")

    def _build_overview(self) -> None:
        self.cards = ttk.Frame(self.overview_tab)
        self.cards.pack(fill="x", pady=(10, 12))
        self.cards.columnconfigure((0, 1, 2, 3), weight=1, uniform="cards")
        self.card_values: dict[str, tk.StringVar] = {}
        for column, (key, label) in enumerate((("container", "CONTAINER"), ("duration", "DAUER"), ("size", "DATEIGRÖSSE"), ("bitrate", "GESAMTBITRATE"))):
            card = ttk.Frame(self.cards, style="Panel.TFrame", padding=15)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0 if column == 3 else 5))
            value = tk.StringVar(value="–")
            self.card_values[key] = value
            ttk.Label(card, text=label, style="Muted.Panel.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=value, style="Metric.TLabel", wraplength=210).pack(anchor="w", pady=(7, 0))

        body = ttk.Frame(self.overview_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        primary = ttk.Frame(body, style="Panel.TFrame", padding=16)
        primary.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(primary, text="Wichtigste Spuren", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 10))
        self.primary_text = tk.Text(primary, bg=self.PANEL, fg=self.TEXT, relief="flat", wrap="word", font=("Segoe UI", 10), state="disabled", height=12)
        self.primary_text.pack(fill="both", expand=True)

        compression = ttk.Frame(body, style="Panel.TFrame", padding=16)
        compression.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(compression, text="Kompressionskennzahlen", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 10))
        columns = ("value", "explanation")
        self.metric_tree = ttk.Treeview(compression, columns=columns, show="tree headings", height=10)
        self.metric_tree.heading("#0", text="Kennzahl")
        self.metric_tree.heading("value", text="Wert")
        self.metric_tree.heading("explanation", text="Einordnung")
        self.metric_tree.column("#0", width=190, minwidth=130)
        self.metric_tree.column("value", width=150, minwidth=110)
        self.metric_tree.column("explanation", width=330, minwidth=180)
        self.metric_tree.pack(fill="both", expand=True)

    def _build_streams(self) -> None:
        columns = ("kind", "codec", "bitrate", "language", "details")
        self.stream_tree = ttk.Treeview(self.streams_tab, columns=columns, show="headings")
        headers = {"kind": "Spur", "codec": "Codec / Profil", "bitrate": "Bitrate", "language": "Sprache", "details": "Details"}
        widths = {"kind": 105, "codec": 330, "bitrate": 110, "language": 105, "details": 360}
        for column in columns:
            self.stream_tree.heading(column, text=headers[column])
            self.stream_tree.column(column, width=widths[column], minwidth=80)
        scrollbar = ttk.Scrollbar(self.streams_tab, orient="vertical", command=self.stream_tree.yview)
        self.stream_tree.configure(yscrollcommand=scrollbar.set)
        self.stream_tree.pack(side="left", fill="both", expand=True, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

    def _build_details(self) -> None:
        self.raw_text = tk.Text(self.details_tab, bg=self.PANEL, fg="#cbd5e1", insertbackground=self.TEXT, relief="flat", wrap="none", font=("Consolas", 9), state="disabled")
        y_scroll = ttk.Scrollbar(self.details_tab, orient="vertical", command=self.raw_text.yview)
        x_scroll = ttk.Scrollbar(self.details_tab, orient="horizontal", command=self.raw_text.xview)
        self.raw_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.raw_text.grid(row=0, column=0, sticky="nsew", pady=(10, 0))
        y_scroll.grid(row=0, column=1, sticky="ns", pady=(10, 0))
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.details_tab.rowconfigure(0, weight=1)
        self.details_tab.columnconfigure(0, weight=1)

    def _refresh_analyzer_status(self) -> None:
        found = find_analyzer()
        self.analyzer_status.set(f"✓ {found[0]} bereit" if found else "⚠ Analysedienst fehlt")

    def _setup_drag_and_drop(self) -> None:
        if not DRAG_DROP_AVAILABLE:
            self.drop_zone.configure(text="Datei hier auswählen\n(Drag-and-drop-Modul ist in dieser Startart nicht installiert)")
            return
        for target in (self, self.drop_zone, self.path_entry):
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._on_file_drop)
            target.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            target.dnd_bind("<<DropLeave>>", self._on_drop_leave)

    def _on_drop_enter(self, event: Any) -> str:
        self.drop_zone.configure(bg=self.ACCENT_DARK, fg=self.ACCENT, text="Loslassen, um die Datei zu scannen")
        return getattr(event, "action", "copy")

    def _on_drop_leave(self, event: Any) -> str:
        self._reset_drop_zone()
        return getattr(event, "action", "copy")

    def _reset_drop_zone(self) -> None:
        self.drop_zone.configure(
            bg=self.PANEL,
            fg=self.MUTED,
            text="⇩  Videodatei hier ablegen\noder klicken, um eine Datei auszuwählen",
        )

    def _on_file_drop(self, event: Any) -> str:
        self._reset_drop_zone()
        try:
            dropped = list(self.tk.splitlist(event.data))
        except (tk.TclError, AttributeError):
            dropped = [str(getattr(event, "data", ""))]
        path = next((Path(item) for item in dropped if Path(item).is_file()), None)
        if path is None:
            self.status.set("Im abgelegten Inhalt wurde keine Datei gefunden.")
            return "copy"
        self.selected_path.set(str(path.resolve()))
        self.start_scan()
        return "copy"

    def _read_startup_argument(self) -> None:
        if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
            self.selected_path.set(str(Path(sys.argv[1]).resolve()))
            self.start_scan()

    def choose_file(self) -> None:
        selected = filedialog.askopenfilename(title="Videodatei auswählen", filetypes=VIDEO_TYPES)
        if selected:
            self.selected_path.set(selected)
            self.start_scan()

    def start_scan(self) -> None:
        path = Path(self.selected_path.get().strip().strip('"'))
        if not path.is_file():
            messagebox.showwarning(APP_TITLE, "Bitte wählen Sie zuerst eine vorhandene Videodatei aus.")
            return
        self.scan_button.state(["disabled"])
        self.progress.start(12)
        self.status.set(f"Analysiere {path.name} …")
        threading.Thread(target=self._scan_worker, args=(path,), daemon=True).start()

    def _scan_worker(self, path: Path) -> None:
        try:
            report = analyze(path)
        except Exception as exc:
            self.after(0, self._scan_failed, str(exc))
        else:
            self.after(0, self._show_report, report)

    def _scan_failed(self, reason: str) -> None:
        self.progress.stop()
        self.scan_button.state(["!disabled"])
        self.status.set("Analyse fehlgeschlagen.")
        self._refresh_analyzer_status()
        messagebox.showerror(APP_TITLE, reason)

    def _show_report(self, report: MediaReport) -> None:
        self.report = report
        self.progress.stop()
        self.scan_button.state(["!disabled"])
        self.card_values["container"].set(report.container)
        self.card_values["duration"].set(format_duration(report.duration))
        self.card_values["size"].set(format_bytes(report.size))
        self.card_values["bitrate"].set(format_bitrate(report.overall_bitrate))
        self._set_primary(report)

        for item in self.metric_tree.get_children():
            self.metric_tree.delete(item)
        for label, value, explanation in metrics(report):
            self.metric_tree.insert("", "end", text=label, values=(value, explanation))

        for item in self.stream_tree.get_children():
            self.stream_tree.delete(item)
        for stream in report.streams:
            details = self._stream_details(stream)
            self.stream_tree.insert("", "end", values=(f"{stream.kind} {stream.index}", stream.codec, format_bitrate(stream.bitrate), stream.language, details))

        self._replace_text(self.raw_text, json.dumps(report.raw, ensure_ascii=False, indent=2))
        self.status.set(f"Fertig: {len(report.videos)} Video-, {len(report.audios)} Audio- und {len(report.subtitles)} Untertitelspur(en) · analysiert mit {report.analyzer}")
        self.analyzer_status.set(f"✓ {report.analyzer} verwendet")
        self.notebook.select(self.overview_tab)

    def _set_primary(self, report: MediaReport) -> None:
        lines = [f"DATEI\n{report.path.name}\n"]
        if report.videos:
            video = report.videos[0]
            width, height = video.details.get("Breite"), video.details.get("Höhe")
            resolution = f"{width} × {height}" if width and height else "–"
            fps = format_decimal(as_float(video.details.get("Framerate")), 3, " fps")
            lines.append(f"VIDEO\n{video.codec}\n{resolution} · {video.details.get('Bildformat') or 'Format –'} · {fps}\n{format_bitrate(video.bitrate)}\n")
        else:
            lines.append("VIDEO\nKeine Videospur gefunden\n")
        if report.audios:
            audio = report.audios[0]
            channels = audio.details.get("Kanäle")
            sample_rate = audio.details.get("Abtastrate")
            extras = []
            if channels:
                extras.append(f"{channels} Kanäle")
            if sample_rate:
                extras.append(f"{sample_rate / 1000:g} kHz")
            lines.append(f"AUDIO\n{audio.codec}\n{' · '.join(extras) or '–'} · {format_bitrate(audio.bitrate)}\n")
        else:
            lines.append("AUDIO\nKeine Audiospur gefunden\n")
        subtitle_languages = ", ".join(stream.language for stream in report.subtitles) if report.subtitles else "Keine"
        lines.append(f"UNTERTITEL\n{len(report.subtitles)} Spur(en) · {subtitle_languages}")
        self._replace_text(self.primary_text, "\n".join(lines))

    @staticmethod
    def _stream_details(stream: StreamInfo) -> str:
        parts = []
        for key, value in stream.details.items():
            if value in (None, "", "N/A"):
                continue
            if key == "Framerate":
                shown = format_decimal(as_float(value), 3, " fps")
            elif key == "Abtastrate":
                shown = f"{as_int(value) or 0} Hz"
            elif key == "Bittiefe":
                shown = f"{value} bit"
            else:
                shown = str(value)
            parts.append(f"{key}: {shown}")
        if stream.title != "–":
            parts.append(f"Titel: {stream.title}")
        return " · ".join(parts) or "–"

    @staticmethod
    def _replace_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def report_as_text(self) -> str:
        report = self.report
        if not report:
            return ""
        lines = [
            APP_TITLE,
            f"Datei: {report.path}",
            f"Analysiert mit: {report.analyzer}",
            f"Container: {report.container}",
            f"Dauer: {format_duration(report.duration)}",
            f"Dateigröße: {format_bytes(report.size)}",
            f"Gesamtbitrate: {format_bitrate(report.overall_bitrate)}",
            "",
            "SPUREN",
        ]
        for stream in report.streams:
            lines.append(f"- {stream.kind} {stream.index}: {stream.codec}; {format_bitrate(stream.bitrate)}; Sprache: {stream.language}; {self._stream_details(stream)}")
        lines.extend(["", "KOMPRESSIONSKENNZAHLEN"])
        for label, value, explanation in metrics(report):
            lines.append(f"- {label}: {value} ({explanation})")
        return "\n".join(lines)

    def copy_report(self) -> None:
        content = self.report_as_text()
        if not content:
            messagebox.showinfo(APP_TITLE, "Scannen Sie zuerst eine Datei.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.status.set("Bericht wurde in die Zwischenablage kopiert.")


if __name__ == "__main__":
    ScannerApp().mainloop()
