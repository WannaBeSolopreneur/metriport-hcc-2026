PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
PATIENTS ?= 3000
REPEATS ?= 3

.PHONY: all install crosswalk compare bench demo lint test clean

all: install crosswalk compare bench demo lint test

$(PY):
	$(PYTHON) -m venv $(VENV)

install: $(PY)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e '.[dev]'

crosswalk:
	$(PY) -m crosswalk.build

compare:
	$(PY) -m compare.run

bench:
	$(PY) -m fhir_loader.benchmark --patients $(PATIENTS) --repeats $(REPEATS)

demo:
	$(PY) -m fhir_loader.demo

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

test:
	$(VENV)/bin/pytest -q

clean:
	rm -rf .cache .pytest_cache .ruff_cache
