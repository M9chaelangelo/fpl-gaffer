"""Which CBC to hand a model to.

PuLP 3.3 deprecated both halves of how this project talked to it, and PuLP 4.0
removes them. One half is a rename: `LpVariable(name, cat=...)` becomes
`prob.add_variable(name, cat=...)`, which 3.3 already understands, so the call
sites just use the new form and this module has nothing to say about it.

The other half is not a rename, and that is why this file exists.
`PULP_CBC_CMD` ran a CBC binary that shipped inside the wheel. `COIN_CMD` runs
whatever `cbc` is on PATH and has nothing to fall back on — under PuLP 4 the
binary is a separate install (`pulp[cbc]`, which is in `requirements.txt` for
exactly this reason). Swapping one name for the other blind would trade a
TypeError for a solver that quietly finds no answer, and an unsolved model
looks precisely like an unsolvable one: the wildcard drafter raises "no legal
squad for 100.0m" either way. A crash is honest; that is not.

So ask which of them can actually reach a binary, newest first.
"""
import warnings

import pulp

# Newest first: COIN_CMD is the one that survives PuLP 4, PULP_CBC_CMD is the
# bundled binary that does not.
BACKENDS = ("COIN_CMD", "PULP_CBC_CMD")

_chosen = None


def _probe(cls):
    """Can this backend find a CBC to run? Construction alone proves nothing."""
    try:
        with warnings.catch_warnings():
            # Constructing PULP_CBC_CMD warns about its own removal. Asking a
            # question is not using it; the answer may well be that we don't.
            warnings.simplefilter("ignore", DeprecationWarning)
            return bool(cls(msg=0).available())
    except Exception:
        # A backend that cannot even be constructed is simply not available.
        return False


def backend():
    """The CBC class to use, decided once."""
    global _chosen
    if _chosen is None:
        for name in BACKENDS:
            cls = getattr(pulp, name, None)
            if cls is not None and _probe(cls):
                _chosen = cls
                break
        else:
            raise RuntimeError(
                "no CBC solver available — PuLP is installed but neither "
                "COIN_CMD nor PULP_CBC_CMD can find a binary. Install one with "
                "`pip install 'pulp[cbc]'`.")
    return _chosen


def solve(model, time_limit):
    """Solve `model` quietly under a time limit; return the status name."""
    model.solve(backend()(msg=0, timeLimit=time_limit))
    return pulp.LpStatus[model.status]
