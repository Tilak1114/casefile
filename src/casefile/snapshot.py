"""Export and restore the case database, so teammates restore it instead of re-running paid work.

Uses the local mongodump/mongorestore against any connection string, local or Atlas.
"""

import subprocess
from pathlib import Path

from casefile.config import settings


# Kept out of the snapshot: the caches and source PDFs are already in git and in Atlas, and would
# multiply the snapshot's size.
EXCLUDED = ["cache", "sources.files", "sources.chunks"]


def export(path: Path, uri: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = settings()
    subprocess.run(
        ["mongodump", f"--uri={uri or config.atlas_connection_string}", f"--db={config.casefile_database}",
         f"--archive={path}", "--gzip", *[f"--excludeCollection={c}" for c in EXCLUDED]],
        check=True,
    )


def restore(path: Path, uri: str | None = None) -> None:
    subprocess.run(
        ["mongorestore", f"--uri={uri or settings().atlas_connection_string}", f"--archive={path}", "--gzip", "--drop"],
        check=True,
    )
