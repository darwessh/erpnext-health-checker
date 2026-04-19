"""
GL Reconciliation Checks
========================
These hit the GL Entry doctype directly — they catch transaction-level integrity
failures that compound silently during implementation and only surface at month-end.

Each check follows the same return contract as checks.py:
{
    "name": str,
    "category": str,
    "status": "pass" | "warn" | "fail",
    "message": str,
    "details": list[str],
    "delta": float | None   # monetary impact where applicable
}
"""

import json
from decimal import Decimal, ROUND_HALF_UP


# ── Public API ────────────────────────────────────────────────────────────────

def run_gl_checks(session, base_url):
    checks = [
        check_ar_gl_mismatch,
        check_ap_gl_mismatch,
        check_stock_gl_mismatch,
        check_duplicate_payments,
        check_unallocated_payments,
        check_direct_gl_entries_to_control_accounts,
        check_negative_stock,
        check_journal_entries_missing_cost_center,
        check_cancelled_invoices_with_open_payments,
        check_advance_payments_not_adjusted,
    ]

    results = []
    for check in checks:
        try:
            result = check(session, base_url)
        except Exception as e:
            result = {
                "name": check.__name__.replace("check_", "").replace("_", " ").title(),
                "category": "GL Integrity",
                "status": "warn",
                "message": f"Could not complete check: {str(e)}",
                "details": [],
                "delta": None,
            }
        results.append(result)

    return results


# ── AR / AP Control Account Reconciliation ────────────────────────────────────

def check_ar_gl_mismatch(session, base_url):
    """
    Core check: sum of outstanding Sales Invoices must equal
    the net balance of the AR control account in the GL.
    Any delta means someone posted directly to AR — the ledger is lying.
    """
    companies = _get_companies(session, base_url)
    mismatches = []
    total_delta = Decimal("0")

    for company in companies:
        ar_account = company.get("default_receivable_account")
        if not ar_account:
            continue

        # Outstanding invoices (submitted, not cancelled)
        invoices = _get_list(session, base_url, "Sales Invoice",
                             filters=[
                                 ["docstatus", "=", 1],
                                 ["company", "=", company["name"]],
                                 ["outstanding_amount", "!=", 0],
                             ],
                             fields=["name", "outstanding_amount"])
        invoice_total = sum(Decimal(str(r.get("outstanding_amount", 0))) for r in invoices)

        # GL balance of AR account
        gl_balance = _get_gl_account_balance(session, base_url, ar_account, company["name"])

        delta = abs(gl_balance - invoice_total)
        if delta > Decimal("0.50"):   # tolerance: 50 cents for rounding
            mismatches.append(
                f"{company['name']}: Invoice AR = {_fmt(invoice_total)}, "
                f"GL AR = {_fmt(gl_balance)}, delta = {_fmt(delta)}"
            )
            total_delta += delta

    return {
        "name": "AR Control Account vs Outstanding Invoices",
        "category": "GL Reconciliation",
        "status": "fail" if mismatches else "pass",
        "message": (
            f"Mismatch detected in {len(mismatches)} company/companies. "
            f"Total unexplained delta: {_fmt(total_delta)}. "
            "Likely cause: direct journal entries posted to the AR account."
        ) if mismatches else "AR control account balances match outstanding invoices.",
        "details": mismatches,
        "delta": float(total_delta),
    }


def check_ap_gl_mismatch(session, base_url):
    """
    Same logic for Accounts Payable — outstanding Purchase Invoices
    must match the AP control account GL balance.
    """
    companies = _get_companies(session, base_url)
    mismatches = []
    total_delta = Decimal("0")

    for company in companies:
        ap_account = company.get("default_payable_account")
        if not ap_account:
            continue

        invoices = _get_list(session, base_url, "Purchase Invoice",
                             filters=[
                                 ["docstatus", "=", 1],
                                 ["company", "=", company["name"]],
                                 ["outstanding_amount", "!=", 0],
                             ],
                             fields=["name", "outstanding_amount"])
        invoice_total = sum(Decimal(str(r.get("outstanding_amount", 0))) for r in invoices)

        gl_balance = _get_gl_account_balance(session, base_url, ap_account, company["name"])

        delta = abs(gl_balance - invoice_total)
        if delta > Decimal("0.50"):
            mismatches.append(
                f"{company['name']}: Invoice AP = {_fmt(invoice_total)}, "
                f"GL AP = {_fmt(gl_balance)}, delta = {_fmt(delta)}"
            )
            total_delta += delta

    return {
        "name": "AP Control Account vs Outstanding Invoices",
        "category": "GL Reconciliation",
        "status": "fail" if mismatches else "pass",
        "message": (
            f"Mismatch in {len(mismatches)} company/companies. "
            f"Total delta: {_fmt(total_delta)}. "
            "Check for direct journal entries to AP account."
        ) if mismatches else "AP control account balances match outstanding purchase invoices.",
        "details": mismatches,
        "delta": float(total_delta),
    }


# ── Stock / GL Mismatch ───────────────────────────────────────────────────────

def check_stock_gl_mismatch(session, base_url):
    """
    ERPNext maintains a parallel stock ledger (SLE) and GL ledger.
    If someone posts a manual journal to a stock/warehouse account,
    they diverge permanently. This compares stock valuation vs GL stock accounts.
    """
    companies = _get_companies(session, base_url)
    mismatches = []
    total_delta = Decimal("0")

    for company in companies:
        # Get stock account balance from GL
        stock_account = company.get("stock_adjustment_account") or \
                        company.get("default_inventory_account")
        if not stock_account:
            continue

        # Stock value from Stock Ledger Entry
        sle_res = _query(session, base_url,
            f"""SELECT SUM(stock_value_difference) as total
                FROM `tabStock Ledger Entry`
                WHERE company = '{company["name"]}'
                AND is_cancelled = 0""")
        sle_value = Decimal(str(sle_res[0].get("total") or 0))

        # GL balance of stock account
        gl_balance = _get_gl_account_balance(session, base_url, stock_account, company["name"])

        delta = abs(gl_balance - sle_value)
        if delta > Decimal("1.00"):   # wider tolerance for stock rounding
            mismatches.append(
                f"{company['name']}: Stock Ledger = {_fmt(sle_value)}, "
                f"GL Stock = {_fmt(gl_balance)}, delta = {_fmt(delta)}"
            )
            total_delta += delta

    return {
        "name": "Stock Ledger vs GL Stock Account",
        "category": "GL Reconciliation",
        "status": "fail" if mismatches else "pass",
        "message": (
            f"Stock-GL divergence in {len(mismatches)} company/companies. "
            f"Delta: {_fmt(total_delta)}. "
            "Manual journals were likely posted directly to stock accounts."
        ) if mismatches else "Stock ledger and GL stock accounts are in sync.",
        "details": mismatches,
        "delta": float(total_delta),
    }


# ── Duplicate Payments ────────────────────────────────────────────────────────

def check_duplicate_payments(session, base_url):
    """
    Detects Payment Entries referencing the same Sales/Purchase Invoice
    more than once — classic double-payment mistake during training period.
    """
    # Pull payment references
    refs = _query(session, base_url,
        """SELECT pr.reference_name, pe.party, pe.payment_type,
                  COUNT(*) as cnt, SUM(pr.allocated_amount) as total_allocated
           FROM `tabPayment Entry Reference` pr
           JOIN `tabPayment Entry` pe ON pe.name = pr.parent
           WHERE pe.docstatus = 1
             AND pr.reference_doctype IN ('Sales Invoice', 'Purchase Invoice')
           GROUP BY pr.reference_name, pe.party, pe.payment_type
           HAVING COUNT(*) > 1""")

    offenders = [
        f"{r['reference_name']} paid {r['cnt']}x by {r['party']} "
        f"(total allocated: {_fmt(Decimal(str(r.get('total_allocated', 0))))})"
        for r in refs
    ]

    return {
        "name": "Duplicate Payment Entries",
        "category": "Transactions",
        "status": "fail" if offenders else "pass",
        "message": (
            f"{len(offenders)} invoice(s) have been paid more than once. "
            "Review and cancel the duplicate Payment Entry."
        ) if offenders else "No duplicate payments detected.",
        "details": offenders[:10],
        "delta": None,
    }


# ── Unallocated Payments ──────────────────────────────────────────────────────

def check_unallocated_payments(session, base_url):
    """
    Payment Entries submitted but not linked to any invoice.
    Real money sitting in the system as unreconciled advance.
    Often caused by paying before creating the invoice.
    """
    res = _get_list(session, base_url, "Payment Entry",
                    filters=[
                        ["docstatus", "=", 1],
                        ["unallocated_amount", ">", 0],
                    ],
                    fields=["name", "party", "payment_type",
                            "paid_amount", "unallocated_amount"])

    total_unallocated = sum(
        Decimal(str(r.get("unallocated_amount", 0))) for r in res
    )

    offenders = [
        f"{r['name']} ({r.get('payment_type', '')} | {r.get('party', 'unknown')}) "
        f"— unallocated: {_fmt(Decimal(str(r.get('unallocated_amount', 0))))}"
        for r in res[:10]
    ]

    return {
        "name": "Unallocated Payment Entries",
        "category": "Transactions",
        "status": "warn" if res else "pass",
        "message": (
            f"{len(res)} payment(s) with unallocated amount totalling "
            f"{_fmt(total_unallocated)}. These won't clear outstanding invoices."
        ) if res else "All payments are fully allocated to invoices.",
        "details": offenders,
        "delta": float(total_unallocated),
    }


# ── Direct GL Entries to Control Accounts ────────────────────────────────────

def check_direct_gl_entries_to_control_accounts(session, base_url):
    """
    Catches manual Journal Entries posted directly to AR or AP control accounts.
    This is the most common cause of AR/AP-GL mismatch above.
    ERPNext warns against this but doesn't block it.
    """
    companies = _get_companies(session, base_url)
    control_accounts = []
    for c in companies:
        if c.get("default_receivable_account"):
            control_accounts.append(c["default_receivable_account"])
        if c.get("default_payable_account"):
            control_accounts.append(c["default_payable_account"])

    if not control_accounts:
        return {
            "name": "Direct Journals to Control Accounts",
            "category": "GL Integrity",
            "status": "warn",
            "message": "Could not determine control accounts to check.",
            "details": [],
            "delta": None,
        }

    account_list = ", ".join(f"'{a}'" for a in control_accounts)
    entries = _query(session, base_url,
        f"""SELECT gle.account, gle.voucher_type, gle.voucher_no,
                   gle.debit, gle.credit, gle.posting_date
            FROM `tabGL Entry` gle
            WHERE gle.account IN ({account_list})
              AND gle.voucher_type = 'Journal Entry'
              AND gle.is_cancelled = 0
            ORDER BY gle.posting_date DESC
            LIMIT 50""")

    offenders = [
        f"{r['voucher_no']} ({r['posting_date']}) — {r['account']} "
        f"Dr:{_fmt(Decimal(str(r.get('debit',0))))} "
        f"Cr:{_fmt(Decimal(str(r.get('credit',0))))}"
        for r in entries
    ]

    return {
        "name": "Direct Journal Entries to AR/AP Control Accounts",
        "category": "GL Integrity",
        "status": "fail" if offenders else "pass",
        "message": (
            f"{len(offenders)} manual journal entry line(s) posted directly to "
            "AR or AP control accounts. This breaks subledger reconciliation."
        ) if offenders else "No direct journal entries to control accounts found.",
        "details": offenders[:10],
        "delta": None,
    }


# ── Negative Stock ────────────────────────────────────────────────────────────

def check_negative_stock(session, base_url):
    """
    Items with negative stock quantity in any warehouse.
    Means deliveries/issues happened before goods were received —
    causes FIFO/AVCO valuation to break irreversibly.
    """
    res = _query(session, base_url,
        """SELECT item_code, warehouse, actual_qty, item_name
           FROM `tabBin`
           WHERE actual_qty < 0
           ORDER BY actual_qty ASC
           LIMIT 50""")

    offenders = [
        f"{r.get('item_name', r['item_code'])} @ {r['warehouse']}: "
        f"qty = {r['actual_qty']}"
        for r in res
    ]

    return {
        "name": "Negative Stock",
        "category": "Stock Integrity",
        "status": "fail" if offenders else "pass",
        "message": (
            f"{len(offenders)} item-warehouse combination(s) have gone negative. "
            "Valuation for these items is now unreliable. "
            "Backdate a Purchase Receipt to fix transaction order."
        ) if offenders else "No negative stock detected across all warehouses.",
        "details": offenders[:10],
        "delta": None,
    }


# ── Journal Entries Missing Cost Center ──────────────────────────────────────

def check_journal_entries_missing_cost_center(session, base_url):
    """
    P&L account GL entries with no cost center = invisible in departmental reports.
    Very common when accountants post manually and skip the cost center field.
    """
    entries = _query(session, base_url,
        """SELECT gle.voucher_no, gle.account, gle.posting_date,
                  gle.debit, gle.credit
           FROM `tabGL Entry` gle
           JOIN `tabAccount` acc ON acc.name = gle.account
           WHERE gle.voucher_type = 'Journal Entry'
             AND gle.cost_center IS NULL
             AND gle.is_cancelled = 0
             AND acc.report_type = 'Profit and Loss'
           ORDER BY gle.posting_date DESC
           LIMIT 100""")

    offenders = [
        f"{r['voucher_no']} ({r['posting_date']}) — {r['account']}"
        for r in entries
    ]

    return {
        "name": "P&L Journal Entries Missing Cost Center",
        "category": "GL Integrity",
        "status": "warn" if offenders else "pass",
        "message": (
            f"{len(offenders)} P&L journal entry line(s) have no cost center. "
            "These won't appear in departmental cost reports."
        ) if offenders else "All P&L journal entries have a cost center assigned.",
        "details": offenders[:10],
        "delta": None,
    }


# ── Cancelled Invoices with Open Payments ─────────────────────────────────────

def check_cancelled_invoices_with_open_payments(session, base_url):
    """
    Payment Entries linked to invoices that have since been cancelled.
    The payment is still submitted and allocated — the money is stuck.
    """
    res = _query(session, base_url,
        """SELECT pr.reference_name, pr.parent as payment_entry,
                  pr.allocated_amount, pe.party
           FROM `tabPayment Entry Reference` pr
           JOIN `tabPayment Entry` pe ON pe.name = pr.parent
           JOIN `tabSales Invoice` si ON si.name = pr.reference_name
           WHERE pe.docstatus = 1
             AND si.docstatus = 2
             AND pr.reference_doctype = 'Sales Invoice'
           LIMIT 50

           UNION ALL

           SELECT pr.reference_name, pr.parent,
                  pr.allocated_amount, pe.party
           FROM `tabPayment Entry Reference` pr
           JOIN `tabPayment Entry` pe ON pe.name = pr.parent
           JOIN `tabPurchase Invoice` pi ON pi.name = pr.reference_name
           WHERE pe.docstatus = 1
             AND pi.docstatus = 2
             AND pr.reference_doctype = 'Purchase Invoice'
           LIMIT 50""")

    total = sum(Decimal(str(r.get("allocated_amount", 0))) for r in res)
    offenders = [
        f"{r['payment_entry']} → {r['reference_name']} (cancelled) "
        f"| {r.get('party', 'unknown')} | "
        f"{_fmt(Decimal(str(r.get('allocated_amount', 0))))}"
        for r in res
    ]

    return {
        "name": "Payments Linked to Cancelled Invoices",
        "category": "Transactions",
        "status": "fail" if offenders else "pass",
        "message": (
            f"{len(offenders)} payment(s) are still allocated to cancelled invoices. "
            f"Total stuck amount: {_fmt(total)}. "
            "Cancel the Payment Entry and re-allocate or refund."
        ) if offenders else "No payments found linked to cancelled invoices.",
        "details": offenders[:10],
        "delta": float(total),
    }


# ── Advance Payments Not Adjusted ────────────────────────────────────────────

def check_advance_payments_not_adjusted(session, base_url):
    """
    Payment Entries marked as advance (paid before invoice) but never
    linked to a final invoice. Common in hospitality and retail deposits.
    Overstates cash received and understates AR.
    """
    res = _get_list(session, base_url, "Payment Entry",
                    filters=[
                        ["docstatus", "=", 1],
                        ["payment_type", "in", ["Receive", "Pay"]],
                        ["unallocated_amount", ">", 0],
                    ],
                    fields=["name", "party", "party_type", "payment_type",
                            "paid_amount", "unallocated_amount", "posting_date"])

    # Filter for old ones (>30 days) — new advances are fine
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    old = [r for r in res if r.get("posting_date", "9999") < cutoff]

    total = sum(Decimal(str(r.get("unallocated_amount", 0))) for r in old)
    offenders = [
        f"{r['name']} ({r.get('posting_date', '')}) — "
        f"{r.get('party_type', '')} {r.get('party', 'unknown')}: "
        f"{_fmt(Decimal(str(r.get('unallocated_amount', 0))))} unallocated"
        for r in old[:10]
    ]

    return {
        "name": "Advance Payments Older Than 30 Days (Unadjusted)",
        "category": "Transactions",
        "status": "warn" if old else "pass",
        "message": (
            f"{len(old)} advance payment(s) older than 30 days with "
            f"{_fmt(total)} still unallocated. "
            "Create and link the corresponding invoice or refund the advance."
        ) if old else "No stale advance payments found.",
        "details": offenders,
        "delta": float(total),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_companies(session, base_url):
    return _get_list(session, base_url, "Company",
                     fields=["name", "default_receivable_account",
                             "default_payable_account",
                             "stock_adjustment_account",
                             "default_inventory_account"])


def _get_gl_account_balance(session, base_url, account, company):
    """Returns net balance (debit - credit) for an account."""
    res = _query(session, base_url,
        f"""SELECT SUM(debit) - SUM(credit) as balance
            FROM `tabGL Entry`
            WHERE account = '{account}'
              AND company = '{company}'
              AND is_cancelled = 0""")
    if res and res[0].get("balance") is not None:
        return Decimal(str(res[0]["balance"]))
    return Decimal("0")


def _query(session, base_url, sql):
    """Run a raw SQL query via ERPNext's query API."""
    res = session.post(
        f"{base_url}/api/method/frappe.client.get_list",
        json={"method": "frappe.client.run_query", "args": {"query": sql}}
    )
    # ERPNext exposes raw SQL via /api/method/frappe.db.sql for permitted users
    res2 = session.get(
        f"{base_url}/api/method/frappe.db.sql",
        params={"query": sql, "as_dict": 1}
    )
    if res2.status_code == 200:
        return res2.json().get("message", [])
    return []


def _get_list(session, base_url, doctype, filters=None, fields=None, limit=500):
    params = {
        "limit_page_length": limit,
        "fields": json.dumps(fields or ["name"]),
    }
    if filters:
        params["filters"] = json.dumps(filters)
    res = session.get(f"{base_url}/api/resource/{doctype}", params=params)
    if res.status_code != 200:
        return []
    return res.json().get("data", [])


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"
