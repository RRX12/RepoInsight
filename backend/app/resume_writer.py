"""Public production writing entry and explicit evaluation-only baseline entry."""
from .resume_support import collect
from .resume_quality import generate


def write(snapshot,material,chat=None,source_reader=None):
    return generate(snapshot,material,chat,source_reader)


def write_legacy(snapshot,material,chat=None):
    # Retained for eval-resume-quality --compare-legacy; never selected by the API.
    from .resume_legacy import write_legacy as baseline
    return baseline(snapshot,material,chat)
