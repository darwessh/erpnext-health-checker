"""Unit tests for checks.py — all HTTP calls are mocked."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, call
import pytest

import checks as C


# ── helpers ────────────────────────────────────────────────────────────────────

BASE = "https://erp.example.com"


def _session(responses):
    """Build a mock session whose .get() returns *responses* in sequence."""
    session = MagicMock()
    session.get.side_effect = responses
    return session


def _ok(data):
    """200 response wrapping *data* under the 'data' key."""
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"data": data}
    return r


def _ok_raw(payload):
    """200 response returning *payload* directly from .json()."""
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    return r


def _err():
    r = MagicMock()
    r.status_code = 500
    return r


# ── _get_list ─────────────────────────────────────────────────────────────────

class TestGetList:
    def test_returns_empty_on_error(self):
        session = _session([_err()])
        result = C._get_list(session, BASE, "Account")
        assert result == []

    def test_single_page(self):
        session = _session([_ok([{"name": "A"}, {"name": "B"}])])
        result = C._get_list(session, BASE, "Account", limit=500)
        assert result == [{"name": "A"}, {"name": "B"}]

    def test_paginates_when_full_page_returned(self):
        # First page: exactly 2 records (page_size=2) → fetch next
        # Second page: 1 record → stop
        session = _session([
            _ok([{"name": "A"}, {"name": "B"}]),
            _ok([{"name": "C"}]),
        ])
        result = C._get_list(session, BASE, "Account", limit=2)
        assert result == [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        assert session.get.call_count == 2

    def test_stops_after_error_mid_pagination(self):
        session = _session([_ok([{"name": "A"}, {"name": "B"}]), _err()])
        result = C._get_list(session, BASE, "Account", limit=2)
        # Returns whatever was fetched before the error
        assert result == [{"name": "A"}, {"name": "B"}]

    def test_passes_timeout(self):
        session = _session([_ok([])])
        C._get_list(session, BASE, "Account")
        _, kwargs = session.get.call_args
        assert kwargs.get("timeout") == 30


# ── check_accounts_missing_group ──────────────────────────────────────────────

class TestCheckAccountsMissingGroup:
    def test_pass_when_no_offenders(self):
        session = _session([_ok([])])
        r = C.check_accounts_missing_group(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_offenders_exist(self):
        session = _session([_ok([{"name": "Acc1"}, {"name": "Acc2"}])])
        r = C.check_accounts_missing_group(session, BASE)
        assert r["status"] == "fail"
        assert "2" in r["message"]
        assert "Acc1" in r["details"]

    def test_details_capped_at_10(self):
        data = [{"name": f"Acc{i}"} for i in range(20)]
        session = _session([_ok(data)])
        r = C.check_accounts_missing_group(session, BASE)
        assert len(r["details"]) <= 10


# ── check_cost_centers_missing ────────────────────────────────────────────────

class TestCheckCostCentersMissing:
    def test_pass_when_all_have_cost_center(self):
        session = _session([_ok([{"name": "Acme", "cost_center": "Main CC"}])])
        r = C.check_cost_centers_missing(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_company_missing_cost_center(self):
        session = _session([_ok([{"name": "Acme", "cost_center": ""}])])
        r = C.check_cost_centers_missing(session, BASE)
        assert r["status"] == "fail"
        assert "Acme" in r["details"]


# ── check_customers_missing_payment_terms ─────────────────────────────────────

class TestCheckCustomersMissingPaymentTerms:
    def test_pass_when_no_customers_missing(self):
        session = _session([_ok([])])
        r = C.check_customers_missing_payment_terms(session, BASE)
        assert r["status"] == "pass"

    def test_warn_when_customers_missing(self):
        session = _session([_ok([
            {"name": "CUST-001", "customer_name": "Alice"},
            {"name": "CUST-002", "customer_name": "Bob"},
        ])])
        r = C.check_customers_missing_payment_terms(session, BASE)
        assert r["status"] == "warn"
        assert "Alice" in r["details"]
        assert "Bob" in r["details"]


# ── check_suppliers_missing_payment_terms ─────────────────────────────────────

class TestCheckSuppliersMissingPaymentTerms:
    def test_pass(self):
        session = _session([_ok([])])
        r = C.check_suppliers_missing_payment_terms(session, BASE)
        assert r["status"] == "pass"

    def test_warn(self):
        session = _session([_ok([{"name": "S-001", "supplier_name": "SupplierX"}])])
        r = C.check_suppliers_missing_payment_terms(session, BASE)
        assert r["status"] == "warn"
        assert "SupplierX" in r["details"]


# ── check_items_missing_income_account ───────────────────────────────────────

class TestCheckItemsMissingIncomeAccount:
    def test_pass(self):
        session = _session([_ok([])])
        r = C.check_items_missing_income_account(session, BASE)
        assert r["status"] == "pass"

    def test_warn(self):
        session = _session([_ok([{"name": "ITEM-1", "item_name": "Widget"}])])
        r = C.check_items_missing_income_account(session, BASE)
        assert r["status"] == "warn"
        assert "Widget" in r["details"]


# ── check_items_missing_expense_account ──────────────────────────────────────

class TestCheckItemsMissingExpenseAccount:
    def test_pass(self):
        session = _session([_ok([])])
        r = C.check_items_missing_expense_account(session, BASE)
        assert r["status"] == "pass"

    def test_warn(self):
        session = _session([_ok([{"name": "ITEM-1", "item_name": "Supply"}])])
        r = C.check_items_missing_expense_account(session, BASE)
        assert r["status"] == "warn"


# ── check_tax_templates_missing ──────────────────────────────────────────────

class TestCheckTaxTemplatesMissing:
    def test_pass_when_both_present(self):
        session = _session([_ok([{"name": "Sales VAT"}]), _ok([{"name": "Purchase VAT"}])])
        r = C.check_tax_templates_missing(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_sales_tax_missing(self):
        session = _session([_ok([]), _ok([{"name": "Purchase VAT"}])])
        r = C.check_tax_templates_missing(session, BASE)
        assert r["status"] == "fail"
        assert "Sales" in r["message"]

    def test_fail_when_both_missing(self):
        session = _session([_ok([]), _ok([])])
        r = C.check_tax_templates_missing(session, BASE)
        assert r["status"] == "fail"


# ── check_unsubmitted_sales_invoices ─────────────────────────────────────────

class TestCheckUnsubmittedSalesInvoices:
    def test_pass(self):
        session = _session([_ok([])])
        r = C.check_unsubmitted_sales_invoices(session, BASE)
        assert r["status"] == "pass"

    def test_warn_with_drafts(self):
        session = _session([_ok([
            {"name": "SINV-001", "customer": "Alice", "grand_total": 500}
        ])])
        r = C.check_unsubmitted_sales_invoices(session, BASE)
        assert r["status"] == "warn"
        assert "SINV-001" in r["details"][0]


# ── check_unsubmitted_purchase_invoices ──────────────────────────────────────

class TestCheckUnsubmittedPurchaseInvoices:
    def test_pass(self):
        session = _session([_ok([])])
        r = C.check_unsubmitted_purchase_invoices(session, BASE)
        assert r["status"] == "pass"

    def test_warn(self):
        session = _session([_ok([
            {"name": "PINV-001", "supplier": "Bob", "grand_total": 300}
        ])])
        r = C.check_unsubmitted_purchase_invoices(session, BASE)
        assert r["status"] == "warn"


# ── check_party_accounts_missing ─────────────────────────────────────────────

class TestCheckPartyAccountsMissing:
    def test_pass_when_all_set(self):
        session = _session([_ok([{
            "name": "Acme",
            "default_receivable_account": "1200 - AR",
            "default_payable_account": "2100 - AP",
        }])])
        r = C.check_party_accounts_missing(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_ar_missing(self):
        session = _session([_ok([{
            "name": "Acme",
            "default_receivable_account": "",
            "default_payable_account": "2100 - AP",
        }])])
        r = C.check_party_accounts_missing(session, BASE)
        assert r["status"] == "fail"
        assert any("AR" in d for d in r["details"])

    def test_fail_when_both_missing(self):
        session = _session([_ok([{
            "name": "Acme",
            "default_receivable_account": "",
            "default_payable_account": "",
        }])])
        r = C.check_party_accounts_missing(session, BASE)
        assert r["status"] == "fail"
        assert len(r["details"]) == 2


# ── check_fiscal_year_configured ─────────────────────────────────────────────

class TestCheckFiscalYearConfigured:
    def test_pass(self):
        session = _session([_ok([{"name": "2024"}])])
        r = C.check_fiscal_year_configured(session, BASE)
        assert r["status"] == "pass"

    def test_fail_when_none(self):
        session = _session([_ok([])])
        r = C.check_fiscal_year_configured(session, BASE)
        assert r["status"] == "fail"


# ── check_default_currency_set ───────────────────────────────────────────────

class TestCheckDefaultCurrencySet:
    def test_pass(self):
        session = _session([_ok_raw({"data": {"default_currency": "USD"}})])
        r = C.check_default_currency_set(session, BASE)
        assert r["status"] == "pass"
        assert "USD" in r["message"]

    def test_fail_when_not_set(self):
        session = _session([_ok_raw({"data": {"default_currency": ""}})])
        r = C.check_default_currency_set(session, BASE)
        assert r["status"] == "fail"


# ── run_all_checks ────────────────────────────────────────────────────────────

class TestRunAllChecks:
    def test_returns_list_of_results(self):
        """
        run_all_checks catches exceptions per-check and still returns a result
        for every check in the list.
        """
        session = MagicMock()
        # Make every call blow up — each check should be caught and produce a warn.
        session.get.side_effect = RuntimeError("network error")
        results = C.run_all_checks(session, BASE)
        assert isinstance(results, list)
        assert len(results) == 12  # 12 checks defined in checks.py
        for r in results:
            assert r["status"] == "warn"
            assert "Could not complete check" in r["message"]

    def test_aggregates_all_check_results(self):
        """All 12 checks run and return a dict with the required keys."""
        session = MagicMock()
        # Most checks call _get_list; a couple call the Global Defaults endpoint.
        # Return sensible empty-data responses for everything.
        ok_list = MagicMock(status_code=200)
        ok_list.json.return_value = {"data": []}
        ok_global = MagicMock(status_code=200)
        ok_global.json.return_value = {"data": {"default_currency": "USD"}}
        # Alternate: return ok_list for list endpoints, ok_global for the singleton
        session.get.return_value = ok_list
        # Override just the Global Defaults call (last in run order)
        # by intercepting on URL
        def side(url, **kwargs):
            if "Global Defaults" in url:
                return ok_global
            return ok_list
        session.get.side_effect = side

        results = C.run_all_checks(session, BASE)
        assert len(results) == 12
        required_keys = {"name", "category", "status", "message", "details"}
        for r in results:
            assert required_keys.issubset(r.keys())
