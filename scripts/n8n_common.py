"""Shared helpers for talking to a self-hosted n8n instance.

Reads `n8n.env` from the same folder (git-ignored!) with at least:

    N8N_SELFHOSTED_URL=https://n8n.example.com
    N8N_SELFHOSTED_API_KEY=<your n8n public REST API key>
"""
import json
import os
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env(filename="n8n.env"):
    """Load a simple KEY=VALUE env file from the script folder."""
    env = {}
    with open(os.path.join(ROOT, filename), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
BASE_URL = ENV.get("N8N_SELFHOSTED_URL", "https://n8n.example.com").rstrip("/")
API_KEY = ENV["N8N_SELFHOSTED_API_KEY"]


def api(method, path, payload=None, raw_body=None, timeout=60):
    """Call the n8n public REST API. Returns (status, parsed_json_or_text)."""
    url = BASE_URL + "/api/v1" + path
    data = raw_body if raw_body is not None else (
        json.dumps(payload).encode("utf-8") if payload is not None else None
    )
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-N8N-API-KEY": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        status = e.code
    except Exception as e:
        return 0, {"error": str(e)}
    try:
        return status, json.loads(body)
    except Exception:
        return status, body


def save(name, obj):
    """Dump a dict/list as pretty JSON next to this script (debug helper)."""
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print("saved", name)
