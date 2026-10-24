#!/usr/bin/env python3
"""sloth-tidy server: connects the frontend/ web page to backend.py.

    python server.py

Opens http://127.0.0.1:8765 in your browser. Zero dependencies (standard library
only). The server listens on localhost only; nothing is sent to the internet.
The AI part is an open-weight model served by Ollama on your own machine.
"""
import argparse
import base64
import io
import json
import os
import secrets
import tempfile
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import backend

JOB_LOCK = threading.Lock()
JOB = {"status": "idle", "done": 0, "total": 0, "current": "", "items": [], "raw": [],
       "folder": None, "skipped_recent": 0, "warnings": [], "error": None}
OLLAMA_HOST = backend.DEFAULT_HOST
FRONTEND = Path(__file__).resolve().parent / "frontend"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/script.js": ("script.js", "application/javascript; charset=utf-8")}


# --------------------------------------------------------------------------- #
# Demo data
# --------------------------------------------------------------------------- #
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def _docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")
    return buf.getvalue()


def make_demo() -> str:
    """Create a fresh, deliberately messy folder of sample files. Returns its path."""
    d = Path(tempfile.mkdtemp(prefix="sloth-tidy-demo-"))
    old = time.time() - 3 * 24 * 3600
    files = {
        "Screenshot 2026-10-12 at 9.41.03 PM.png": _PNG,
        "IMG_4821.jpg": _PNG,
        "vlc-setup.exe": b"MZ demo",
        "project-backup.zip": b"PK demo",
        "train.py": b"print('hello')\n",
        "lofi-beat.mp3": b"ID3 demo",
        "trip.mp4": b"demo",
        "mystery.xyz": b"???",
        "final_FINAL_v3.docx": _docx_bytes(
            "Operating Systems Assignment 3. Semester 5 lecture notes on CPU scheduling: round robin, "
            "shortest job first and priority scheduling. Submit before exam week."),
        "scan0001.txt": b"Electricity bill - October 2026\nAmount due: Rs 1,240\nConsumption: 212 kWh\nPay by UPI before 5 Nov.\n",
        "bill.txt": b"Mobile bill - October\nAmount due: Rs 399\nPay by UPI.\n",
        "notes (2).md": b"# Weekly sync with design team\n- agenda: launch checklist\n- action items: share client feedback\n- next meeting Thursday\n",
        "Untitled document.txt": b"Internship offer letter\nDear Candidate, we are pleased to offer you an internship starting in January.\n",
        "data.csv": b"date,expense,amount\n2026-10-01,groceries,640\n2026-10-03,books,899\n",
        "weekend ideas.txt": b"Weekend dinner ideas\npasta, paneer wrap, khichdi\n",
        "movie.mp4.crdownload": b"partial",
    }
    for name, data in files.items():
        p = d / name
        p.write_bytes(data)
        os.utime(p, (old, old))
    (d / "just-downloaded.txt").write_text("Fresh file, modified a moment ago. sloth-tidy leaves it alone.\n")
    return str(d)


# --------------------------------------------------------------------------- #
# Scan job
# --------------------------------------------------------------------------- #
def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def run_scan(folder: Path, use_llm: bool, model: str, min_age: int):
    def progress(i, total, name):
        with JOB_LOCK:
            JOB.update(done=i, total=total, current=name)

    def warn(msg):
        with JOB_LOCK:
            JOB["warnings"].append(msg)

    try:
        files, recent = backend.eligible_files(folder, min_age)
        with JOB_LOCK:
            JOB.update(total=len(files), skipped_recent=recent)
        raw = backend.plan_items(folder, use_llm=use_llm, model=model, host=OLLAMA_HOST,
                                min_age=min_age, progress=progress, warn=warn)
        items = [{
            "id": i, "name": it["src"].name, "size": _size(it["src"]), "category": it["category"],
            "newname": it["dst"].name, "method": it["method"], "renamed": it["renamed"],
        } for i, it in enumerate(raw)]
        with JOB_LOCK:
            JOB.update(status="done", raw=raw, items=items, can_undo=backend.has_undo(folder))
    except Exception as e:  # surface any failure to the UI instead of dying silently
        with JOB_LOCK:
            JOB.update(status="error", error=f"{type(e).__name__}: {e}")


def resolve_folder(text: str) -> Path:
    folder = Path(os.path.expandvars(os.path.expanduser(str(text).strip()))).resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")
    if folder == Path(folder.anchor):
        raise ValueError("Please pick a specific folder, not the drive root.")
    return folder


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "sloth-tidy"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, api: bool) -> bool:
        # Defends against DNS-rebinding and cross-site requests to this local server.
        if self.headers.get("Host", "").lower() not in self.server.allowed_hosts:
            self._send(403, {"error": "bad host"})
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Token", ""), self.server.token):
            self._send(403, {"error": "bad token"})
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._guard(api=path.startswith("/api/")):
            return
        if path in STATIC:
            name, ctype = STATIC[path]
            data = (FRONTEND / name).read_text(encoding="utf-8")
            if name == "index.html":
                data = data.replace("__TOKEN__", self.server.token)
            return self._send(200, data, ctype)
        if path == "/api/status":
            models = backend.ollama_models(OLLAMA_HOST)
            dl = Path.home() / "Downloads"
            return self._send(200, {
                "ollama": models is not None, "models": models or [],
                "default_model": backend.DEFAULT_MODEL,
                "default_folder": str(dl if dl.is_dir() else Path.home()),
            })
        if path == "/api/job":
            with JOB_LOCK:
                return self._send(200, {k: v for k, v in JOB.items() if k != "raw"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._guard(api=True):
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
        except Exception:
            return self._send(400, {"error": "bad request"})
        try:
            self._route(path, body)
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def _route(self, path, body):
        if path == "/api/demo":
            return self._send(200, {"folder": make_demo()})

        if path == "/api/scan":
            folder = resolve_folder(body.get("folder", ""))
            try:
                min_age = max(0, min(int(body.get("min_age", 5)), 1440))
            except (TypeError, ValueError):
                raise ValueError("min_age must be a number")
            with JOB_LOCK:
                if JOB["status"] == "running":
                    return self._send(409, {"error": "A scan is already running."})
                JOB.update(status="running", done=0, total=0, current="", items=[], raw=[],
                           folder=str(folder), skipped_recent=0, warnings=[], error=None, can_undo=False)
            model = str(body.get("model") or backend.DEFAULT_MODEL)
            threading.Thread(target=run_scan, args=(folder, bool(body.get("use_llm", True)), model, min_age),
                             daemon=True).start()
            return self._send(200, {"ok": True})

        if path == "/api/apply":
            ids = body.get("ids")
            if not isinstance(ids, list):
                raise ValueError("ids must be a list")
            with JOB_LOCK:
                if JOB["status"] != "done" or not JOB["raw"]:
                    raise ValueError("Nothing planned. Scan a folder first.")
                folder = Path(JOB["folder"])
                chosen = sorted({i for i in ids if isinstance(i, int) and 0 <= i < len(JOB["raw"])})
                moves = [(JOB["raw"][i]["src"], JOB["raw"][i]["dst"]) for i in chosen]
            moves = [(s, d) for s, d in moves if s.exists() and s.parent == folder]
            if not moves:
                raise ValueError("No files selected.")
            moved = backend.apply_moves(folder, moves)
            folders = len({d.parent.name for _, d in moves})
            with JOB_LOCK:
                JOB.update(status="idle", raw=[], items=[])
            return self._send(200, {"moved": moved, "folders": folders, "can_undo": backend.has_undo(folder)})

        if path == "/api/undo":
            folder = resolve_folder(body.get("folder", ""))
            restored = backend.undo(folder)
            with JOB_LOCK:
                JOB.update(status="idle", raw=[], items=[])
            return self._send(200, {"restored": restored or 0, "nothing": restored is None,
                                    "can_undo": backend.has_undo(folder)})
        self._send(404, {"error": "not found"})


def main():
    global OLLAMA_HOST
    ap = argparse.ArgumentParser(description="sloth-tidy local web app")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--ollama-host", default=backend.DEFAULT_HOST)
    args = ap.parse_args()
    OLLAMA_HOST = args.ollama_host.rstrip("/")

    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"No free port found starting at {args.port}.")
    server.token = secrets.token_urlsafe(24)
    server.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    url = f"http://127.0.0.1:{port}"
    print(f"sloth-tidy is running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye 🦥")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()