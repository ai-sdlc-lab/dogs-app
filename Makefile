# Local AWS commands: export AWS_PROFILE=sdlc-lab-admin (aws login). CI injects role credentials.
BUCKET := sdlc-lab-app-dogs-dev-992382408037
PY ?= $(if $(wildcard .venv/bin/python),$(CURDIR)/.venv/bin/python,python3.14)  # make venv once
TF := terraform -chdir=infra
BUILD_INFO ?= build/lambda/app/build_info.json

.PHONY: venv fmt test test-api test-process test-web lint build build-info plan apply destroy seed run-api

venv:
	python3.14 -m venv .venv
	.venv/bin/pip install -q --require-hashes -r api/requirements.txt -r api/requirements-dev.txt
	.venv/bin/pip install -q --require-hashes -r tests/process/requirements.txt

test: test-api test-process test-web

test-api:
	cd api && $(PY) -m pytest -q

# Frontend tests (change 0002): built-in node:test, no dependency; Node >= 22.18 (type stripping).
test-web:
	npm --prefix web test

# SDLC workflow tests (change 0001): hook, settings, agents, workflows, scripts. Needs .appsec-baseline/ (scripts/appsec_checkout.py).
test-process:
	$(PY) -I -B -m pytest -q -p no:cacheprovider tests/process

# Formatting the SDLC workflow runs at the code stage (it doesn't run lint: CI does, tflint isn't local).
fmt:
	cd api && ruff format . && ruff check --fix .
	terraform fmt -recursive infra

lint:
	cd api && ruff check . && ruff format --check .
	cd web && npm run typecheck
	terraform fmt -check -recursive infra
	tflint --chdir=infra

build:
	cd web && npm ci && npm run build
	rm -rf build && mkdir -p build/lambda
	$(PY) -m pip install -q --target build/lambda --platform manylinux2014_aarch64 \
		--implementation cp --python-version 3.14 --only-binary=:all: --require-hashes -r api/requirements.txt
	cp -R api/app build/lambda/app
	$(MAKE) build-info
	cp -R web/dist build/lambda/web
	cd build/lambda && find . -name '__pycache__' -prune -exec rm -rf {} + && zip -qr ../lambda.zip .

# Change 0004: the git SHA the Lambda log events carry as `version`. Needs only git.
build-info:
	mkdir -p $(dir $(BUILD_INFO))
	printf '{"sha": "%s"}\n' "$$(git rev-parse HEAD)" > $(BUILD_INFO)

plan:
	$(TF) init -input=false
	$(TF) plan -out=tfplan

apply:
	$(TF) apply tfplan
	rm -f infra/tfplan

destroy:
	$(TF) init -input=false
	$(TF) destroy

# Additive: never deletes, so later user uploads under dogs/ survive a reseed.
seed:
	aws s3 sync seed/images s3://$(BUCKET)/dogs/

run-api:
	cd api && DOGS_BUCKET=$(BUCKET) uvicorn app.main:app --port 8080
