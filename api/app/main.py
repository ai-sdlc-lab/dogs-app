import os
import re
from functools import cache
from pathlib import Path

import boto3
from botocore.config import Config
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

PREFIX = "dogs/"  # images live at s3://$DOGS_BUCKET/dogs/<breed>/<file>
BREED = re.compile(r"^[a-z0-9-]{1,40}$")
URL_TTL = 900  # presigned image URLs expire after 15 minutes; the bucket stays private

app = FastAPI(title="dogs-app", docs_url=None, redoc_url=None, openapi_url=None)


@cache
def s3():
    # Regional endpoint: presigned URLs on the global s3.amazonaws.com host get a
    # TemporaryRedirect for new buckets, which browsers' <img> requests don't survive.
    region = os.environ.get("AWS_REGION", "eu-north-1")
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def list_dogs(breed: str | None = None) -> list[dict]:
    bucket = os.environ["DOGS_BUCKET"]
    prefix = PREFIX + (f"{breed}/" if breed else "")
    dogs = []
    for page in s3().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            parts = obj["Key"].removeprefix(PREFIX).split("/")
            if len(parts) != 2 or not BREED.match(parts[0]) or not parts[1]:
                continue
            url = s3().generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": obj["Key"]}, ExpiresIn=URL_TTL
            )
            dogs.append({"breed": parts[0], "url": url})
    return dogs


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dogs")
def dogs():
    return list_dogs()


@app.get("/api/dogs/{breed}")
def dogs_by_breed(breed: str):
    if not BREED.match(breed):
        raise HTTPException(status_code=404, detail="unknown breed")
    found = list_dogs(breed)
    if not found:
        raise HTTPException(status_code=404, detail="unknown breed")
    return found


# The built web app (web/dist) is bundled next to the code in Lambda; absent in tests and the k8s image.
web = Path(os.environ.get("WEB_DIR", Path(__file__).parent.parent / "web"))
if web.is_dir():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")

handler = Mangum(app, lifespan="off")
