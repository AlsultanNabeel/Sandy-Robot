from typing import Any, Optional, Tuple
import certifi

try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MongoClient = None
    MONGODB_AVAILABLE = False
    print("[Warning] PyMongo not available. To enable: pip install pymongo>=4.6.0")


def _connect_mongo(uri: str):
    """Build Mongo client with Atlas-friendly TLS defaults for cloud runtimes."""
    base_kwargs = {
        "serverSelectionTimeoutMS": 20000,
        "connectTimeoutMS": 20000,
        "socketTimeoutMS": 20000,
        "retryWrites": True,
        "maxPoolSize": 10,
        "minPoolSize": 1,
        "appname": "sandy-railway-agent",
    }

    client = MongoClient(
        uri,
        tls=True,
        tlsCAFile=certifi.where(),
        **base_kwargs,
    )
    client.admin.command("ping")
    return client


def init_mongo_connection(mongodb_uri: str, mongodb_db_name: str) -> Tuple[Optional[Any], Optional[Any]]:
    """Initialize MongoDB connection and return (mongo_client, mongo_db)."""
    if not MONGODB_AVAILABLE:
        print("[MongoDB] ⚠️ PyMongo not installed, using JSON memory for now")
        return None, None

    if not mongodb_uri:
        print("[MongoDB] ⚠️ MONGODB_URI not set, using JSON memory for now")
        return None, None

    mongo_client = None
    mongo_db = None

    try:
        mongo_client = _connect_mongo(mongodb_uri)
        mongo_db = mongo_client[mongodb_db_name]
        print(f"[MongoDB] ✅ Connected successfully (db={mongodb_db_name})")
        return mongo_client, mongo_db

    except Exception as first_error:
        print(f"[MongoDB] ⚠️ Primary TLS connection failed: {first_error}")

        try:
            mongo_client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=20000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                tls=True,
                tlsAllowInvalidCertificates=True,
                retryWrites=True,
                maxPoolSize=10,
                minPoolSize=1,
                appname="sandy-railway-agent-fallback",
            )
            mongo_client.admin.command("ping")
            mongo_db = mongo_client[mongodb_db_name]
            print(f"[MongoDB] ✅ Connected with fallback TLS mode (db={mongodb_db_name})")
            return mongo_client, mongo_db

        except Exception as second_error:
            print(f"[MongoDB] ⚠️ Connection failed: {second_error}")
            print("[MongoDB] Hint: check Atlas Network Access allowlist and URI credentials")
            print("[MongoDB] Falling back to JSON memory")
            return None, None