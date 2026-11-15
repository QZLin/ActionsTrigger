"""ActionsTrigger - trigger GitHub Actions workflows when upstream projects change."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('actions_trigger')
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = '0.0.0'

__all__ = ['__version__']
