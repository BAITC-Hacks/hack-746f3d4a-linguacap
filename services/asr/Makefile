NEMO_VENV := .venv-nemo

.PHONY: install install-nemo install-diarization download-rukk download-nemo download-pyannote benchmark-rukk benchmark-nemo dev dev-full test

install:
	python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt

install-nemo:
	python3.12 -m venv $(NEMO_VENV)
	$(NEMO_VENV)/bin/python -m pip install -r requirements.txt -r requirements-nemo.txt

install-diarization:
	$(NEMO_VENV)/bin/python -m pip install -r requirements-diarization.txt

download-rukk:
	python3 -m app.model_download

download-nemo:
	$(NEMO_VENV)/bin/python -m app.model_download nemo

download-pyannote:
	$(NEMO_VENV)/bin/python -m app.model_download pyannote

benchmark-rukk:
	python3 -m app.benchmark rukk $(RECORDING)

benchmark-nemo:
	$(NEMO_VENV)/bin/python -m app.benchmark nemo $(RECORDING)

dev:
	python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev-full:
	$(NEMO_VENV)/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	python3 -m pytest -q
