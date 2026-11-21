import os

port = os.environ.get('PORT', '8000')
bind = f"0.0.0.0:{port}"
timeout = 120

# STRICT SINGLE-WORKER DEPLOYMENT GUARD
# TrashTrekyx assignment synchronization uses in-process serialization (assignment_sync_lock = threading.RLock()).
# To eliminate cross-process concurrency hazards across SQLite and Firebase RTDB, exactly ONE worker
# process is explicitly enforced, overriding host/Render WEB_CONCURRENCY defaults.
# Horizontal multi-instance scaling is strictly unsupported until external distributed locking is deployed.
workers = 1
threads = 4
worker_class = 'gthread'
