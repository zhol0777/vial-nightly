venv:
	uv venv

activate:
	echo source .venv/bin/activate

install-requirements:
	uv pip install -r dependencies.txt

docker:
	sudo systemctl start docker

build-image:
	docker build -t vial-nightly .

start: docker build-image
	python3 ./build.py

lint: ruff mypy

ruff:
	python3 -m ruff check *.py --config ruff.toml

mypy:
	python3 -m mypy *.py --check-untyped-defs
