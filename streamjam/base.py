import typing as tp
from dataclasses import dataclass, field

if tp.TYPE_CHECKING:
    from .component import Component


@dataclass
class ComponentEvent:
    name: str
    source: 'Component'
    data: tp.Any


@dataclass(order=True)
class ServiceEvent:
    name: str = field(compare=False)
    source: str = field(compare=False)
    data: tp.Any = field(compare=False)
    priority: int = 1


@dataclass
class ServerEvent:
    name: str


def final(fn):
    """A decorator to mark methods as final (non-overridable)."""
    setattr(fn, 'final', True)
    return fn


def deny_final_method_override(cls, base_cls):
    # Iterate through attributes of the base class (Service in this case)
    """
    Raises PermissionError if any methods marked with the `final` decorator in
    the base class were overridden in the subclass.

    This is a utility function to be called in the `__init_subclass__` method of
    a base class (like Service) to ensure that certain methods are never
    overridden in subclasses.

    :param cls: The subclass that is being checked.
    :param base_cls: The base class that contains the `final` methods.
    """
    for name, value in base_cls.__dict__.items():
        # Check if the attribute is a method marked with `final`
        if callable(value) and getattr(value, 'final', False):
            # Check if this method was overridden in the subclass
            if getattr(cls, name) != value:
                raise PermissionError(
                    f"Method {name!r} should not be overridden in subclass {cls.__name__!r}"
                )
