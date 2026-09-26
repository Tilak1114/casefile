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


def restore(path: Path) -> None:
    with path.open("rb") as src:
        subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "mongorestore", "--archive", "--gzip", "--drop"],
            stdin=src, check=True,
        )
