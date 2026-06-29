#!/usr/bin/env python3
"""Build ailt/index.html from Android repo USER_MANUAL.md."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANUAL = Path(r"D:\VSCode\android\ailanguagetutor\docs\manuals\USER_MANUAL.md")
FALLBACK_MANUAL = ROOT / "docs" / "USER_MANUAL.md"
DEFAULT_OUT_DIR = Path(r"D:\VSCode\cheradip\fcheradip\src\assets\ailt")
DEFAULT_OUT_HTML = DEFAULT_OUT_DIR / "ailt.html"
ASSETS_SRC = ROOT / "assets"


def slugify(title: str) -> str:
    text = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text.strip().lower())
    return text.strip("-") or "section"


def inline_md(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def parse_manual(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (body_html, toc_items) where toc_items are (id, label)."""
    lines = md.splitlines()
    parts: list[str] = []
    toc: list[tuple[str, str]] = []
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    for line in lines:
        stripped = line.strip()

        if stripped == "---":
            close_lists()
            parts.append("<hr>")
            continue

        if line.startswith("# ") and not line.startswith("## "):
            close_lists()
            title = line[2:].strip()
            # Skip duplicate page title — shown in hero
            continue

        if line.startswith("## "):
            close_lists()
            title = line[3:].strip()
            sid = slugify(title)
            toc.append((sid, title))
            parts.append(f'<h2 id="{sid}">{inline_md(title)}</h2>')
            continue

        if line.startswith("### "):
            close_lists()
            title = line[4:].strip()
            parts.append(f"<h3>{inline_md(title)}</h3>")
            continue

        if re.match(r"^\d+\.\s", stripped):
            if not in_ol:
                close_lists()
                parts.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s", "", stripped)
            parts.append(f"<li>{inline_md(item)}</li>")
            continue

        if line.startswith("- "):
            if not in_ul:
                close_lists()
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{inline_md(line[2:])}</li>")
            continue

        if stripped == "":
            close_lists()
            continue

        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            close_lists()
            inner = stripped.strip("*")
            parts.append(f'<p class="footer-note">{inline_md(inner)}</p>')
            continue

        close_lists()
        parts.append(f"<p>{inline_md(stripped)}</p>")

    close_lists()
    return "\n".join(parts), toc


def nav_html(toc: list[tuple[str, str]]) -> str:
    items = "\n".join(
        f'      <li><a href="#{sid}">{html.escape(label)}</a></li>' for sid, label in toc
    )
    return f"<ol>\n{items}\n    </ol>"


def build_page(manual_path: Path, out_path: Path) -> None:
    md = manual_path.read_text(encoding="utf-8")
    body, toc = parse_manual(md)
    nav = nav_html(toc)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sync static assets next to ailt.html (Angular: src/assets/ailt/)
    for name in ("manual.css", "cheradip.svg"):
        src = ASSETS_SRC / name
        if src.is_file():
            (out_dir / name).write_bytes(src.read_bytes())

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Cheradip AI Language Tutor — official user guide for scan, practice, grammar, subscriptions, and troubleshooting.">
  <title>User Guide — AI Language Tutor | Cheradip</title>
  <link rel="stylesheet" href="manual.css">
</head>
<body>
  <header class="site-header">
    <div class="site-header__brand">
      <img class="site-header__logo" src="cheradip.svg" alt="Cheradip" width="180" height="45">
      <p class="site-header__title">AI Language Tutor</p>
    </div>
    <div class="site-header__links">
      <a href="https://cheradip.com">Cheradip.com</a>
    </div>
  </header>

  <section class="hero">
    <span class="hero__badge">User Manual</span>
    <h1>AI Language Tutor — User Guide</h1>
    <p>Everything you need to scan, read, practice, and learn languages offline and with AI — for guests, trial, Pro, and Plus users.</p>
  </section>

  <div class="layout">
    <aside class="sidebar" aria-label="Table of contents">
      <h2>Contents</h2>
      <nav>{nav}</nav>
    </aside>

    <main class="content">
      <details class="mobile-toc">
        <summary>Table of contents</summary>
        <nav>{nav}</nav>
      </details>

      <article class="content-card manual">
{body}
      </article>
    </main>
  </div>

  <footer class="site-footer">
    <p>
      <a href="https://cheradip.com">Cheradip.com</a>
      &nbsp;·&nbsp;
      <a href="https://cheradip.com/ailt/api/health">API status</a>
      &nbsp;·&nbsp;
      AI Language Tutor User Guide
    </p>
  </footer>

  <script>
    (function () {{
      var links = document.querySelectorAll('.sidebar nav a, .mobile-toc nav a');
      if (!('IntersectionObserver' in window)) return;
      var map = {{}};
      links.forEach(function (a) {{
        var id = a.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (el) map[id] = a;
      }});
      var obs = new IntersectionObserver(function (entries) {{
        entries.forEach(function (e) {{
          if (e.isIntersecting) {{
            Object.values(map).forEach(function (l) {{ l.classList.remove('is-active'); }});
            var link = map[e.target.id];
            if (link) link.classList.add('is-active');
          }}
        }});
      }}, {{ rootMargin: '-40% 0px -55% 0px', threshold: 0 }});
      Object.keys(map).forEach(function (id) {{
        var el = document.getElementById(id);
        if (el) obs.observe(el);
      }});
    }})();
  </script>
</body>
</html>
"""
    out_path.write_text(page, encoding="utf-8")
    print(f"Built {out_path} ({len(toc)} sections) from {manual_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ailt user manual page")
    parser.add_argument(
        "--manual",
        type=Path,
        default=DEFAULT_MANUAL if DEFAULT_MANUAL.is_file() else FALLBACK_MANUAL,
        help="Path to USER_MANUAL.md",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_HTML,
        help="Output HTML path (default: fcheradip/src/assets/ailt/ailt.html)",
    )
    args = parser.parse_args()
    if not args.manual.is_file():
        print(f"Manual not found: {args.manual}", file=sys.stderr)
        return 1
    build_page(args.manual, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
