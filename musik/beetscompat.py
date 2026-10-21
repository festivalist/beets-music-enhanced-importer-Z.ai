# -*- coding: utf-8 -*-
"""beets-Versionsbrücken — musik läuft auf beets 2.13.x (Windows-Dev)
und 2.14.x (Pi). Erstere bricht an Schnittstellen, die 2.14 umgestellt
hat (Story 9.11: tag_album). Hier lebt der versionstolerante Zugriff,
damit Call-Sites nicht selbst auf Versionen prüfen müssen."""


def tag_album_compat(items, search_artist=None, search_name=None,
                     search_ids=None):
    """autotag.tag_album über die API-Brüche hinweg; Rückgabe immer die
    Proposal (Kandidaten + Recommendation).

    beets 2.13: tag_album(Item-Liste) → (artist, album, Proposal)
    beets 2.14: tag_album(Source) → Proposal; Source baut man via
    Source.from_items(items) (trägt die häufigsten Tags der Items und
    steuert Suche/VA-Erkennung wie bisher über die Keyword-Args)."""
    from beets.autotag import tag_album

    kwargs = {
        "search_artist": search_artist,
        "search_name": search_name,
        "search_ids": list(search_ids or []),
    }
    try:
        from beets.autotag.source import Source
    except ImportError:  # beets 2.13
        _artist, _album, proposal = tag_album(list(items), **kwargs)
        return proposal
    return tag_album(Source.from_items(list(items)), **kwargs)
