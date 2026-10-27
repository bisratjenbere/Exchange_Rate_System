import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

workers = 2
worker_class = "sync"
worker_connections = 100
timeout = 120
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"

proc_name = "exchange-rates-api"

daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
