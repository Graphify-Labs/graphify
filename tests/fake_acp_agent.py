"""Minimal ACP v1 agent used by Graphify's transport integration tests."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _send(message: dict) -> None:
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    request_id = message.get("id")
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": 1}
    elif method == "session/new":
        result = {
            "sessionId": "graphify-test",
            "configOptions": [
                {
                    "id": "model",
                    "name": "Model",
                    "type": "select",
                    "currentValue": "default",
                    "options": [],
                },
                {
                    "id": "mode",
                    "name": "Mode",
                    "type": "select",
                    "currentValue": "agent",
                    "options": [],
                },
            ],
        }
    elif method == "session/set_config_option":
        if log_path := os.environ.get("GRAPHIFY_FAKE_ACP_CONFIG_LOG"):
            with Path(log_path).open("a", encoding="utf-8") as log:
                log.write(json.dumps(message["params"], sort_keys=True) + "\n")
        result = {"configOptions": []}
    elif method == "session/prompt":
        _send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "graphify-test",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {
                            "type": "text",
                            "text": '{"nodes": [], "edges": [], "hyperedges": []}',
                        },
                    },
                },
            }
        )
        result = {
            "stopReason": "end_turn",
            "usage": {"inputTokens": 11, "outputTokens": 7, "totalTokens": 18},
        }
    else:
        _send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            }
        )
        continue
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})
