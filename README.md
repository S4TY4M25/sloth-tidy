# 🦥 sloth-tidy

**Do less. Your Downloads folder tidies itself, powered by an AI model running on your own computer.**

sloth-tidy is a lazy, fully local file organizer built with Python, plain HTML/CSS/JavaScript, Ollama and Qwen 2.5 (1.5B). Point it at a messy folder and it sorts your files into folders, gives documents readable names, and lets you undo everything with one click.

Built as a submission for the Open-Source AI Challenge: **Slow and Steady** (International Sloth Day edition).

## ✨ Features

- 🗂️ **Automatic sorting**: images, videos, audio, archives, installers and code are filed by type; screenshots are detected by name.
- 🤖 **Local AI for documents**: a small open-weight model reads the start of each document and picks a category and a short, descriptive file name.
- 👀 **Review before anything moves**: a plan table shows every move, tagged *AI*, *Rule* or *Keywords*. Untick anything you don't want.
- ↩️ **One-click undo**: every run is journaled, so Undo restores every file, even after you restart the app.
- 🧪 **Demo mode**: "Try a demo mess" creates a fake messy folder so you can see it work without touching your real files.
- 🔌 **Works without the model too**: if Ollama isn't running, built-in offline keyword rules take over.
- 🔒 **Local inference**: no API key, no cloud, no uploads.

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| Python (standard library) | Sorting engine and the local web server |
| HTML, CSS, JavaScript | The web interface (no frameworks, no CDN, so it works offline) |
| Ollama | Local model inference |
| Qwen 2.5 (`qwen2.5:1.5b`) | Document categorization and naming |
| pypdf (optional) | Reading text from PDFs |

## 📁 Project Structure

```
sloth-tidy/
├── backend.py        # engine + command-line tool: rules, model calls, planning, apply/undo
├── server.py         # small local server connecting the page to the backend
├── requirements.txt
├── README.md
└── frontend/
    ├── index.html    # page structure
    ├── style.css     # the look
    └── script.js     # buttons, plan table, calls to the server
```

## 🚀 Installation and Setup

### Prerequisites

- Python 3.9 or later
- [Ollama](https://ollama.com) installed on your computer (optional but recommended)
- About 1 GB of free space for the model

### 1. Clone the repository

```bash
git clone https://github.com/S4TY4M25/sloth-tidy.git
cd sloth-tidy
```

### 2. Install the optional dependency

The app itself needs nothing beyond Python. This only adds PDF text reading:

```bash
python -m pip install -r requirements.txt
```

### 3. Download the AI model

Make sure Ollama is installed and running, then enter:

```bash
ollama pull qwen2.5:1.5b
```

To confirm the download:

```bash
ollama list
```

### 4. Launch sloth-tidy

```bash
python server.py
```

Open http://127.0.0.1:8765 if your browser doesn't open automatically. (On Windows, use `py server.py` if `python` isn't recognized.)

## 💡 Example Usage

1. Click **✨ Try a demo mess**, or paste a folder path such as your Downloads folder.
2. Review the plan, for example:

| File | Goes to | How |
|---|---|---|
| `IMG_4821.jpg` | `Images/IMG_4821.jpg` | Rule |
| `Screenshot 2026-10-12 at 9.41.03 PM.png` | `Screenshots/…` | Rule |
| `vlc-setup.exe` | `Installers/vlc-setup.exe` | Rule |
| `scan0001.txt` (an electricity bill) | `Finance/electricity-bill-october-2026.txt` | AI / Keywords |
| `notes (2).md` (weekly sync notes) | `Work/weekly-sync-with-design-team.md` | AI / Keywords |

3. Click **Tidy**. Changed your mind? Click **Undo**.

Document results vary with the model, since they are AI-generated. Review the plan before applying.

### Command line (optional)

```bash
python backend.py ~/Downloads            # dry run: prints the plan
python backend.py ~/Downloads --apply    # move the files
python backend.py ~/Downloads --undo     # reverse the last run
python backend.py ~/Downloads --no-llm   # rules only, no model
python backend.py ~/Downloads --model llama3.2:3b
```

To tidy automatically every night, add a cron job (the truly lazy part):

```
0 21 * * * /usr/bin/python3 /path/to/backend.py ~/Downloads --apply
```

## 🛡️ Safety

- Nothing moves until you click Tidy. Scanning only shows a plan.
- Files are only moved and renamed, never deleted, and never overwritten (name clashes get `-2`, `-3`, and so on).
- Files modified in the last 5 minutes are skipped, so half-finished downloads are left alone.
- The server listens on `127.0.0.1` only and requires a per-session token, so other machines and other websites can't control it.

## 🔐 Why Open-Weight, Local AI?

Your invoices, notes and study material are read by a model on your own machine instead of being sent to a cloud API. Once Ollama and the model are installed, everything runs without internet: the page, the server and the model. There is no API key and no per-file cost, and you can swap the model from the dropdown or edit the category list in `backend.py` to make it your own.

## ⚠️ Limitations

- Only files directly inside the chosen folder are organized; existing subfolders are left alone.
- A 1.5B model is fast but sometimes picks vague names. Try a larger model for better results.
- Scanned PDFs with no text layer can't be read by a text model.
- Image content is not analyzed; images are sorted by file type and name only.
- Running the AI part requires a local Ollama installation and a downloaded model. Without it, the app uses simpler keyword rules.

## 🔮 Future Improvements

- Vision model support for sorting photos by content
- Custom categories editable from the web interface
- Duplicate file detection
- Built-in scheduling
- Packaging as a one-click desktop app

## 👨‍💻 Author

S4TY4M25

## 📄 License

MIT