"""Tests for report.py — verifies generate_report() returns a valid PDF."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import base64
import pytest

from report import generate_report


BASE = "https://erp.example.com"

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _result(status="pass", name="Test Check", category="Config",
            message="All good.", details=None, delta=None):
    return {
        "name": name,
        "category": category,
        "status": status,
        "message": message,
        "details": details or [],
        "delta": delta,
    }


# ── generate_report ───────────────────────────────────────────────────────────

class TestGenerateReport:
    def test_returns_string(self):
        results = [_result()]
        output = generate_report(results, BASE)
        assert isinstance(output, str)

    def test_output_is_valid_base64(self):
        results = [_result()]
        output = generate_report(results, BASE)
        # Should not raise
        decoded = base64.b64decode(output)
        assert len(decoded) > 0

    def test_output_is_pdf(self):
        results = [_result()]
        output = generate_report(results, BASE)
        decoded = base64.b64decode(output)
        # PDF files start with the %PDF magic bytes
        assert decoded[:4] == b"%PDF"

    def test_all_statuses(self):
        results = [
            _result("pass", "Check A", "Category X"),
            _result("warn", "Check B", "Category X",
                    details=["item1", "item2"]),
            _result("fail", "Check C", "Category Y",
                    message="3 issues found.", details=["x", "y", "z"]),
        ]
        output = generate_report(results, BASE)
        decoded = base64.b64decode(output)
        assert decoded[:4] == b"%PDF"

    def test_delta_shown_in_report(self):
        """A result with delta > 0 and no details should not crash."""
        results = [_result("fail", "Delta Check", "GL",
                           message="Mismatch.", details=[], delta=1234.56)]
        output = generate_report(results, BASE)
        decoded = base64.b64decode(output)
        assert decoded[:4] == b"%PDF"

    def test_empty_results(self):
        """generate_report must not crash with an empty results list."""
        output = generate_report([], BASE)
        decoded = base64.b64decode(output)
        assert decoded[:4] == b"%PDF"

    def test_score_100_when_all_pass(self):
        """When all checks pass the report should be generated without error."""
        results = [_result("pass", f"Check {i}", "Cat") for i in range(10)]
        output = generate_report(results, BASE)
        assert base64.b64decode(output)[:4] == b"%PDF"

    def test_score_0_when_all_fail(self):
        results = [_result("fail", f"Check {i}", "Cat") for i in range(5)]
        output = generate_report(results, BASE)
        assert base64.b64decode(output)[:4] == b"%PDF"

    def test_many_details(self):
        """Long detail lists should not overflow / crash reportlab."""
        details = [f"Detail item {i}" for i in range(50)]
        results = [_result("fail", "Big Check", "Cat",
                           details=details)]
        output = generate_report(results, BASE)
        assert base64.b64decode(output)[:4] == b"%PDF"
