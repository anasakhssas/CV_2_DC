"""Utilitaires communs."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Nettoie le texte extrait d'un PDF."""
    # Supprimer caractères de contrôle
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Normaliser les espaces multiples
    text = re.sub(r"[ \t]+", " ", text)
    # Normaliser les sauts de ligne multiples
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str, max_length: int = 200) -> str:
    """Tronque un texte avec ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
