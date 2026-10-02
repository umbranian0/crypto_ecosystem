"""RPT-001-02: convert a stored report's HTML `content` to PDF bytes.

Conversion only -- no second template and no added text, so a status-only
stored report yields a status-only PDF.
"""

from __future__ import annotations


class PdfFetchRefusedError(Exception):
    pass


def _refuse_fetch(url: str, *args: object, **kwargs: object) -> dict:
    # Report content is tenant-derived; never let rendering reach the network
    # or the local filesystem (SSRF / local-file disclosure).
    raise PdfFetchRefusedError("external resource fetching is disabled")


# WeasyPrint >=68 reads this attribute off the fetcher on error; False makes a
# refused resource a warning (resource skipped) rather than aborting the render.
_refuse_fetch._fail_on_errors = False  # type: ignore[attr-defined]


# PDF-only: the per-split results table has ~21 columns and overflows portrait A4.
_PDF_CSS = """
@page { size: A4 landscape; margin: 10mm; }
table { width: 100%; table-layout: auto; }
th, td { font-size: 6.5pt; padding: 1px 2px; overflow-wrap: anywhere; word-break: break-word; }
"""


def render_pdf(html: str) -> bytes:
    # Lazy: the service must still import where WeasyPrint's native libs are absent.
    from weasyprint import CSS, HTML

    return HTML(string=html, url_fetcher=_refuse_fetch).write_pdf(
        stylesheets=[CSS(string=_PDF_CSS)]
    )
