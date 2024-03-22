import typing as tp
from dataclasses import dataclass

if tp.TYPE_CHECKING:
    from .component import Component


@dataclass
class ComponentEvent:
    name: str
    source: 'Component'
    data: tp.Any


@dataclass
class ServiceEvent:
    name: str
    source: str
    data: tp.Any


@dataclass
class ServerEvent:
    name: str


def final(fn):
    """A decorator to mark methods as final (non-overridable)."""
    setattr(fn, 'final', True)
    return fn


def deny_final_method_override(cls, base_cls):
    # Iterate through attributes of the base class (Service in this case)
    for name, value in base_cls.__dict__.items():
        # Check if the attribute is a method marked with `final`
        if callable(value) and getattr(value, 'final', False):
            # Check if this method was overridden in the subclass
            if getattr(cls, name) != value:
                raise PermissionError(
                    f"Method {name!r} should not be overridden in subclass {cls.__name__!r}"
                )
