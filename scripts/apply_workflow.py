"""Apply surgical fix to kb-capture workflow (n8n 2.38.5).
PUT payload: {name, nodes, connections, settings} — no versionId, no active.
Changes:
  1. New node 'Create kDrive share link' (POST /2/drive/{id}/files/{fid}/link, right=public).
  2. Linear chain: Save Image to Disk -> Upload to kDrive -> Create kDrive share link
     -> Create a database page -> Edit Fields1 -> Respond to Webhook1.
  3. Notion page: date property fixed (range: false, date: $now.toISO()), Files & media
     -> kDrive public share URL, all property expressions re-sourced from Save Image to Disk,
     body blocks (OCR paragraph + inline image) inlined via contentType blockUi.
  4. Append Notion Children removed (content now created with the page in one call).
  5. Edit Fields1: explicit assignments incl. notion_url + kdrive_url + markdown with image links.
  6. Respond to Webhook1: JSON with title, markdown, notion_url, kdrive_url (+summary, ocr, filename, tags).
  7. Edit Fields: filename fallback if AI omits it.
"""
import copy
import json
import uuid

from kb_common import api, save

import os as _os
WF = _os.environ.get("N8N_WORKFLOW_ID", "<WORKFLOW_ID>")

status, wf = api("GET", f"/workflows/{WF}")
assert status == 200, f"GET failed: {status}"
save("kb_workflow_backup_before_fix.json", wf)

nodes = {n["name"]: n for n in wf["nodes"]}
HIDDEN_TYPE = '={{$parameter["&key"].split("|").pop()}}'

# ---------------------------------------------------------------- 1. new share-link node
share_node = {
    "id": str(uuid.uuid4()),
    "name": "Create kDrive share link",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.5,
    "position": [1040, 208],
    "credentials": {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "kDrive Upload Token"}},
    "parameters": {
        "method": "POST",
        "url": "=https://api.infomaniak.com/2/drive/<DRIVE_ID>/files/{{ $json.data.id }}/link",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ right: "public", can_download: true }) }}',
        "options": {},
    },
}

# ---------------------------------------------------------------- 2. Edit Fields: filename fallback
ef = nodes["Edit Fields"]["parameters"]["assignments"]["assignments"]
for a in ef:
    if a["name"] == "filename":
        a["value"] = ("={{ JSON.parse($json.choices[0].message.content).filename "
                      "|| ('capture-' + $now.toFormat('yyyy-MM-dd-HHmmss')) }}")

# ---------------------------------------------------------------- 3. Notion page node
notion = nodes["Create a database page"]
notion["position"] = [1232, 0]
notion["parameters"]["title"] = "={{ $('Save Image to Disk').item.json.title }}"
notion["parameters"]["propertiesUi"]["propertyValues"] = [
    {
        "key": "Summary|rich_text",
        "type": HIDDEN_TYPE,
        "textContent": "={{ $('Save Image to Disk').item.json.summary }}",
    },
    {
        "key": "Tags|multi_select",
        "type": HIDDEN_TYPE,
        "multiSelectValue": "={{ $('Save Image to Disk').item.json.tags }}",
    },
    {
        "key": "Source|select",
        "type": HIDDEN_TYPE,
        "selectValue": "iOS Screenshot",
    },
    {
        "key": "Created|date",
        "type": HIDDEN_TYPE,
        "range": False,
        "includeTime": True,
        "date": "={{ $now.toISO() }}",
        "timezone": "Europe/Paris",
    },
    {
        "key": "Text|rich_text",
        "type": HIDDEN_TYPE,
        "textContent": "={{ $('Save Image to Disk').item.json.ocr }}",
    },
    {
        "key": "Files & media|files",
        "type": HIDDEN_TYPE,
        "fileUrls": {
            "multipleValues": False,
            "fileUrl": [
                {
                    "name": "={{ $('Save Image to Disk').item.json.title }}.png",
                    "url": "={{ $('Create kDrive share link').item.json.data.url }}",
                }
            ],
        },
    },
]
notion["parameters"]["contentType"] = "blockUi"
notion["parameters"]["blockUi"] = {
    "blockValues": [
        {
            "richText": True,
            "text": {
                "text": [
                    {
                        "textType": "text",
                        "text": "={{ $('Save Image to Disk').item.json.ocr }}",
                    }
                ]
            },
        },
        {
            "type": "image",
            "url": "={{ 'https://n8n.example.com/media/' + $('Save Image to Disk').item.json.filename + '.png' }}",
        },
    ]
}

# ---------------------------------------------------------------- 4. Edit Fields1 (explicit)
sid = "$('Save Image to Disk').item.json"
kd = "$('Create kDrive share link').item.json.data.url"
markdown_expr = (
    "={{ `---\n"
    "source: screenshot\n"
    "created: ${new Date().toISOString()}\n"
    "tags:\n"
    "${" + sid + ".tags.map(tag => `  - ${tag}`).join('\\n')}\n"
    "---\n\n"
    "# ${" + sid + ".title}\n\n"
    "## Summary\n\n"
    "${" + sid + ".summary}\n\n"
    "## Original text\n\n"
    "${" + sid + ".ocr}\n\n"
    "![screenshot](https://n8n.example.com/media/${" + sid + ".filename}.png)\n\n"
    "[View on kDrive](" + kd + ")\n"
    "` }}"
)
ef1 = nodes["Edit Fields1"]
ef1["position"] = [1424, 0]
ef1["parameters"] = {
    "assignments": {
        "assignments": [
            {"id": str(uuid.uuid4()), "name": "title",
             "value": "={{ " + sid + ".title }}", "type": "string"},
            {"id": str(uuid.uuid4()), "name": "summary",
             "value": "={{ " + sid + ".summary }}", "type": "string"},
            {"id": str(uuid.uuid4()), "name": "tags",
             "value": "={{ " + sid + ".tags }}", "type": "array"},
            {"id": str(uuid.uuid4()), "name": "ocr",
             "value": "={{ " + sid + ".ocr }}", "type": "string"},
            {"id": str(uuid.uuid4()), "name": "filename",
             "value": "={{ " + sid + ".filename }}", "type": "string"},
            {"id": str(uuid.uuid4()), "name": "notion_url",
             "value": "={{ $json.url }}", "type": "string"},
            {"id": str(uuid.uuid4()), "name": "kdrive_url",
             "value": "=" + kd, "type": "string"},
            {"id": str(uuid.uuid4()), "name": "markdown",
             "value": markdown_expr, "type": "string"},
        ]
    },
    "options": {},
}

# ---------------------------------------------------------------- 5. Respond node
resp = nodes["Respond to Webhook1"]
resp["position"] = [1616, 0]
E1 = "$('Edit Fields1').item.json"
resp["parameters"] = {
    "respondWith": "json",
    "responseBody": (
        "={\n"
        f'  "title": {{{{ JSON.stringify({E1}.title) }}}},\n'
        f'  "markdown": {{{{ JSON.stringify({E1}.markdown) }}}},\n'
        f'  "notion_url": {{{{ JSON.stringify({E1}.notion_url) }}}},\n'
        f'  "kdrive_url": {{{{ JSON.stringify({E1}.kdrive_url) }}}},\n'
        f'  "summary": {{{{ JSON.stringify({E1}.summary) }}}},\n'
        f'  "ocr": {{{{ JSON.stringify({E1}.ocr) }}}},\n'
        f'  "filename": {{{{ JSON.stringify({E1}.filename) }}}},\n'
        f'  "tags": {{{{ JSON.stringify({E1}.tags) }}}}\n'
        "}"
    ),
    "options": {"responseCode": 200},
}

# ---------------------------------------------------------------- 6. assemble node list
wf["nodes"] = [
    nodes["Webhook"],
    nodes["HTTP Request"],
    nodes["Edit Fields"],
    nodes["Save Image to Disk"],
    nodes["Upload to kDrive"],
    share_node,
    nodes["Create a database page"],
    nodes["Edit Fields1"],
    nodes["Respond to Webhook1"],
]
# drop "Append Notion Children" (content now inlined in page create)

# ---------------------------------------------------------------- 7. connections (linear)
def conn(target):
    return [{"node": target, "type": "main", "index": 0}]

chain = [
    ("Webhook", "HTTP Request"),
    ("HTTP Request", "Edit Fields"),
    ("Edit Fields", "Save Image to Disk"),
    ("Save Image to Disk", "Upload to kDrive"),
    ("Upload to kDrive", "Create kDrive share link"),
    ("Create kDrive share link", "Create a database page"),
    ("Create a database page", "Edit Fields1"),
    ("Edit Fields1", "Respond to Webhook1"),
]
wf["connections"] = {src: {"main": [conn(dst)]} for src, dst in chain}

payload = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
save("kb_workflow_new.json", {"nodes": wf["nodes"], "connections": wf["connections"]})

status2, res = api("PUT", f"/workflows/{WF}", payload=payload)
print("PUT status:", status2)
if status2 == 200:
    print("Workflow updated. Nodes now:")
    for n in res["nodes"]:
        print(" -", n["name"], "|", n["type"])
else:
    print("ERROR:", json.dumps(res, ensure_ascii=False)[:600])
