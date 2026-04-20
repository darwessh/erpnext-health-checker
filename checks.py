import json


def run_all_checks(session, base_url):
    checks = [
        check_accounts_missing_group,
        check_cost_centers_missing,
        check_customers_missing_payment_terms,
        check_suppliers_missing_payment_terms,
        check_items_missing_income_account,
        check_items_missing_expense_account,
        check_tax_templates_missing,
        check_unsubmitted_sales_invoices,
        check_unsubmitted_purchase_invoices,
        check_party_accounts_missing,
        check_fiscal_year_configured,
        check_default_currency_set,
    ]
    results = []
    for check in checks:
        try:
            result = check(session, base_url)
        except Exception as e:
            result = {
                "name": check.__name__.replace("check_", "").replace("_", " ").title(),
                "category": "System",
                "status": "warn",
                "message": f"Could not complete check: {str(e)}",
                "details": [],
            }
        results.append(result)
    return results


def check_accounts_missing_group(session, base_url):
    res = _get_list(session, base_url, "Account",
                    filters=[["is_group", "=", 0], ["parent_account", "=", ""]],
                    fields=["name"])
    offenders = [r["name"] for r in res]
    return {"name": "Leaf Accounts Without Parent", "category": "Chart of Accounts", "status": "fail" if offenders else "pass", "message": f"{len(offenders)} account(s) have no parent group." if offenders else "All accounts are correctly grouped.", "details": offenders[:10]}


def check_cost_centers_missing(session, base_url):
    companies = _get_list(session, base_url, "Company", fields=["name", "cost_center"])
    issues = [c["name"] for c in companies if not c.get("cost_center")]
    return {"name": "Company Default Cost Center", "category": "Accounting", "status": "fail" if issues else "pass", "message": f"{len(issues)} company/companies missing a default cost center." if issues else "All companies have a default cost center.", "details": issues}


def check_customers_missing_payment_terms(session, base_url):
    res = _get_list(session, base_url, "Customer", filters=[["payment_terms", "=", ""]], fields=["name", "customer_name"])
    offenders = [r.get("customer_name", r["name"]) for r in res]
    return {"name": "Customers Missing Payment Terms", "category": "Parties", "status": "warn" if offenders else "pass", "message": f"{len(offenders)} customer(s) have no payment terms." if offenders else "All customers have payment terms.", "details": offenders[:10]}


def check_suppliers_missing_payment_terms(session, base_url):
    res = _get_list(session, base_url, "Supplier", filters=[["payment_terms", "=", ""]], fields=["name", "supplier_name"])
    offenders = [r.get("supplier_name", r["name"]) for r in res]
    return {"name": "Suppliers Missing Payment Terms", "category": "Parties", "status": "warn" if offenders else "pass", "message": f"{len(offenders)} supplier(s) have no payment terms." if offenders else "All suppliers have payment terms.", "details": offenders[:10]}


def check_items_missing_income_account(session, base_url):
    res = _get_list(session, base_url, "Item", filters=[["is_sales_item", "=", 1], ["income_account", "=", ""]], fields=["name", "item_name"])
    offenders = [r.get("item_name", r["name"]) for r in res]
    return {"name": "Sales Items Missing Income Account", "category": "Items", "status": "warn" if offenders else "pass", "message": f"{len(offenders)} sales item(s) missing income account." if offenders else "All sales items have an income account.", "details": offenders[:10]}


def check_items_missing_expense_account(session, base_url):
    res = _get_list(session, base_url, "Item", filters=[["is_purchase_item", "=", 1], ["expense_account", "=", ""]], fields=["name", "item_name"])
    offenders = [r.get("item_name", r["name"]) for r in res]
    return {"name": "Purchase Items Missing Expense Account", "category": "Items", "status": "warn" if offenders else "pass", "message": f"{len(offenders)} purchase item(s) missing expense account." if offenders else "All purchase items have an expense account.", "details": offenders[:10]}


def check_tax_templates_missing(session, base_url):
    sales_tax = _get_list(session, base_url, "Sales Taxes and Charges Template", fields=["name"])
    purchase_tax = _get_list(session, base_url, "Purchase Taxes and Charges Template", fields=["name"])
    issues = []
    if not sales_tax: issues.append("No Sales Tax Templates found")
    if not purchase_tax: issues.append("No Purchase Tax Templates found")
    return {"name": "Tax Templates", "category": "Accounting", "status": "fail" if issues else "pass", "message": "; ".join(issues) if issues else f"{len(sales_tax)} sales + {len(purchase_tax)} purchase tax template(s) configured.", "details": []}


def check_unsubmitted_sales_invoices(session, base_url):
    res = _get_list(session, base_url, "Sales Invoice", filters=[["docstatus", "=", 0]], fields=["name", "customer", "grand_total"])
    return {"name": "Draft Sales Invoices", "category": "Transactions", "status": "warn" if res else "pass", "message": f"{len(res)} sales invoice(s) in Draft." if res else "No draft sales invoices.", "details": [f"{r['name']} ({r.get('customer','')}) — {r.get('grand_total',0)}" for r in res[:10]]}


def check_unsubmitted_purchase_invoices(session, base_url):
    res = _get_list(session, base_url, "Purchase Invoice", filters=[["docstatus", "=", 0]], fields=["name", "supplier", "grand_total"])
    return {"name": "Draft Purchase Invoices", "category": "Transactions", "status": "warn" if res else "pass", "message": f"{len(res)} purchase invoice(s) in Draft." if res else "No draft purchase invoices.", "details": [f"{r['name']} ({r.get('supplier','')}) — {r.get('grand_total',0)}" for r in res[:10]]}


def check_party_accounts_missing(session, base_url):
    res = _get_list(session, base_url, "Company", fields=["name", "default_receivable_account", "default_payable_account"])
    issues = []
    for c in res:
        if not c.get("default_receivable_account"): issues.append(f"{c['name']}: missing AR account")
        if not c.get("default_payable_account"): issues.append(f"{c['name']}: missing AP account")
    return {"name": "Company Default AR/AP Accounts", "category": "Accounting", "status": "fail" if issues else "pass", "message": f"{len(issues)} issue(s) found." if issues else "All companies have AR/AP accounts.", "details": issues}


def check_fiscal_year_configured(session, base_url):
    res = _get_list(session, base_url, "Fiscal Year", fields=["name"])
    if not res:
        return {"name": "Fiscal Year", "category": "Configuration", "status": "fail", "message": "No fiscal year configured.", "details": []}
    return {"name": "Fiscal Year", "category": "Configuration", "status": "pass", "message": f"{len(res)} fiscal year(s) configured.", "details": []}


def check_default_currency_set(session, base_url):
    res = session.get(f"{base_url}/api/resource/Global Defaults/Global Defaults", timeout=30)
    currency = res.json().get("data", {}).get("default_currency", "")
    return {"name": "Default Currency", "category": "Configuration", "status": "pass" if currency else "fail", "message": f"Default currency: '{currency}'." if currency else "Default currency not configured.", "details": []}


def _get_list(session, base_url, doctype, filters=None, fields=None, limit=500):
    """Fetch all matching records, paginating in chunks of ``limit`` rows."""
    page_size = limit
    all_records = []
    start = 0
    while True:
        params = {
            "limit_page_length": page_size,
            "limit_start": start,
            "fields": json.dumps(fields or ["name"]),
        }
        if filters:
            params["filters"] = json.dumps(filters)
        res = session.get(
            f"{base_url}/api/resource/{doctype}", params=params, timeout=30
        )
        if res.status_code != 200:
            break
        batch = res.json().get("data", [])
        all_records.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_records
