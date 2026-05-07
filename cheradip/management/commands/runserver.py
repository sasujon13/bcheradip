from __future__ import annotations

import atexit
import os
from pathlib import Path

from django.conf import settings
from django.core.management.commands.runserver import Command as RunserverCommand

from .watch_latex_svg import CommandError, start_latex_svg_observer


class Command(RunserverCommand):
    help = (
        "Starts Django's development server and, in the autoreload child process, "
        "also watches MEDIA_ROOT/latex for .tex -> .svg updates."
    )

    watcher_observer = None

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--latex-root",
            default=str(Path(settings.MEDIA_ROOT) / "latex"),
            help="Folder to watch recursively for .tex files (default: MEDIA_ROOT/latex).",
        )
        parser.add_argument(
            "--latex-debounce-ms",
            type=int,
            default=700,
            help="Wait this many milliseconds after a .tex change before compiling.",
        )
        parser.add_argument(
            "--skip-latex-watch",
            action="store_true",
            help="Disable the automatic .tex -> .svg watcher for this runserver session.",
        )

    def inner_run(self, *args, **options):
        self._maybe_start_latex_watcher(options)
        return super().inner_run(*args, **options)

    def _maybe_start_latex_watcher(self, options) -> None:
        if options.get("skip_latex_watch"):
            return
        if os.environ.get("RUN_MAIN") != "true":
            return
        if self.__class__.watcher_observer is not None:
            return
        try:
            observer = start_latex_svg_observer(
                stdout=self.stdout,
                stderr=self.stderr,
                latex_root=Path(options["latex_root"]),
                debounce_ms=int(options["latex_debounce_ms"]),
                compile_all=False,
                skip_initial_scan=False,
            )
        except CommandError as exc:
            self.stderr.write(self.style.WARNING(f"[latex-svg] watcher disabled: {exc}"))
            return

        self.__class__.watcher_observer = observer

        def _stop_observer() -> None:
            obs = self.__class__.watcher_observer
            if obs is None:
                return
            try:
                obs.stop()
                obs.join(timeout=2)
            finally:
                self.__class__.watcher_observer = None

        atexit.register(_stop_observer)
