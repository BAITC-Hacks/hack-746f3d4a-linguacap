.PHONY: install download-rukk dev test

install:
	python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt

download-rukk:
	python3 -m app.model_download

dev:
	python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	python3 -m pytest -q
