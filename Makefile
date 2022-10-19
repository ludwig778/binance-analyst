ARGS = $(filter-out $@,$(MAKECMDGOALS))

TEST_ARGS = -vvss --show-capture=no


default: py

sh:
	bash

py:
	poetry run ipython3 -i startup.py ${ARGS}

jupyter:
	poetry install
	PYTHONPATH=/app poetry run jupyter notebook --allow-root --ip 0.0.0.0

run_bot:
	PYTHONUNBUFFERED=1 PYTHONPATH=/app poetry run python3 analyst/bot/bot.py

update_test_cache:
	poetry run python3 update_test_cache.py

lint:
	python3 -m flake8 .

isort:
	isort .

black:
	black --line-length 106 .

mypy:
	mypy analyst

piprot:
	piprot pyproject.toml

format: isort black
sure: tests lint mypy piprot

debug:
	while :; do inotifywait -e modify -r .;clear;poetry run make ${ARGS};sleep .1 ;done

tests:
	pytest ${TEST_ARGS}

test_on:
	pytest ${TEST_ARGS} ${ARGS}

cov:
	pytest ${TEST_ARGS} --cov=analyst

cov_html:
	pytest ${TEST_ARGS} --cov=analyst --cov-report html:coverage_html

clean:
	rm -rf coverage_html .coverage .mypy_cache .pytest_cache
	find . -name "*.pyc" -o -name "__pycache__"|xargs rm -rf

.PHONY: tests
