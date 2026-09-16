"""Catalogue implementation backed by DWD's Open Data file server.

Everything in this package is private. It knows the path structure on the
server, speaks HTTP with the server and parses the nginx directory listings.
"""

from __future__ import annotations