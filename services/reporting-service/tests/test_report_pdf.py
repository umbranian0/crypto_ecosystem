"""RPT-001-02: `GET /reports/{id}?format=pdf`.

Contract tests stub `render_pdf`; the `pdf_render` tests exercise real
WeasyPrint and auto-skip where its native libs are unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.repositories import get_report_repository
from app.renderers import pdf
from app.repositories.interfaces import ReportRecord
from app.routers import report_retrieval

from tests.test_get_report_endpoint import (
    REPORT_OWNED_BY_A,
    REPORT_OWNED_BY_B,
    TENANT_A,
    FakeReportRepository,
)

STATUS_ONLY_ID = "status-only"
_STATUS_ONLY_HTML = "<html><body><h1>Audit report</h1><p>Run status: failed</p></body></html>"
_COMPLETED_HTML = (
    "<html><body><h1>Audit report</h1><h2>3. Results table</h2>"
    "<table><tr><th>split</th><th>MAE</th></tr><tr><td>1</td><td>0.01</td></tr></table>"
    "<p>Statistical accuracy is not economic value.</p></body></html>"
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo = FakeReportRepository()
    repo.reports[STATUS_ONLY_ID] = ReportRecord(
        id=STATUS_ONLY_ID,
        tenant_id=TENANT_A,
        run_id="run-failed",
        report_kind="validation_audit",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content=_STATUS_ONLY_HTML,
        status="generated",
    )
    monkeypatch.setattr(pdf, "render_pdf", lambda html: b"%PDF-stub:" + html.encode())
    app = FastAPI()
    app.include_router(report_retrieval.router, prefix="/reports")
    app.dependency_overrides[get_report_repository] = lambda: repo
    return TestClient(app)


def test_pdf_format_returns_attachment(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_A}?format=pdf", headers={"X-Tenant-Id": TENANT_A}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="audit-report-{REPORT_OWNED_BY_A}.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


def test_pdf_cross_tenant_404_identical_to_nonexistent(client: TestClient) -> None:
    cross = client.get(
        f"/reports/{REPORT_OWNED_BY_B}?format=pdf", headers={"X-Tenant-Id": TENANT_A}
    )
    missing = client.get(
        "/reports/nope?format=pdf", headers={"X-Tenant-Id": TENANT_A}
    )

    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_unknown_format_is_422(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_A}?format=docx", headers={"X-Tenant-Id": TENANT_A}
    )

    assert response.status_code == 422


def test_default_json_shape_unchanged(client: TestClient) -> None:
    response = client.get(f"/reports/{REPORT_OWNED_BY_A}", headers={"X-Tenant-Id": TENANT_A})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert set(response.json()) == {
        "id", "run_id", "report_kind", "generated_at", "status", "content"
    }


def test_status_only_report_pdf_converts_stored_html_unchanged(client: TestClient) -> None:
    response = client.get(
        f"/reports/{STATUS_ONLY_ID}?format=pdf", headers={"X-Tenant-Id": TENANT_A}
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-stub:" + _STATUS_ONLY_HTML.encode()


def test_url_fetcher_refuses_every_url() -> None:
    for url in ("http://example.com/x.png", "https://example.com/", "file:///etc/passwd"):
        with pytest.raises(pdf.PdfFetchRefusedError):
            pdf._refuse_fetch(url)


@pytest.fixture()
def real_render():
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("WeasyPrint native libraries unavailable on this host")
    return pdf.render_pdf


@pytest.mark.pdf_render
@pytest.mark.parametrize("html", [_COMPLETED_HTML, _STATUS_ONLY_HTML], ids=["completed", "status_only"])
def test_real_render_produces_pdf(real_render, html: str) -> None:
    data = real_render(html)

    assert data.startswith(b"%PDF-")
    assert len(data) > 1000


@pytest.mark.pdf_render
def test_real_render_does_not_fetch_external_resources(real_render) -> None:
    html = '<html><body><p>x</p><img src="file:///etc/hostname"><img src="http://127.0.0.1:1/a.png"></body></html>'

    assert real_render(html).startswith(b"%PDF-")


def _wide_results_html() -> str:
    cols = (
        ["Split", "Train", "Purge", "Test"]
        + [f"Model {m}" for m in ("MAE", "RMSE", "sMAPE", "MASE", "DA", "F1", "OOS R2")]
        + [f"Naive0 {m}" for m in ("MAE", "RMSE", "sMAPE", "MASE", "DA", "F1", "OOS R2")]
        + ["DM statistic", "DM p-value", "DM verdict"]
    )
    head = "".join(f"<th>{c}</th>" for c in cols)
    span = "2024-01-01T00:00:00+00:00 -- 2024-02-01T00:00:00+00:00"
    row = "<td>0</td>" + f"<td>{span}</td>" * 3 + "<td>0.0012345678901234</td>" * 17
    return f"<html><body><h2>Results</h2><table><thead><tr>{head}</tr></thead><tbody><tr>{row}</tr></tbody></table></body></html>"


@pytest.mark.pdf_render
def test_real_render_wide_results_table_fits_page(real_render) -> None:
    from weasyprint import CSS, HTML

    def right_edges(box):
        if type(box).__name__ == "TextBox":
            yield box.position_x + box.width
        for child in getattr(box, "children", ()):
            yield from right_edges(child)

    html = _wide_results_html()
    document = HTML(string=html, url_fetcher=pdf._refuse_fetch).render(
        stylesheets=[CSS(string=pdf._PDF_CSS)]
    )
    assert real_render(html).startswith(b"%PDF-")
    for page in document.pages:
        width = page._page_box.margin_width()
        assert max(right_edges(page._page_box)) <= width
