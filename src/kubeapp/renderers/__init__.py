"""Rendering backends consuming the shared Application model."""

from .base import Renderer as Renderer
from .kubernetes import KubernetesRenderer as KubernetesRenderer
