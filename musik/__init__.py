"""musik — automated MusicBrainz tagging for a large personal music library.

The `paths` module must be imported (and `bootstrap()` run) before beets is
imported anywhere, so the package `__init__` does it unconditionally.
"""

from . import paths as _paths

_paths.bootstrap()

__version__ = "0.1.0"
