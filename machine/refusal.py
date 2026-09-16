"""The one exception a caller acts on."""


class MachineRefused(RuntimeError):
    """An event the tables do not permit from where the machines stand."""
