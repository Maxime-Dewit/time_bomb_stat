PYTHON ?= .venv/bin/python
MANAGE  = $(PYTHON) manage.py

.PHONY: help install migrate run demo reset-demo test lint format check

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: .venv/bin/python ## Installe les dépendances de dev (crée le virtualenv si besoin)
	.venv/bin/pip install -r requirements-dev.txt
	@test -f .env || cp .env.example .env

.venv/bin/python:
	python3 -m venv .venv

migrate: ## Applique les migrations
	$(MANAGE) migrate

run: ## Lance le serveur de dev sur http://127.0.0.1:8000
	$(MANAGE) runserver

demo: migrate ## Génère des parties simulées (ajoute aux données existantes)
	$(MANAGE) simulate_games

reset-demo: migrate ## Vide la base et régénère des parties simulées
	$(MANAGE) simulate_games --reset --no-input

test: ## Lance les tests
	$(MANAGE) test game

lint: ## Vérifie le style (ruff)
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Formate le code (ruff)
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

check: lint test ## Lint + tests + checks Django
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run
