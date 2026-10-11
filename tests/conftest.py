import os, sys, tempfile, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp(prefix="colstorso-test-")
os.environ["COLSTORSO_DB"] = os.path.join(_tmp, "test.db")
os.environ.setdefault("COLSTORSO_RATE_LIMIT", "100000")
os.environ.setdefault("COLSTORSO_WRITE_RATE_LIMIT", "100000")

@pytest.fixture(scope="session")
def seeded():
    from colstorso import db, seed
    seed.build(path=os.environ["COLSTORSO_DB"], quiet=True)
    return db

@pytest.fixture()
def c(seeded):
    return seeded.get()

@pytest.fixture(scope="session")
def client(seeded):
    from fastapi.testclient import TestClient
    from colstorso.main import app
    return TestClient(app)

def H(uid): return {"X-User": str(uid)}
