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
    return {
        "name": "Leaf Accounts Without Parent",
        "category": "Chart of Accounts",
        "status": "fail" if offenders else "pass",
        "message": f"{len(offenders)} account(s) have no parent group." if offenders else "All accounts are correctly grouped.",
        "details": offenders[:10],
    }

def check_fiscal_year_configured(session, base_url):
    res = _get_list(session, base_url, "Fiscal Year", fields=["name"])
    if not res:
        return {"name": "Fiscal Year", "category": "Configuration", "status": "fail", "message": "No fiscal year configured.", "details": []}
    return {"name": "Fiscal Year", "category": "Configuration", "status": "pass", "message": f"{len(res)} fiscal year(s) configured.", "details": []}

def check_default_currency_set(session, base_url):
    res = session.get(f"{base_url}/api/resource/Global Defaults/Global Defaults")
    currency = res.json().get("data", {}).get("default_currency", "")
    return {"name": "Default Currency", "category": "Configuration", "status": "pass" if currency else "fail", "message": f"Default currency: '{currency}'." if currency else "Default currency not configured.", "details": []}

def check_tax_templates_missing(session, base_url):
    sales_tax = 0.16  # example
