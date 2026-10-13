# Gunicorn configuration for production deployment

import multiprocessing
import os

# Bind to PORT provided by hosting platform (Render, Railway, etc.)
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Worker configuration
# Free tier has limited resources, so keep worker count low
workers = 2
worker_class = "sync"
worker_connections = 100
timeout = 120  # 2 minutes (bank fetches can be slow)
keepalive = 5

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"

# Process naming
proc_name = "exchange-rates-api"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
