from flask import Flask, request, send_file, render_template
from flask_cors import CORS
from checks import run_all_checks
from gl_checks import run_gl_checks
from report import generate_report
import requests, base64, io
import os

app = Flask(__name__)
cors_origins = os.getenv("CORS_ORIGINS", "").strip()
if cors_origins:
    allowed_origins = [origin for origin in (raw_origin.strip() for raw_origin in cors_origins.split(",")) if origin]
    CORS(app, resources={r"/audit": {"origins": allowed_origins}})

@app.route("/audit", methods=["POST"])
def audit():
    body = request.get_json(silent=True)
    if body is None:
        if request.data:
            return {"error": "Invalid JSON payload"}, 400
        body = {}
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    api_secret = body.get("api_secret", "")

    if not all([base_url, api_key, api_secret]):
        return {"error": "missing fields"}, 400

    session = requests.Session()
    session.headers["Authorization"] = f"token {api_key}:{api_secret}"

    test = session.get(f"{base_url}/api/method/frappe.auth.get_logged_user", timeout=30)
    if test.status_code != 200:
        return {"error": "Authentication failed"}, 401

    results = run_all_checks(session, base_url) + run_gl_checks(session, base_url)
    pdf_b64 = generate_report(results, base_url)

    return send_file(
        io.BytesIO(base64.b64decode(pdf_b64)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="erpnext_health_report.pdf"
    )

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
