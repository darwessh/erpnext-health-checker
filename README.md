# erpnext-health-checker
A serverless tool that connects to any ERPNext instance via API, runs a checklist audit (missing cost centers, unlinked taxes, GL mismatches, etc.), and outputs a PDF report with a score and recommendations.

The Flask app now serves a frontend at `/` where you can submit ERPNext credentials and download the generated PDF report.
