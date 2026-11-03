"""API behaviour tests: listing, breed lookup and rejected input."""

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


def test_unknown_valid_breed_stays_404(client):
    r = client.get("/api/dogs/husky")
    assert (r.status_code, r.json()) == (404, {"detail": "unknown breed"})


def test_listing_skips_key_with_trailing_newline(client, monkeypatch):
    class NewlineS3(FakeS3):
        def paginate(self, Bucket, Prefix):
            return [{"Contents": [{"Key": k} for k in ("dogs/pug\n/1.jpg", "dogs/pug/2.jpg")]}]

    monkeypatch.setattr(main, "s3", NewlineS3)
    only = [{"breed": "pug", "url": "https://signed.example/dogs/pug/2.jpg"}]
    assert client.get("/api/dogs").json() == only
    assert main.list_dogs("pug") == only


def test_presigned_urls_use_regional_endpoint(monkeypatch):
    for k, v in {"AWS_REGION": "eu-north-1", "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y"}.items():
        monkeypatch.setenv(k, v)
    url = main.s3.__wrapped__().generate_presigned_url(
        "get_object",
        Params={"Bucket": "sdlc-lab-app-dogs-dev-992382408037", "Key": "dogs/pug/1.jpg"},
        ExpiresIn=60,
    )
    assert url.startswith(
        "https://sdlc-lab-app-dogs-dev-992382408037.s3.eu-north-1.amazonaws.com/dogs/pug/1.jpg?"
    )


def test_no_api_docs_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
