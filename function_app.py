import json
import logging
from typing import Any, Dict

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _normalize_body(body: Dict[str, Any]) -> Dict[str, Any]:
	return {
		"source": str(body.get("source", "unknown")),
		"user_id": str(body.get("user_id", "unknown")),
		"command": body.get("command", ""),
		"context": str(body.get("context", "")),
	}


@app.route(route="sandy_brain", methods=["POST"])
def sandy_brain(req: func.HttpRequest) -> func.HttpResponse:
	try:
		body = req.get_json()
	except ValueError:
		return func.HttpResponse(
			json.dumps({"ok": False, "error": "invalid_json"}, ensure_ascii=False),
			status_code=400,
			mimetype="application/json",
		)

	payload = _normalize_body(body if isinstance(body, dict) else {})
	logging.info("Sandy brain request source=%s user=%s", payload["source"], payload["user_id"])

	response = {
		"ok": True,
		"status": "alive",
		"message": "Sultan Tech is online",
		"echo": payload,
	}
	return func.HttpResponse(
		json.dumps(response, ensure_ascii=False),
		status_code=200,
		mimetype="application/json",
	)

