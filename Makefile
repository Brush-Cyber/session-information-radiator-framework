.PHONY: setup run export clean

setup:
	pip install -r requirements.txt
	python setup_db.py

run:
	gunicorn --bind 0.0.0.0:5000 --reload app:app

export:
	python -m sirm.export --output ./sirm-export

clean:
	rm -rf __pycache__ sirm/__pycache__
