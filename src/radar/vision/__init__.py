"""Vision-research P0/P1 infrastructure.

This package is intentionally separate from Strategy 2.  It prepares blinded,
causal chart samples and Label Studio round-trips; it does not train models.
"""

from .labeling import (
    VisionPilotConfig,
    build_label_studio_bundle,
    import_label_studio_export,
    load_config,
)

__all__ = [
    "VisionPilotConfig",
    "build_label_studio_bundle",
    "import_label_studio_export",
    "load_config",
]
