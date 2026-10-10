"""Validate shipped navigation against the app's real targets (no Frappe runtime needed)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "av_tools"


def validate():
    targets = {}
    for kind in ("doctype", "report", "page", "dashboard", "workspace", "sidebar"):
        for path in APP.glob(f"*/{kind}/*/*.json"):
            doc = json.loads(path.read_text())
            key = (doc["doctype"], doc.get("name") or doc.get("report_name"))
            assert key not in targets, f"Duplicate standard definition: {key}"
            targets[key] = doc
    modules = set((APP / "modules.txt").read_text().splitlines())
    count = 0

    def target(kind, name):
        assert (kind, name) in targets, f"Missing {kind}: {name}"
        doc = targets[(kind, name)]
        assert not doc.get("istable"), f"Child table cannot be navigated to: {name}"
        return doc

    for (kind, name), doc in targets.items():
        if kind not in ("Sidebar", "Workspace"):
            continue
        assert doc["module"] in modules, f"Unknown module: {name}"
        assert doc["standard"] == 1, f"Not standard: {name}"
        if kind == "Sidebar":
            assert doc["app"] == "av_tools"
            assert doc["items"][0]["link_type"] == "Workspace", name
            seen = set()
            for item in doc["items"]:
                if item["type"] != "Link":
                    continue
                key = (item["link_type"], item["link_to"])
                assert key not in seen, f"Duplicate sidebar target: {name} / {key}"
                seen.add(key)
                target(*key)
                count += 1
            continue
        cards = {r["label"] for r in doc["links"] if r["type"] == "Card Break"}
        shortcuts = {r["label"] for r in doc["shortcuts"]}
        for block in json.loads(doc["content"]):
            if block["type"] == "card":
                assert block["data"]["card_name"] in cards, name
            if block["type"] == "shortcut":
                assert block["data"]["shortcut_name"] in shortcuts, name
        for row in doc["links"] + doc["shortcuts"]:
            if row["type"] == "Card Break":
                continue
            kind = row.get("link_type") or row["type"]
            if kind == "URL":
                assert row["url"] in {
                    "/desk/" + n.lower().replace(" ", "-")
                    for k, n in targets if k == "Workspace"
                }, row["url"]
                continue
            linked = target(kind, row["link_to"])
            if kind == "Report" and row.get("link_type"):
                assert row["report_ref_doctype"] == linked["ref_doctype"]
                assert row["is_query_report"] == int(
                    linked["report_type"] in ("Query Report", "Script Report")
                )
            count += 1
    dock = json.loads((APP / "dock/av_tools/av_tools.json").read_text())
    assert dock["standard"] == 1 and dock["app"] == "av_tools" and not dock["user"]
    linked = {r["link_to"] for r in dock["items"]}
    assert linked == {name for kind, name in targets if kind == "Sidebar"}
    for item in dock["items"]:
        target(item["link_type"], item["link_to"])
    legacy = json.loads((APP / "workspace/av_tools/av_tools.json").read_text())
    assert legacy == targets[("Workspace", "AV Tools")], "Divergent legacy workspace"
    print(f"Validated {count} navigation links, {len(linked)} Dock modules and workspace blocks.")


if __name__ == "__main__":
    validate()
