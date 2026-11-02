# Music Library Manager

`static/music/songs.json` is the only authoritative song list. The Music page
loads it directly; Hugo copies it and the referenced files from `static/music/`
to the generated site. Do not edit a second song list.

Run these commands from the repository root in PowerShell:

```powershell
python tools/music_library.py
python tools/music_library.py list
python tools/music_library.py search "song or artist"
python tools/music_library.py add
python tools/music_library.py delete "song or artist"
python tools/music_library.py validate
python tools/music_library.py preview
python tools/music_library.py preview --stop
```

The interactive menu is also available by running the manager without a
subcommand. `add` asks for the title, artist, optional credits/album/year/tags
and link, and a local cover image. It creates a unique ID, copies the cover
into `static/music/assets/`, URL-encodes its page path, checks duplicates, and
writes the song record atomically. Required values and errors are reported
before the operation is considered successful.

`delete` narrows the list by keyword, requires selection and confirmation, and
removes only the selected record. The cover is retained by default. If no
other record references it, the manager offers a separate confirmation before
deleting that image; it refuses paths outside `static/music/assets/`.

`validate` checks JSON parsing, required fields, duplicate IDs and songs,
cover paths/files, responsive cover derivatives, orphan images, and the
Music page's data-loading assumptions. It then builds Hugo into a unique
temporary directory under the repository's ignored `tools/_probe_out/` and
verifies that the generated Music page, JSON, covers, and derivatives are
present. `--no-build` skips the Hugo build.

`preview` explicitly runs the repository's `hugo.exe server` with the
repository root, `hugo.toml`, and port `1313`. The fixed page and data URLs are
<http://localhost:1313/music/> and
<http://localhost:1313/music/songs.json>. If port 1313 is already serving this
project's Hugo preview, the manager verifies the page and exact song-data
contents and reuses it. If another or unverifiable process owns the port, the
manager reports its PID, command, executable, and inferred project path; it
does not stop that process or select another port.

The manager does not stop the preview after browser checks. To stop it
explicitly, run `python tools/music_library.py preview --stop`. This only stops
a Hugo server whose explicit source/config argument identifies this repository
without conflicting project arguments; unrelated or ambiguous listeners are
left running and reported.
The Music data request uses `cache: "no-cache"` so edits do not stay hidden
behind the old fixed `songs.json?v=3` browser-cache key.

The old `tools/add_music.py` importer and `scripts/add-song.ps1` entry point are
retired and fail with a message directing users to this manager.
