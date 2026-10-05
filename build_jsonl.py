
from pathlib import Path
import json

src = Path("output/pages")
dest = Path("output/kb_documents.jsonl")

def split_frontmatter(text):
    meta = {}
    if not text.startswith("---\n"):
        return meta, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return meta, text
    raw = text[4:end]
    body = text[end+5:].strip()
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            meta[k.strip()] = json.loads(v.strip())
        except Exception:
            meta[k.strip()] = v.strip().strip('"')
    return meta, body

with dest.open("w", encoding="utf-8") as out:
    for f in sorted(src.glob("*.md")):
        meta, body = split_frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
        out.write(json.dumps({
            "id": f.stem,
            "text": body,
            "metadata": {**meta, "local_file": str(f)}
        }, ensure_ascii=False) + "\n")

print(dest)
