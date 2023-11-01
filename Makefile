install-requirements: source
		python3 -m pip install -U -r requirements.txt

docker:
		sudo systemctl start docker

docker-image: docker
		sudo docker build -t vial_nightly .

start: docker
		python3 ./build.py

lint: flake8 pylint mypy

flake8:
		python3 -m flake8 *.py

pylint:
		python3 -m pylint *.py

mypy:
		python3 -m mypy *.py
