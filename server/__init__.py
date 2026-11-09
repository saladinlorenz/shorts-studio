"""Serveur local FastAPI de youtube_clipper.

Expose la logique métier Python existante (shortvideos/, downloader/,
processor/, podcaster/) via des routes HTTP bornées, sert le frontend
buildé (web/dist) et orchestre les tâches longues (jobs) hors des
threads de requête.

Ecouté sur 127.0.0.1 par defaut : aucune publication sur Internet.
"""

__version__ = "0.1.0"
