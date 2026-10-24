# sloth-tidy 🦥

**Do less. Your Downloads folder tidies itself.**

A lazy, fully local file tidier with a clean web UI. Point it at a messy folder and it sorts, renames and organizes your files. Documents are read by a small **open-weight model running on your own machine** (via [Ollama](https://ollama.com)). No cloud, no API key, no uploads. The app uses only the Python standard library: there is nothing to `pip install`.

## Quick start (2 minutes)

```bash
# 1. (Recommended) install Ollama from https://ollama.com, then pull a small model
ollama pull qwen2.5:1.5b

# 2. Run the app (Python 3.8+, no dependencies)
python server.py
```

Your browser opens at `http://127.0.0.1:8765`. Click **✨ Try a demo mess** to see it work on a fake messy folder, or paste a real folder path (it defaults to your Downloads).

No Ollama? It still works. Documents fall back to built-in offline keyword rules, and the UI tells you what's going on.

## What you'll see

1. **Scan** a folder. A progress bar shows each file as the local model reads it.
2. **Review the plan.** Stats, a per-category chart and a table of every move (file → new folder and name), each tagged *AI*, *Rule* or *Keywords*. Untick anything you don't want moved.
3. **Tidy.** One click moves the files. **Undo** puts every file back.

## Why open-source AI matters here

- **Private.** Your invoices, notes and study material are read by a model on your own CPU. Nothing is uploaded, ever.
- **Works offline.** The page, the server and the model all run locally. Unplug the Wi-Fi and it still works.
- **Free forever.** No API key, no per-file cost. A 1.5B model runs fine on a CPU-only laptop.
- **Swappable.** Pick any model Ollama serves from the dropdown (`llama3.2:3b`, `gemma2:2b`, ...). Edit the `CATEGORIES` list in `backend.py` to make your own folders.

## How it works

1. **Rules first.** Images, videos, audio, archives, installers and code are sorted by extension, and screenshots by file name. These need no AI, so they're instant.
2. **Local model for documents.** For txt, md, csv, docx and pdf files it reads the first ~1500 characters and asks the model for a category and a short descriptive name, as strict JSON at temperature 0.
3. **Offline fallback.** If the model is missing, gives a bad answer, or shrugs ("Misc"), keyword rules take over (bills → Finance, lectures → Study, meetings → Work).
4. **Safe by design.**
   - Nothing moves until you click Tidy.
   - Files are only moved and renamed, never deleted, and never overwritten: name clashes get `-2`, `-3`, ...
   - Every run is journaled in a hidden `.sloth-tidy` folder, so Undo works even after you restart.
   - Files modified in the last 5 minutes (adjustable) are skipped, so half-finished downloads are left alone.
   - The server only listens on `127.0.0.1` and requires a per-session token, so other websites and other machines can't drive it.

## Command line (optional)

```bash
python backend.py ~/Downloads            # dry run: prints the plan
python backend.py ~/Downloads --apply    # do it
python backend.py ~/Downloads --undo     # reverse the last run
python backend.py ~/Downloads --no-llm   # rules only, no model
python backend.py ~/Downloads --model llama3.2:3b
```

Run it nightly with cron (the truly lazy part):

```
0 21 * * * /usr/bin/python3 /path/to/backend.py ~/Downloads --apply
```

## Files

- `backend.py`: the engine and CLI (rules, model calls, planning, apply/undo)
- `server.py`: tiny local Python server connecting the page to the backend
- `frontend/`: the web UI (`index.html`, `style.css`, `script.js`)

## Optional extras and limits

- `pip install pypdf` lets it read the text of PDFs. Without it, PDFs are sorted by their file names and keywords only.
- Scanned PDFs with no text layer can't be read by any text model.
- A 1.5B model is quick but sometimes picks vague names. Try a larger model for better ones.
- Set a different Ollama address with `python server.py --ollama-host http://host:11434`, or another port with `--port`.