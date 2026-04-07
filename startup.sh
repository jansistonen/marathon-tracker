#!/bin/sh
set -e

exec gunicorn --bind=0.0.0.0:8000 app:app
