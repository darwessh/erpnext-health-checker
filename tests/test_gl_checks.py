"""Unit tests for gl_checks.py — all HTTP calls are mocked."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from decimal import Decimal
import pytest

import gl_checks as G


BASE = "https://erp.example.com"


# ── shared helpers ────────────────────────────────────────────────────────────

def _ok(data):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"data": data}
    return r


def _ok_msg(msg):
    """Simulate a frappe.db.sql response (message key)."""
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"message": msg}
    return r


def _err():
    r = MagicMock()
    r.status_code = 500
    return r


def _company(name="Acme", ar="1200-AR", ap="2100-AP",
              stock=None, inventory=None):
    return {
        "name": name,
        "default_receivable_account": ar,
        "default_payable_account": ap,
        "stock_adjustment_account": stock,
        "default_inventory_account": inventory,
    }


# ── _get_list pagination ──────────────────────────────────────────────────────

class TestGetList:
    def test_single_page(self):
        session = MagicMock()
        session.get.return_value = _ok([{"name": "A"}])
        result = G._get_list(session, BASE, "Payment Entry")
        assert result == [{"name": "A"}]

    def test_paginates(self):
        session = MagicMock()
        session.get.side_effect = [
            _ok([{"name": "A"}, {"name": "B"}]),
            _ok([{"name": "C"}]),
        ]
        result = G._get_list(session, BASE, "Payment Entry", limit=2)
        assert len(result) == 3
        assert session.get.call_count == 2

    def test_timeout_kwarg(self):
        session = MagicMock()
        session.get.return_value = _ok([])
        G._get_list(session, BASE, "Payment Entry")
        _, kwargs = session.get.call_args
        assert kwargs.get("timeout") == 30


# ── _query ────────────────────────────────────────────────────────────────────

class TestQuery:
    def test_returns_message_on_success(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _ok_msg([{"balance": "1000.00"}])
        result = G._query(session, BASE, "SELECT 1")
        assert result == [{"balance": "1000.00"}]

    def test_returns_empty_on_failure(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _err()
        result = G._query(session, BASE, "SELECT 1")
        assert result == []

    def test_timeout_kwarg(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _ok_msg([])
        G._query(session, BASE, "SELECT 1")
        _, get_kwargs = session.get.call_args
        assert get_kwargs.get("timeout") == 30
        _, post_kwargs = session.post.call_args
        assert post_kwargs.get("timeout") == 30


# ── check_ar_gl_mismatch ─────────────────────────────────────────────────────

class TestCheckArGlMismatch:
    def _make_session(self, companies, invoices, gl_balance):
        session = MagicMock()

        def get_side(url, **kwargs):
            if "/Company" in url:
                return _ok(companies)
            if "/Sales Invoice" in url:
                return _ok(invoices)
            # frappe.db.sql (GL balance)
            if "frappe.db.sql" in url:
                return _ok_msg([{"balance": str(gl_balance)}])
            return _ok([])

        def post_side(url, **kwargs):
            return MagicMock(status_code=200)

        session.get.side_effect = get_side
        session.post.side_effect = post_side
        return session

    def test_pass_when_balanced(self):
        session = self._make_session(
            [_company()],
            [{"name": "SINV-001", "outstanding_amount": "1000.00"}],
            gl_balance="1000.00",
        )
        r = G.check_ar_gl_mismatch(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_mismatch(self):
        session = self._make_session(
            [_company()],
            [{"name": "SINV-001", "outstanding_amount": "1000.00"}],
            gl_balance="500.00",
        )
        r = G.check_ar_gl_mismatch(session, BASE)
        assert r["status"] == "fail"
        assert r["delta"] > 0

    def test_skip_company_without_ar_account(self):
        session = self._make_session(
            [_company(ar="")],
            [],
            gl_balance="0",
        )
        r = G.check_ar_gl_mismatch(session, BASE)
        assert r["status"] == "pass"


# ── check_ap_gl_mismatch ─────────────────────────────────────────────────────

class TestCheckApGlMismatch:
    def _make_session(self, companies, invoices, gl_balance):
        session = MagicMock()

        def get_side(url, **kwargs):
            if "/Company" in url:
                return _ok(companies)
            if "/Purchase Invoice" in url:
                return _ok(invoices)
            if "frappe.db.sql" in url:
                return _ok_msg([{"balance": str(gl_balance)}])
            return _ok([])

        session.get.side_effect = get_side
        session.post.return_value = MagicMock(status_code=200)
        return session

    def test_pass(self):
        session = self._make_session(
            [_company()],
            [{"name": "PINV-001", "outstanding_amount": "500.00"}],
            gl_balance="500.00",
        )
        r = G.check_ap_gl_mismatch(session, BASE)
        assert r["status"] == "pass"

    def test_fail(self):
        session = self._make_session(
            [_company()],
            [{"name": "PINV-001", "outstanding_amount": "500.00"}],
            gl_balance="100.00",
        )
        r = G.check_ap_gl_mismatch(session, BASE)
        assert r["status"] == "fail"


# ── check_duplicate_payments ─────────────────────────────────────────────────

class TestCheckDuplicatePayments:
    def test_pass_when_no_duplicates(self):
        session = MagicMock()
        session.get.return_value = _ok_msg([])
        session.post.return_value = MagicMock(status_code=200)
        r = G.check_duplicate_payments(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_duplicates_found(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _ok_msg([{
            "reference_name": "SINV-001",
            "party": "Alice",
            "payment_type": "Receive",
            "cnt": 2,
            "total_allocated": "1000.00",
        }])
        r = G.check_duplicate_payments(session, BASE)
        assert r["status"] == "fail"
        assert "SINV-001" in r["details"][0]


# ── check_unallocated_payments ────────────────────────────────────────────────

class TestCheckUnallocatedPayments:
    def test_pass(self):
        session = MagicMock()
        session.get.return_value = _ok([])
        r = G.check_unallocated_payments(session, BASE)
        assert r["status"] == "pass"
        assert r["delta"] == 0.0

    def test_warn(self):
        session = MagicMock()
        session.get.return_value = _ok([{
            "name": "PE-001",
            "party": "Bob",
            "payment_type": "Receive",
            "paid_amount": "500.00",
            "unallocated_amount": "500.00",
        }])
        r = G.check_unallocated_payments(session, BASE)
        assert r["status"] == "warn"
        assert r["delta"] == pytest.approx(500.0)


# ── check_negative_stock ──────────────────────────────────────────────────────

class TestCheckNegativeStock:
    def test_pass(self):
        session = MagicMock()
        session.get.return_value = _ok_msg([])
        session.post.return_value = MagicMock(status_code=200)
        r = G.check_negative_stock(session, BASE)
        assert r["status"] == "pass"

    def test_fail(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _ok_msg([{
            "item_code": "ITEM-001",
            "item_name": "Widget",
            "warehouse": "Main Warehouse",
            "actual_qty": -5,
        }])
        r = G.check_negative_stock(session, BASE)
        assert r["status"] == "fail"
        assert "Widget" in r["details"][0]


# ── check_journal_entries_missing_cost_center ─────────────────────────────────

class TestCheckJournalEntriesMissingCostCenter:
    def test_pass(self):
        session = MagicMock()
        session.get.return_value = _ok_msg([])
        session.post.return_value = MagicMock(status_code=200)
        r = G.check_journal_entries_missing_cost_center(session, BASE)
        assert r["status"] == "pass"

    def test_warn(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=200)
        session.get.return_value = _ok_msg([{
            "voucher_no": "JV-001",
            "account": "Sales",
            "posting_date": "2024-01-01",
            "debit": "0",
            "credit": "1000",
        }])
        r = G.check_journal_entries_missing_cost_center(session, BASE)
        assert r["status"] == "warn"
        assert "JV-001" in r["details"][0]


# ── check_advance_payments_not_adjusted ──────────────────────────────────────

class TestCheckAdvancePaymentsNotAdjusted:
    def test_pass_when_no_old_advances(self):
        session = MagicMock()
        session.get.return_value = _ok([])
        r = G.check_advance_payments_not_adjusted(session, BASE)
        assert r["status"] == "pass"

    def test_warn_for_old_unallocated(self):
        session = MagicMock()
        session.get.return_value = _ok([{
            "name": "PE-OLD",
            "party": "Alice",
            "party_type": "Customer",
            "payment_type": "Receive",
            "paid_amount": "1000.00",
            "unallocated_amount": "1000.00",
            "posting_date": "2020-01-01",  # definitely >30 days ago
        }])
        r = G.check_advance_payments_not_adjusted(session, BASE)
        assert r["status"] == "warn"
        assert r["delta"] == pytest.approx(1000.0)

    def test_ignores_recent_advances(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        session = MagicMock()
        session.get.return_value = _ok([{
            "name": "PE-NEW",
            "party": "Bob",
            "party_type": "Customer",
            "payment_type": "Receive",
            "paid_amount": "500.00",
            "unallocated_amount": "500.00",
            "posting_date": recent,
        }])
        r = G.check_advance_payments_not_adjusted(session, BASE)
        assert r["status"] == "pass"


# ── run_gl_checks ─────────────────────────────────────────────────────────────

class TestRunGlChecks:
    def test_catches_exceptions_per_check(self):
        session = MagicMock()
        session.get.side_effect = RuntimeError("boom")
        session.post.side_effect = RuntimeError("boom")
        results = G.run_gl_checks(session, BASE)
        assert len(results) == 10  # 10 checks in gl_checks.py
        for r in results:
            assert r["status"] == "warn"
            assert "Could not complete check" in r["message"]

    def test_result_schema(self):
        """Each result must have the required keys including delta."""
        session = MagicMock()
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"data": [], "message": []}
        session.get.return_value = ok
        session.post.return_value = ok

        results = G.run_gl_checks(session, BASE)
        required = {"name", "category", "status", "message", "details"}
        for r in results:
            assert required.issubset(r.keys()), f"Missing keys in {r}"
            assert "delta" in r
