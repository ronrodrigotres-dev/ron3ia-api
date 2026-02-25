"""Root deployment guard.

This repository must be deployed from `./backend` in Cloud Run source deploys.
Using `--source .` is intentionally blocked to avoid mixing root/backend entrypoints.
"""

raise RuntimeError(
    "Invalid deployment source: root main.py was loaded. Deploy with `--source ./backend` "
    "so Cloud Run runs `backend/main.py` (main:app)."
)
