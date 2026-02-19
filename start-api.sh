#!/bin/bash

exec /root/DevApps/Wandikweza/indicator_api_v2.0/venv/bin/gunicorn \
    'app:create_app()' \
    --bind 0.0.0.0:5001 \
    --workers 4 \
    --worker-class sync \
    --timeout 180 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /var/log/wandikweza/gunicorn.access.log \
    --error-logfile /var/log/wandikweza/gunicorn.error.log \
    --log-level info
