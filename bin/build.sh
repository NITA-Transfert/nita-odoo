#!/usr/bin/env bash
# Construit payment_nita-17.0.zip : le module Odoo `payment_nita/` seul,
# élagué de tout ce qui n'a rien à faire dans une install Odoo (tests/,
# e2e/, .git, .superpowers, caches Python) — installable tel quel via
# Apps > Mettre à jour la liste des Apps (apps/extra-addons).
#
# Usage : bash bin/build.sh   (depuis n'importe quel répertoire)
set -euo pipefail

# --- Chemins : toujours relatifs à l'emplacement du script, jamais au cwd ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODULE_DIR="$REPO_ROOT/payment_nita"
ZIP_NAME="payment_nita-17.0.zip"
ZIP_PATH="$REPO_ROOT/$ZIP_NAME"

if [ ! -d "$MODULE_DIR" ]; then
  echo "Erreur : $MODULE_DIR introuvable (le script doit vivre dans bin/ à la racine du repo nita-odoo)." >&2
  exit 1
fi

# --- Dossier de travail jetable : on copie payment_nita/ puis on élague ---
WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

cp -R "$MODULE_DIR" "$WORKDIR/payment_nita"

# Élagage (défense en profondeur : ces noms ne vivent normalement pas sous
# payment_nita/, sauf __pycache__ qui s'y génère réellement à chaque run
# pytest/import) :
find "$WORKDIR/payment_nita" -depth -type d \( \
    -name '__pycache__' -o \
    -name '.pytest_cache' -o \
    -name 'tests' -o \
    -name 'e2e' -o \
    -name '.superpowers' -o \
    -name '.git' -o \
    -name '.venv' \
  \) -exec rm -rf {} +
find "$WORKDIR/payment_nita" -type f -name '*.pyc' -delete

rm -f "$ZIP_PATH"

# --- Archive : `zip` si présent (Linux/macOS/CI habituels), sinon repli
#     Python (zipfile), pour rester robuste sur un poste Windows/Git Bash
#     sans l'utilitaire `zip`. Les deux produisent un zip avec `payment_nita/`
#     comme unique dossier racine (ce qu'Odoo attend). ---
if command -v zip >/dev/null 2>&1; then
  ( cd "$WORKDIR" && zip -r -q "$ZIP_PATH" payment_nita )
else
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
  if [ -z "$PYTHON_BIN" ]; then
    echo "Erreur : ni 'zip' ni 'python'/'python3' disponibles pour créer l'archive." >&2
    exit 1
  fi
  "$PYTHON_BIN" - "$WORKDIR" "$ZIP_PATH" <<'PYEOF'
import os
import sys
import zipfile

workdir, zip_path = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(workdir):
        for name in sorted(files):
            full = os.path.join(root, name)
            arcname = os.path.relpath(full, workdir)
            zf.write(full, arcname)
PYEOF
fi

echo "OK : $ZIP_PATH"
