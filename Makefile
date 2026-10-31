SHELL := /bin/bash

.PHONY: setup manifest test lint gandalf-build gandalf-start gandalf-stop \
	neo4j-export neo4j-import neo4j-start neo4j-stop neo4j-index \
	rule-features target-inventory evaluate-rules validate status \
	benchmark-prepare benchmark-build benchmark-start

setup:
	uv sync --all-groups
	mkdir -p data/evaluations data/gandalf data/neo4j/import data/neo4j/data \
		data/rule-set-evaluations data/tmp logs .run manifest results/rule-sets
	test -f .env || cp .env.example .env
	./scripts/fetch_biolink.sh

manifest:
	./scripts/build_manifest.sh

test:
	uv run pytest -q

lint:
	uv run ruff check .

gandalf-build:
	./scripts/build_gandalf.sh

gandalf-start:
	./scripts/start_gandalf.sh

gandalf-stop:
	./scripts/stop_gandalf.sh

neo4j-export:
	./scripts/export_neo4j.sh

neo4j-import:
	./scripts/import_neo4j.sh

neo4j-start:
	docker compose up -d neo4j

neo4j-stop:
	docker compose stop neo4j

neo4j-index:
	./scripts/index_neo4j.sh

rule-features:
	uv run miner-build-rule-features

target-inventory:
	uv run miner-target-inventory

evaluate-rules:
	uv run miner-evaluate-rules

validate:
	./scripts/validate.sh

status:
	./scripts/status.sh

benchmark-prepare:
	uv run miner-benchmark-setup prepare

benchmark-build:
	uv run miner-benchmark-setup build-stores

benchmark-start:
	uv run miner-benchmark-setup start
