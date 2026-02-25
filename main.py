"""Root deployment guard.

Cloud Run source deploys for this repository must use `--source ./backend` (or `--source .\\backend` on Windows).
Using `--source .` is intentionally blocked to avoid mixed root/backend entrypoints.
"""

raise RuntimeError(
    "Invalid deployment source: root main.py was loaded. Deploy with `--source ./backend` "
    "(Windows: `--source .\\backend`) so Cloud Run runs backend/main.py (main:app)."
)
