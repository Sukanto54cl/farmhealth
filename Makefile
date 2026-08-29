# farmhealth — common developer tasks.
#
# Pass extra CLI flags through ARGS, e.g.
#     make run ARGS="--start 2024-04-01 --end 2024-11-01"
#     make landsat ARGS="--max-cloud 40 --yes"

ARGS ?=
UV   ?= uv
PY   := $(UV) run python

.DEFAULT_GOAL := help
.PHONY: help sync run landsat test test-cov notebook clean clean-outputs

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sync:  ## Install/refresh the locked dependency set
	$(UV) sync

run: sync  ## Run the NDVI pipeline (ARGS passes flags to main.py)
	$(PY) main.py $(ARGS)

landsat: sync  ## Download Landsat 30 m scenes for the field blocks
	$(PY) -m src.landsat $(ARGS)

test: sync  ## Run the test suite (no network, no CDSE account needed)
	$(PY) -m pytest $(ARGS)

test-cov: sync  ## Run the test suite with a coverage report
	$(PY) -m pytest --cov=src --cov-report=term-missing $(ARGS)

notebook: sync  ## Open the visualization notebook in Jupyter Lab
	$(UV) run jupyter lab notebooks/visualize.ipynb

clean:  ## Remove Python/pytest caches (keeps outputs/ and data/)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache

clean-outputs:  ## Delete everything in outputs/ (re-running the pipeline is slow)
	rm -rf outputs
