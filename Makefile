.PHONY: setup lint format typecheck test serve ui eval ci clean

PYTHON ?= python

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

lint:
	ruff check app tests eval

format:
	ruff format --check app tests eval

typecheck:
	mypy app

test:
	pytest tests/

serve:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

ui:
	streamlit run app/ui/streamlit_app.py

eval:
	$(PYTHON) -m eval.run_eval

ci: lint format typecheck test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +

