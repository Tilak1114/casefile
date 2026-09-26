"""MongoDB connection."""

from pymongo import MongoClient
from pymongo.database import Database

from casefile.config import settings


_client: MongoClient | None = None


def client() -> MongoClient:
    """One shared client. The 30 s server selection outlasts an Atlas primary election (a failover
    stopped run full-1 at 5 s); reads and writes are retried once by the driver."""
    global _client
    if _client is None:
        _client = MongoClient(settings().atlas_connection_string, serverSelectionTimeoutMS=30000,
                              retryWrites=True, retryReads=True)
    return _client


def database() -> Database:
    return client()[settings().casefile_database]


def ping() -> bool:
    return client().admin.command("ping").get("ok") == 1.0
