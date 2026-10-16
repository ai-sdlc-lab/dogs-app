import pytest
from fastapi.testclient import TestClient

from app import main

KEYS = [
    "dogs/beagle/1.jpg",
    "dogs/beagle/2.jpg",
    "dogs/pug/1.jpg",
    "dogs/README",
    "dogs/Bad_Breed/x.jpg",
    "dogs/pug/",
]


class FakeS3:
    def get_paginator(self, _):
        return self

    def paginate(self, Bucket, Prefix):
        assert Bucket == "test-bucket"
        return [{"Contents": [{"Key": k} for k in KEYS if k.startswith(Prefix)]}]

    def generate_presigned_url(self, op, Params, ExpiresIn):
        assert op == "get_object" and ExpiresIn == main.URL_TTL
        return f"https://signed.example/{Params['Key']}"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOGS_BUCKET", "test-bucket")
    monkeypatch.setattr(main, "s3", FakeS3)
    return TestClient(main.app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_lists_only_well_formed_keys(client):
    assert client.get("/api/dogs").json() == [
        {"breed": "beagle", "url": "https://signed.example/dogs/beagle/1.jpg"},
        {"breed": "beagle", "url": "https://signed.example/dogs/beagle/2.jpg"},
        {"breed": "pug", "url": "https://signed.example/dogs/pug/1.jpg"},
    ]


def test_by_breed(client):
    assert [d["breed"] for d in client.get("/api/dogs/pug").json()] == ["pug"]


@pytest.mark.parametrize("breed", ["husky", "Bad_Breed", "..", "a" * 41])
def test_unknown_or_invalid_breed_is_404(client, breed):
    assert client.get(f"/api/dogs/{breed}").status_code == 404


def test_no_api_docs_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
