"""MongoDB connection."""

from pymongo import MongoClient
from pymongo.database import Database

from casefile.config import settings


def client() -> MongoClient:
    return MongoClient(settings().atlas_connection_string, serverSelectionTimeoutMS=5000)


def database() -> Database:
    return client()[settings().casefile_database]


def ping() -> bool:
    return client().admin.command("ping").get("ok") == 1.0
