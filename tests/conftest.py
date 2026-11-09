import sys
from pathlib import Path

# Rend le package shortvideos importable quand pytest est lance
# depuis n'importe quel repertoire.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
