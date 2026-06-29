"""Branded HTML + plain-text email bodies for Cheradip / AI Language Tutor."""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "email"
_LOGO_SVG = _ASSETS / "cheradip.svg"

# Matches ui/theme Color.kt — CheradipTeal, CheradipForestGreen, logo gradient, surfaces
BRAND = {
    "teal": "#00897B",
    "teal_dark": "#004D40",
    "forest": "#228B22",
    "green_start": "#50b848",
    "green_end": "#b0d235",
    "surface": "#E0F2F1",
    "background": "#FAFAFA",
    "text": "#1C1B1F",
    "text_muted": "#424242",
    "text_faint": "#757575",
    "white": "#FFFFFF",
}


@lru_cache(maxsize=1)
def _logo_svg_markup() -> str:
    if not _LOGO_SVG.is_file():
        return ""
    raw = _LOGO_SVG.read_text(encoding="utf-8")
    # Email-safe: drop scripts; keep viewBox for scaling
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.I | re.S)
    return raw.strip()


def _otp_digits_html(code: str) -> str:
    digits = html.escape(code.strip())
    spans = "".join(
        f'<span style="display:inline-block;min-width:36px;text-align:center;">{ch}</span>'
        for ch in digits
    )
    return spans


def _promo_section_html() -> str:
    """Eye-catching promo block — two center-aligned service rows (brand colors only)."""
    t, f, s, td, tm, w = (
        BRAND["teal"],
        BRAND["forest"],
        BRAND["surface"],
        BRAND["teal_dark"],
        BRAND["text_muted"],
        BRAND["white"],
    )
    return f"""
          <tr>
            <td align="center" style="padding:0 28px 28px;font-family:Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;">
              <p style="margin:0 0 16px;font-size:12px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;text-align:center;color:{t};">
                ✦ Explore Cheradip ✦
              </p>
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:0 0 12px;">
                <tr>
                  <td align="center" style="padding:18px 20px;background-color:{s};border:2px solid {t};border-radius:12px;text-align:center;">
                    <p style="margin:0 0 6px;font-size:16px;font-weight:700;color:{td};text-align:center;">
                      AI Language Tutor
                    </p>
                    <p style="margin:0 0 12px;font-size:13px;line-height:1.5;color:{tm};text-align:center;">
                      Learn languages with AI practice, OCR scanning, offline packs &amp; teen-voice pronunciation
                    </p>
                    <a href="https://cheradip.com/ailt" style="display:inline-block;padding:10px 22px;background-color:{t};color:{w};font-size:13px;font-weight:700;text-decoration:none;border-radius:999px;text-align:center;">
                      AI Language Tutor Services →
                    </a>
                  </td>
                </tr>
              </table>
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center" style="padding:18px 20px;background-color:{s};border:2px solid {f};border-radius:12px;text-align:center;">
                    <p style="margin:0 0 6px;font-size:16px;font-weight:700;color:{td};text-align:center;">
                      Cheradip.com
                    </p>
                    <p style="margin:0 0 12px;font-size:13px;line-height:1.5;color:{tm};text-align:center;">
                      HSC &amp; Honours MCQ prep, job circulars, study resources &amp; online education
                    </p>
                    <a href="https://cheradip.com" style="display:inline-block;padding:10px 22px;background-color:{f};color:{w};font-size:13px;font-weight:700;text-decoration:none;border-radius:999px;text-align:center;">
                      Cheradip.com Services →
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def render_otp_plain(*, purpose: str, code: str, ttl_minutes: int) -> str:
    return (
        f"AI Language Tutor — {purpose}\n\n"
        f"Your verification code is: {code}\n\n"
        f"This code expires in {ttl_minutes} minutes.\n"
        f"If you did not request this, ignore this message.\n\n"
        f"— Cheradip (AI Language Tutor)\n"
        f"https://cheradip.com\n\n"
        f"---\n"
        f"AI Language Tutor: practice, OCR, AI tutoring, 243+ languages — https://cheradip.com/ailt\n"
        f"Cheradip.com: MCQ prep, jobs, study resources — https://cheradip.com\n"
    )


def render_otp_html(*, purpose: str, code: str, ttl_minutes: int) -> str:
    safe_purpose = html.escape(purpose)
    safe_code = html.escape(code.strip())
    digits = _otp_digits_html(code)
    logo = _logo_svg_markup()
    logo_block = (
        f'<div style="max-width:220px;margin:0 auto;">{logo}</div>'
        if logo
        else (
            '<p style="margin:0;font-size:26px;font-weight:700;letter-spacing:2px;'
            f'color:{BRAND["white"]};">Cheradip</p>'
        )
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{safe_purpose} — AI Language Tutor</title>
</head>
<body style="margin:0;padding:0;background-color:{BRAND["surface"]};">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:{BRAND["surface"]};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:520px;background-color:{BRAND["white"]};border-radius:16px;overflow:hidden;border:1px solid #B0BEC5;">
          <tr>
            <td align="center" style="padding:28px 24px 20px;background:linear-gradient(135deg,skyblue,darkgreen,skyblue);">
              {logo_block}
              <p style="margin:12px 0 0;font-size:13px;font-weight:600;letter-spacing:0.5px;color:{BRAND["white"]};opacity:0.95;">
                AI Language Tutor
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 28px 24px;font-family:Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;">
              <h1 style="margin:0 0 8px;font-size:22px;line-height:1.3;color:{BRAND["teal"]};font-weight:700;">
                {safe_purpose}
              </h1>
              <p style="margin:0 0 24px;font-size:15px;line-height:1.5;color:{BRAND["text_muted"]};">
                Enter this verification code in the app to continue.
              </p>
              <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center" style="padding:22px 16px;background-color:{BRAND["surface"]};border:2px solid {BRAND["teal"]};border-radius:12px;">
                    <div style="font-family:Consolas,Monaco,Courier New,monospace;font-size:34px;font-weight:700;letter-spacing:10px;color:{BRAND["teal_dark"]};line-height:1;">
                      {digits}
                    </div>
                    <div style="display:none;font-size:0;line-height:0;max-height:0;overflow:hidden;mso-hide:all;">
                      {safe_code}
                    </div>
                  </td>
                </tr>
              </table>
              <p style="margin:24px 0 0;font-size:14px;line-height:1.5;color:{BRAND["text_muted"]};">
                This code expires in <strong>{ttl_minutes} minutes</strong>.
                Do not share it with anyone — Cheradip staff will never ask for your code.
              </p>
            </td>
          </tr>
{_promo_section_html()}
          <tr>
            <td style="padding:18px 28px 24px;background-color:{BRAND["background"]};border-top:1px solid {BRAND["surface"]};font-family:Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;">
              <p style="margin:0;font-size:12px;line-height:1.5;color:{BRAND["text_faint"]};">
                If you did not request this email, you can safely ignore it.
              </p>
              <p style="margin:10px 0 0;font-size:12px;line-height:1.5;color:{BRAND["teal"]};">
                <a href="https://cheradip.com" style="color:{BRAND["teal"]};text-decoration:none;font-weight:600;">Cheradip</a>
                &nbsp;·&nbsp; AI Language Tutor
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
