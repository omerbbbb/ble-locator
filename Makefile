.PHONY: setup test run build clean

setup:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -v

test-engine:
	.venv/bin/pytest tests/test_engine/ -v

test-filtering:
	.venv/bin/pytest tests/test_filtering/ -v

test-services:
	.venv/bin/pytest tests/test_services/ -v

test-core:
	.venv/bin/pytest tests/test_core/ -v

test-storage:
	.venv/bin/pytest tests/test_storage/ -v

test-net:
	.venv/bin/pytest tests/test_net/ -v

run:
	.venv/bin/python main.py

build:
	./build_app.sh

clean:
	rm -rf build dist
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Simulated distance-accuracy benchmark → docs/benchmark/SIMULATED_ACCURACY.md
bench-sim:
	.venv/bin/python -m benchmark.simulate_accuracy

# Real-room measurement (run at a known distance): make measure DEVICE=iPhone DIST=1.0
measure:
	.venv/bin/python -m benchmark.measure_real --device "$(DEVICE)" --true-distance $(DIST) --seconds 30
