install-requirements: source
		python3 -m pip install -U -r requirements.txt

docker:
		sudo systemctl start docker

start: docker
		python3 ./build.py

lint: flake8 mypy pylint

flake8:
		flake8 *.py

pylint:
		pylint *.py

mypy:
		mypy *.py
