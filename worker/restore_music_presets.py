"""Populate a new private Storage bucket with the licensed music presets.

Run through worker/bootstrap.py so the project configuration is loaded. The
source tracks and their attribution are listed in web/lib/musicPresets.ts.
"""
from __future__ import annotations

import urllib.parse
import urllib.request

import db


TRACKS = {
    "guoxue-ripples": "Ripples",
    "guoxue-ishikari-lore": "Ishikari Lore",
    "guoxue-finding-movement": "Finding Movement",
    "health-morning": "Morning",
    "health-evening": "Evening",
    "health-midsummer-sky": "Midsummer Sky",
}


def main() -> None:
    bucket = db.get_client().storage.from_("artifacts")
    for name, title in TRACKS.items():
        path = f"music-presets/{name}.mp3"
        try:
            if (bucket.info(path) or {}).get("size", 0) > 100_000:
                print(f"{name}: present")
                continue
        except Exception:
            pass
        url = (
            "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
            + urllib.parse.quote(title)
            + ".mp3"
        )
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if len(data) < 100_000 or not (data.startswith(b"ID3") or data[:2] == b"\xff\xfb"):
            raise RuntimeError(f"Invalid MP3 for {name}")
        bucket.upload(path, data, {"content-type": "audio/mpeg", "upsert": "true"})
        print(f"{name}: restored ({len(data)} bytes)")


if __name__ == "__main__":
    main()
