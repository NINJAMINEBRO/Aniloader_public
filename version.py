"""The running build's version.

``BUILD`` is the number the updater compares against ``latest_version.txt`` in
the public repo, so it is a plain ``YYYYMMDD`` integer rather than a dotted
version string: newer is simply greater. Bump it whenever a release is cut,
and publish the same number to that file.

``NAME`` is the human-facing label ("0.1 Development") and carries no ordering.
"""

NAME: str = "0.5 Open Beta"
BUILD: int = 20260928


def display() -> str:
    """Version as shown in the window title, e.g. ``0.1 Development (20260819)``."""
    return f"{NAME} ({BUILD})"
