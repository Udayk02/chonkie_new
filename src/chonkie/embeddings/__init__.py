"""Embeddings classes for text embedding."""

from .auto import AutoEmbeddings
from .base import BaseEmbeddings
from .cohere import CohereEmbeddings
from .model2vec import Model2VecEmbeddings
from .openai import OpenAIEmbeddings
from .sentence_transformer import SentenceTransformerEmbeddings
from .ollama import OllamaEmbeddings

# Add all embeddings classes to __all__
__all__ = [
    "BaseEmbeddings",
    "Model2VecEmbeddings",
    "SentenceTransformerEmbeddings",
    "OpenAIEmbeddings",
    "CohereEmbeddings",
    "OllamaEmbeddings",
    "AutoEmbeddings",
]
