from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileMovedEvent
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - handled at runtime
    FileSystemEvent = object  # type: ignore[assignment]
    FileMovedEvent = object  # type: ignore[assignment]
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


TEX_SUFFIX = ".tex"
SVG_SUFFIX = ".svg"
CLEAN_SUFFIXES = (
    ".aux",
    ".dvi",
    ".log",
    ".fls",
    ".fdb_latexmk",
    ".synctex.gz",
)


def cleanup_build_files(tex_path: Path) -> None:
    for suffix in CLEAN_SUFFIXES:
        sidecar = tex_path.with_suffix(suffix)
        try:
            if sidecar.exists():
                sidecar.unlink()
        except OSError:
            continue


def compile_tex_to_svg(tex_path: Path, stdout, stderr) -> bool:
    tex_path = tex_path.resolve()
    workdir = tex_path.parent
    dvi_path = tex_path.with_suffix(".dvi")
    svg_path = tex_path.with_suffix(SVG_SUFFIX)

    latex = subprocess.run(
        ["latex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if latex.returncode != 0 or not dvi_path.exists():
        stderr.write(f"[latex-svg] compile failed: {tex_path}\n")
        log = (latex.stdout or "") + ("\n" + latex.stderr if latex.stderr else "")
        excerpt = "\n".join(line for line in log.splitlines()[-12:] if line.strip())
        if excerpt:
            stderr.write(excerpt + "\n")
        cleanup_build_files(tex_path)
        return False

    svg = subprocess.run(
        ["dvisvgm", "--no-fonts", "--bbox=min", dvi_path.name, "-o", svg_path.name],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if svg.returncode != 0 or not svg_path.exists():
        stderr.write(f"[latex-svg] dvisvgm failed: {tex_path}\n")
        log = (svg.stdout or "") + ("\n" + svg.stderr if svg.stderr else "")
        excerpt = "\n".join(line for line in log.splitlines()[-12:] if line.strip())
        if excerpt:
            stderr.write(excerpt + "\n")
        cleanup_build_files(tex_path)
        return False

    cleanup_build_files(tex_path)
    stdout.write(f"[latex-svg] updated: {svg_path}\n")
    return True


def remove_generated_outputs(tex_path: Path, stdout) -> None:
    removed = False
    for suffix in (SVG_SUFFIX,) + CLEAN_SUFFIXES:
        target = tex_path.with_suffix(suffix)
        try:
            if target.exists():
                target.unlink()
                removed = True
        except OSError:
            continue
    if removed:
        stdout.write(f"[latex-svg] removed outputs: {tex_path}\n")


class LatexSvgWatcher(FileSystemEventHandler):
    def __init__(self, stdout, stderr, latex_root: Path, debounce_s: float) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.latex_root = latex_root
        self.debounce_s = debounce_s
        self._timers: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def _normalize(self, raw_path: str) -> Path | None:
        p = Path(raw_path)
        if p.suffix.lower() != TEX_SUFFIX:
            return None
        return p.resolve()

    def _schedule_compile(self, tex_path: Path) -> None:
        if not tex_path.exists():
            return
        with self._lock:
            timer = self._timers.pop(tex_path, None)
            if timer is not None:
                timer.cancel()
            timer = threading.Timer(self.debounce_s, self._run_compile, args=(tex_path,))
            timer.daemon = True
            self._timers[tex_path] = timer
            timer.start()

    def _run_compile(self, tex_path: Path) -> None:
        with self._lock:
            self._timers.pop(tex_path, None)
        compile_tex_to_svg(tex_path, self.stdout, self.stderr)

    def _remove_outputs(self, tex_path: Path) -> None:
        with self._lock:
            timer = self._timers.pop(tex_path, None)
            if timer is not None:
                timer.cancel()
        remove_generated_outputs(tex_path, self.stdout)

    def on_created(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        tex_path = self._normalize(event.src_path)
        if tex_path is not None:
            self._schedule_compile(tex_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        tex_path = self._normalize(event.src_path)
        if tex_path is not None:
            self._schedule_compile(tex_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        tex_path = self._normalize(event.src_path)
        if tex_path is not None:
            self._remove_outputs(tex_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        old_path = self._normalize(event.src_path)
        if old_path is not None:
            self._remove_outputs(old_path)
        new_path = self._normalize(event.dest_path)
        if new_path is not None:
            self._schedule_compile(new_path)


def ensure_latex_svg_requirements() -> None:
    if Observer is None:
        raise CommandError(
            "watchdog is not installed. Run `pip install watchdog` in the backend environment."
        )
    for binary in ("latex", "dvisvgm"):
        if shutil.which(binary) is None:
            raise CommandError(
                f"Required executable `{binary}` was not found in PATH. "
                "Install MiKTeX/TeX Live and ensure the command is available."
            )


def compile_initial_tex_files(
    latex_root: Path,
    stdout,
    stderr,
    *,
    compile_all: bool = False,
) -> None:
    tex_files = sorted(latex_root.rglob(f"*{TEX_SUFFIX}"))
    for tex_path in tex_files:
        svg_path = tex_path.with_suffix(SVG_SUFFIX)
        needs_compile = (
            compile_all
            or not svg_path.exists()
            or tex_path.stat().st_mtime_ns > svg_path.stat().st_mtime_ns
        )
        if needs_compile:
            compile_tex_to_svg(tex_path, stdout, stderr)


def start_latex_svg_observer(
    *,
    stdout,
    stderr,
    latex_root: Path | None = None,
    debounce_ms: int = 700,
    compile_all: bool = False,
    skip_initial_scan: bool = False,
):
    ensure_latex_svg_requirements()
    root = (latex_root or (Path(settings.MEDIA_ROOT) / "latex")).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    if not skip_initial_scan:
        compile_initial_tex_files(root, stdout, stderr, compile_all=compile_all)

    handler = LatexSvgWatcher(stdout, stderr, latex_root=root, debounce_s=max(0, debounce_ms) / 1000.0)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    stdout.write(f"[latex-svg] watching: {root}\n")
    return observer


class Command(BaseCommand):
    help = (
        "Watch MEDIA_ROOT/latex recursively and compile changed .tex files to sibling .svg "
        "using latex + dvisvgm."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--latex-root",
            default=str(Path(settings.MEDIA_ROOT) / "latex"),
            help="Folder to watch recursively for .tex files (default: MEDIA_ROOT/latex).",
        )
        parser.add_argument(
            "--debounce-ms",
            type=int,
            default=700,
            help="Wait this many milliseconds after a change before compiling.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Compile stale .tex files once and exit.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Compile every .tex file during the startup scan, not only stale ones.",
        )
        parser.add_argument(
            "--skip-initial-scan",
            action="store_true",
            help="Start watching immediately without compiling existing files first.",
        )

    def handle(self, *args, **options) -> None:
        latex_root = Path(options["latex_root"]).expanduser().resolve()
        latex_root.mkdir(parents=True, exist_ok=True)

        ensure_latex_svg_requirements()
        if not options["skip_initial_scan"]:
            compile_initial_tex_files(
                latex_root,
                self.stdout,
                self.stderr,
                compile_all=bool(options["all"]),
            )

        if options["once"]:
            return

        observer = start_latex_svg_observer(
            stdout=self.stdout,
            stderr=self.stderr,
            latex_root=latex_root,
            debounce_ms=int(options["debounce_ms"]),
            compile_all=False,
            skip_initial_scan=True,
        )
        self.stdout.write("[latex-svg] press Ctrl+C to stop.\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
