#!/usr/bin/env python3
"""sloth-tidy: a lazy, fully local file tidier.

Sorts and renames the clutter in a folder (e.g. Downloads) using a small
open-weight model running on your own machine via Ollama. No cloud, no API key,
no file contents ever leave your computer.

Safe by default: it only PRINTS a plan. Pass --apply to move files, and --undo
to reverse the last run. (server.py + frontend/ is the web UI for the same logic.)
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "qwen2.5:1.5b"
DEFAULT_HOST = "http://localhost:11434"

CATEGORIES = [
    "Documents", "Study", "Finance", "Work", "Images", "Screenshots",
    "Videos", "Audio", "Archives", "Code", "Installers", "Misc",
]

# Cheap rules first: the model is only asked about files where content matters.
EXT_RULES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".apk", ".appimage"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".ipynb", ".sh"},
}
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log", ".rtf", ".tex"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".odt", ".xlsx", ".pptx"} | TEXT_EXTS
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download"}
JOURNAL_DIR = ".sloth-tidy"


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def rule_category(path: Path):
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg"} and re.match(r"(?i)^(screenshot|screen shot|scr)", path.name):
        return "Screenshots"
    for cat, exts in EXT_RULES.items():
        if ext in exts:
            return cat
    return None


def read_snippet(path: Path, limit: int = 1500) -> str:
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXTS:
            with open(path, "r", errors="ignore") as f:
                return f.read(limit)
        if ext == ".docx":
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf8", "ignore")
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))[:limit]
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # optional dependency
            except ImportError:
                return ""
            reader = PdfReader(str(path))
            return (reader.pages[0].extract_text() or "")[:limit] if reader.pages else ""
    except Exception:
        return ""
    return ""


def ollama_models(host: str = DEFAULT_HOST, timeout: float = 2.0):
    """Names of locally installed Ollama models, or None if Ollama isn't reachable."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return None


def ask_model(host: str, model: str, filename: str, snippet: str):
    prompt = (
        "You tidy files. Given a file name and the start of its content, reply with JSON "
        'only: {"category": <one of %s>, "name": <short descriptive kebab-case name, '
        "no extension, max 6 words>}.\n\nFile name: %s\nContent start:\n%s"
        % (CATEGORIES, filename, snippet or "(no readable text)")
    )
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "format": "json", "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(f"{host}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(json.loads(r.read())["response"])
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    wanted = str(data.get("category", "")).strip().lower()
    cat = next((c for c in CATEGORIES if c.lower() == wanted), "Misc")
    return cat, str(data.get("name", ""))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


KEYWORDS = {
    "Finance": ["invoice", "receipt", "bill", "amount due", "payment", "bank", "statement",
                "tax", "salary", "expense", "upi", "emi", "balance", "kwh"],
    "Study": ["lecture", "assignment", "syllabus", "semester", "exam", "course", "professor",
              "chapter", "homework", "university", "viva", "lab manual", "scheduling"],
    "Work": ["meeting", "agenda", "client", "offer letter", "internship", "resume", "sprint",
             "standup", "quarterly", "stakeholder", "action items"],
}


def heuristic_doc(path: Path, snippet: str):
    """Offline fallback when no model is available: keyword scoring plus a title guess.

    Returns (category, new_stem_or_None, matched_bool)."""
    text = f"{path.stem} {snippet}".lower()
    scores = {c: sum(text.count(k) for k in kws) for c, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    cat, matched = (best, True) if scores[best] > 0 else ("Documents", False)
    stem = None
    if path.suffix.lower() in {".txt", ".md"}:
        first = next((ln.strip(" #*-\t") for ln in snippet.splitlines() if ln.strip(" #*-\t")), "")
        words = first.split()
        if 1 <= len(words) <= 10 and len(first) <= 70 and re.search(r"[A-Za-z]{3}", first):
            stem = slug(" ".join(words[:6])) or None
    return cat, stem, matched


def unique(dest: Path, reserved=frozenset()) -> Path:
    """First free variant of dest: not on disk and not already promised to another file."""
    if not dest.exists() and dest not in reserved:
        return dest
    n = 2
    while True:
        cand = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
        if not cand.exists() and cand not in reserved:
            return cand
        n += 1


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def eligible_files(folder: Path, min_age: int = 5):
    """(files to consider, count skipped because they were modified very recently)."""
    cutoff = time.time() - min_age * 60
    files, recent = [], 0
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in SKIP_SUFFIXES:
            continue
        if p.stat().st_mtime > cutoff:  # probably still downloading / in use
            recent += 1
            continue
        files.append(p)
    return files, recent


def plan_items(folder: Path, *, use_llm=True, model=DEFAULT_MODEL, host=DEFAULT_HOST,
               min_age=5, progress=None, warn=None):
    """Return a list of dicts: src, dst, category, method ('rule' | 'ai' | 'fallback'), renamed."""
    files, _ = eligible_files(folder, min_age)
    items, reserved, llm_ok = [], set(), use_llm
    for i, p in enumerate(files):
        if progress:
            progress(i, len(files), p.name)
        cat, new_stem, method = rule_category(p), p.stem, "rule"
        if cat is None:
            is_doc = p.suffix.lower() in DOC_EXTS
            cat, method = ("Documents" if is_doc else "Misc"), "fallback"
            if is_doc:
                snippet = read_snippet(p)
                ai_done = False
                if llm_ok:
                    try:
                        cat, name = ask_model(host, model, p.name, snippet)
                        method, ai_done = "ai", True
                        if slug(name):
                            new_stem = slug(name)
                        if cat == "Misc":  # a small model shrugged: let keyword rules take a look
                            h_cat, h_stem, h_matched = heuristic_doc(p, snippet)
                            if h_matched:
                                cat = h_cat
                            if not slug(name) and h_stem:
                                new_stem = h_stem
                    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                        llm_ok = False  # model is down; stop asking for the rest of this run
                        if warn:
                            warn(f"Model unreachable ({e}); using offline keyword rules for the rest.")
                    except Exception:
                        pass  # bad answer for this one file; use the keyword fallback below
                if not ai_done:
                    cat, stem, matched = heuristic_doc(p, snippet)
                    method = "keywords" if matched else "fallback"
                    if stem:
                        new_stem = stem
        dest = unique(folder / cat / (new_stem + p.suffix.lower()), reserved)
        reserved.add(dest)
        if dest != p:
            items.append({"src": p, "dst": dest, "category": cat, "method": method,
                          "renamed": dest.stem != p.stem})
    if progress:
        progress(len(files), len(files), "")
    return items


def plan(folder: Path, args):
    """CLI wrapper: list of (src, dst) tuples."""
    warn = lambda m: print(f"  ({m})", file=sys.stderr)  # noqa: E731
    items = plan_items(folder, use_llm=not args.no_llm, model=args.model, host=args.host,
                       min_age=args.min_age, warn=warn)
    return [(it["src"], it["dst"]) for it in items]


# --------------------------------------------------------------------------- #
# Applying / undoing
# --------------------------------------------------------------------------- #
def apply_moves(folder: Path, moves):
    done, reserved = [], set()
    try:
        for src, dst in moves:
            dst = unique(dst, reserved)  # never overwrite anything that appeared since planning
            reserved.add(dst)
            dst.parent.mkdir(exist_ok=True)
            src.rename(dst)
            done.append({"from": str(src), "to": str(dst)})
    finally:
        if done:  # always journal what actually moved, even if a later move failed
            jd = folder / JOURNAL_DIR
            jd.mkdir(exist_ok=True)
            (jd / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json").write_text(json.dumps(done, indent=2))
    return len(done)


def undo(folder: Path):
    """Reverse the most recent run. Returns files restored, or None if there is nothing to undo."""
    jd = folder / JOURNAL_DIR
    journals = sorted(jd.glob("*.json")) if jd.exists() else []
    if not journals:
        return None
    last = journals[-1]
    restored = 0
    for m in reversed(json.loads(last.read_text())):
        src, dst = Path(m["to"]), Path(m["from"])
        if src.exists():
            src.rename(unique(dst))
            restored += 1
    last.unlink()
    # tidy up category folders that are now empty (never touches non-empty ones)
    for cat in CATEGORIES:
        d = folder / cat
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return restored


def has_undo(folder: Path) -> bool:
    jd = folder / JOURNAL_DIR
    return jd.exists() and any(jd.glob("*.json"))


def main():
    ap = argparse.ArgumentParser(description="Lazy local file tidier powered by an open-weight model.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--apply", action="store_true", help="actually move files (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="reverse the last --apply run")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--no-llm", action="store_true", help="rules only, skip the model")
    ap.add_argument("--min-age", type=int, default=5, help="skip files modified in the last N minutes")
    args = ap.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    if args.undo:
        n = undo(folder)
        return print("Nothing to undo." if n is None else f"Restored {n} files.")

    moves = plan(folder, args)
    if not moves:
        return print("Already tidy. Nothing to do. 🦥")
    for src, dst in moves:
        print(f"{src.name}  ->  {dst.relative_to(folder)}")
    if args.apply:
        print(f"\nMoved {apply_moves(folder, moves)} files. Undo with: --undo")
    else:
        print(f"\nDry run: {len(moves)} moves planned. Re-run with --apply to do it.")


if __name__ == "__main__":
    main()