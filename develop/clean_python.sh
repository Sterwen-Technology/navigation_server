#!/bin/bash

# Vérifie qu'un répertoire est fourni en argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <répertoire>"
    exit 1
fi

# Répertoire de départ
DIR="$1"

# Vérifie que le répertoire existe
if [ ! -d "$DIR" ]; then
    echo "Erreur: Le répertoire '$DIR' n'existe pas."
    exit 1
fi

# Supprime les fichiers .pyc, .pyo, .pyd
find "$DIR" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \) -delete

# Supprime les répertoires __pycache__
find "$DIR" -type d -name "__pycache__" -exec rm -rf {} +

echo "Nettoyage terminé : fichiers compilés et répertoires __pycache__ supprimés dans '$DIR'."