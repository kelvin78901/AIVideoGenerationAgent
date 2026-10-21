"""Worker scripts for local models (``modelhub/adapters/local_python.py``).

Each runs as a standalone script in the model's own environment (``~/.drama-studio/envs/<env>``),
not imported by the app: they need libraries the app does not have, so mypy skips this folder.
"""
