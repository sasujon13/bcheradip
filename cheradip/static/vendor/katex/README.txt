Bundled KaTeX for PDF export (Playwright) when the server has no outbound CDN access.

Version folder: 0.16.11 (keep in sync with fcheradip package.json and export_question_katex.py).

Deploy this entire vendor/katex tree with the Django app. PDF generation loads:
  cheradip/static/vendor/katex/0.16.11/katex.min.{js,css}
  cheradip/static/vendor/katex/0.16.11/contrib/auto-render.min.js
  cheradip/static/vendor/katex/0.16.11/fonts/*.woff2

To refresh from npm (on a dev machine):
  cd fcheradip && npm install katex@0.16.11 --no-save
  copy dist/* and dist/fonts/* into this folder (see project docs).
