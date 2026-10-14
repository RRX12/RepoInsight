"""Single public production writing entry."""
from .resume_support import collect
from .resume_quality import generate


def write(snapshot,material,chat=None,source_reader=None):
    return generate(snapshot,material,chat,source_reader)
