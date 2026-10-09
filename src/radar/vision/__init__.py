"""Vision-research P0/P1 infrastructure.

This package is intentionally separate from Strategy 2.  It prepares blinded,
causal chart samples and Label Studio round-trips; it does not train models.
"""

__all__ = [
    "VisionPilotConfig",
    "build_label_studio_bundle",
    "import_label_studio_export",
    "load_config",
]

def __getattr__(name):
    # Existing API, loaded only when requested. The Label Studio HTTP extension
    # must not import DuckDB or any research/future reader at server startup.
    if name not in __all__:
        raise AttributeError(name)
    from . import labeling
    return getattr(labeling,name)
