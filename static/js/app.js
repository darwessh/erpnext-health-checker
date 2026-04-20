const form = document.getElementById("audit-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");

const AUDIT_TIMEOUT_MS = 60_000;

function setLoadingState(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.textContent = isLoading ? "Running..." : "Run Audit";
  statusEl.textContent = isLoading ? "Audit in progress. Please wait..." : "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.textContent = "";

  const formData = new FormData(form);
  const payload = {
    base_url: (formData.get("base_url") || "").toString().trim(),
    api_key: (formData.get("api_key") || "").toString().trim(),
    api_secret: (formData.get("api_secret") || "").toString().trim(),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, AUDIT_TIMEOUT_MS);

  try {
    setLoadingState(true);
    const response = await fetch("/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok) {
      let message = "Audit request failed.";
      try {
        const data = await response.json();
        if (data && data.error) {
          message = data.error;
        }
      } catch (parseErr) {
        console.warn("Failed to parse error response JSON.", parseErr);
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "erpnext_health_report.pdf";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
    statusEl.textContent = "Audit complete. Download started.";
  } catch (error) {
    statusEl.textContent = "";
    if (error.name === "AbortError") {
      errorEl.textContent =
        "The audit timed out after 60 seconds. Your ERPNext instance may be slow or unreachable.";
    } else {
      errorEl.textContent = error.message || "Unexpected error occurred.";
    }
  } finally {
    clearTimeout(timeoutId);
    setLoadingState(false);
  }
});
