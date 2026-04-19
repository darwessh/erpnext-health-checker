import json
import requests
from checks import run_all_checks
from gl_checks import run_gl_checks
from report import generate_report

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        base_url = body.get("base_url", "").rstrip("/")
        api_key = body.get("api_key", "")
        api_secret = body.get("api_secret", "")

        if not all([base_url, api_key, api_secret]):
            return _response(400, {"error": "base_url, api_key, and api_secret are required."})

        session = _auth_session(base_url, api_key, api_secret)

        # Verify connection
        test = session.get(f"{base_url}/api/method/frappe.auth.get_logged_user")
        if test.status_code != 200:
            return _response(401, {"error": "Authentication failed. Check your API key/secret."})

        results = run_all_checks(session, base_url) + run_gl_checks(session, base_url)
        pdf_bytes = generate_report(results, base_url)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/pdf",
                "Content-Disposition": "attachment; filename=erpnext_health_report.pdf",
                "Access-Control-Allow-Origin": "*",
            },
            "body": pdf_bytes,
            "isBase64Encoded": True,
        }

    except Exception as e:
        return _response(500, {"error": str(e)})


def _auth_session(base_url, api_key, api_secret):
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {api_key}:{api_secret}",
        "Content-Type": "application/json",
    })
    return session


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
