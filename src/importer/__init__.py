"""Data importer: loads WSDC dancer/event data into Postgres.

Ports the legacy flat-file pipeline in ``points/`` (dancer_repository.py,
event_repository.py, fetch.py) to write into the relational schema instead of
msgpack/JSON files. Run as a module::

    python -m src.importer            # weekly loop (default)
    python -m src.importer --once     # single import, then exit
"""
