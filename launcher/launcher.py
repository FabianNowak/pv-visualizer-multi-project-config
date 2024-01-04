#!/opt/pv-launcher/venv/bin/python
import os

from wslink import launcher

os.environ["PYTHONUNBUFFERED"] = "1"
launcher.start()