#!/bin/sh
gunicorn -w 2 --threads 4 -b 0.0.0.0:5000 http_api:app 