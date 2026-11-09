"""Moteur Short Videos - modèles vidéo paramétrables, servis par l'app web.

Séparation des responsabilités :
- project.py    : modèle de projet JSON (versionné) + sauvegarde/chargement
- schema.py     : version 2 du format, modèle par défaut, conversion v1 -> v2
- resolve.py    : résolution déterministe (frames absolues, ressources, graine)
- validation.py : validation du projet (erreurs bloquantes + avertissements)
- fonts.py      : catalogue des polices sous licence (partagé avec le frontend)
- timing.py     : calculs de durée, fondu, glissement, zoom
- render.py     : composition Pillow (mesure v1 ; le rendu web vient de Remotion)
- exporter.py   : export MP4 Pillow/ffmpeg, progression, annulation, nettoyage
- probe.py      : vérification des MP4 produits (sans ffprobe)

L'interface Tkinter (main.py, run.bat, tab.py) a été retirée : l'unique point
d'entrée est start_web.bat et la source de vérité des compositions est
web/src/remotion/.
"""

__version__ = "0.1.0"
