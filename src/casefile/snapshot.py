"""Export and import the case database, so teammates restore it instead of re-running paid work."""

import subprocess
from pathlib import Path

from casefile.config import settings

CONTAINER = "casefile-mongo"


def export(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        subprocess.run(
            ["docker", "exec", CONTAINER, "mongodump", "--archive", "--gzip", f"--db={settings().casefile_database}"],
            stdout=out, check=True,
        )


def restore(path: Path, uri: str | None = None) -> None:
    """Restore into the local container, or into the cluster at `uri` (e.g. the Atlas sandbox)."""
    if uri:
        command = ["mongorestore", f"--uri={uri}", "--archive", "--gzip", "--drop"]
    else:
        command = ["docker", "exec", "-i", CONTAINER, "mongorestore", "--archive", "--gzip", "--drop"]
    with path.open("rb") as src:
        subprocess.run(command, stdin=src, check=True)
