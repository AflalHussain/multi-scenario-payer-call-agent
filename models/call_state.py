from enum import Enum, auto


class CallState(Enum):
    """
    Explicit state machine states for a payer call.
    The agent transitions through these in order; any failure
    drops to BLOCKED rather than inventing a result.
    """
    INITIALIZING    = auto()  # loading scenario config
    DIALING         = auto()  # attempting to reach payer
    NAVIGATING_IVR  = auto()  # pressing DTMF digits through menu tree
    WAITING_FOR_REP = auto()  # on hold
    ASKING          = auto()  # active Q&A with the representative
    EXTRACTING      = auto()  # turning transcript into structured data
    COMPLETE        = auto()  # clean result produced
    BLOCKED         = auto()  # needs-human; must never be skipped to COMPLETE
