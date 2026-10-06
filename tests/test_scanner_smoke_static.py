from pathlib import Path
import re


DIST = Path(__file__).resolve().parents[1] / "site" / "dist"


def test_browser_smoke_uses_production_page_and_real_api():
    smoke = (DIST / "ui-smoke.html").read_text(encoding="utf-8")
    page = (DIST / "lab.html").read_text(encoding="utf-8")
    assert 'src="./lab.html?smoke=1#scanner"' in smoke
    for source in ("lab.js", "scanner.js"):
        assert re.search(r'src="\./' + re.escape(source) + r'(?:\?[^\"]*)?"', page)
    for endpoint in ("/health", "/api/lab/strategies", "/api/lab/scanner/runs",
                     "/api/lab/scanner/candidates"):
        assert endpoint in smoke
    for target in ("scanner-metrics", "scanner-quality", "scanner-candidates",
                   "scanner-funnel", "scanner-regime", "scanner-audit"):
        assert f'id="{target}"' in page
    assert "window.onerror" in smoke and "window.onunhandledrejection" in smoke
    assert "window.onerror" in page and "window.onunhandledrejection" in page
