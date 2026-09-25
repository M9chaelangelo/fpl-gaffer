"""The solver has to exist before the model is worth writing.

PuLP 4.0 removed both halves of how this project talked to it. The variable
constructor was a rename and the call sites moved. The solver was not: the CBC
that used to ship inside the wheel now has to be installed separately, and the
replacement class has nothing to fall back on when it isn't.

That is the failure worth a test. A missing solver does not raise — it returns
no answer, and the wildcard drafter then reports "no legal squad for 100.0m",
which reads exactly like a budget that doesn't work. A dependency change would
arrive disguised as a football problem.
"""
import pytest

import pulp

from gaffer import solver


@pytest.fixture(autouse=True)
def _forget_the_choice():
    """The backend is cached on purpose; these tests all change the answer."""
    solver._chosen = None
    yield
    solver._chosen = None


def test_it_finds_a_solver_here():
    assert solver.backend().__name__ in solver.BACKENDS


def test_it_prefers_the_backend_that_survives_pulp_4(monkeypatch):
    """COIN_CMD first, whenever it can actually reach a binary."""
    monkeypatch.setattr(solver, "_probe", lambda cls: True)
    assert solver.backend() is pulp.COIN_CMD


def test_it_falls_back_when_coin_cmd_has_no_binary(monkeypatch):
    """PuLP 3 without the extra: COIN_CMD is importable but finds nothing, and
    the bundled binary is the only one there is.

    `PULP_CBC_CMD` is set here rather than assumed, because under PuLP 4 it is
    gone and this test would otherwise be asserting the installed version
    instead of the fallback."""
    bundled = type("PULP_CBC_CMD", (), {})
    monkeypatch.setattr(pulp, "PULP_CBC_CMD", bundled, raising=False)
    monkeypatch.setattr(solver, "_probe",
                        lambda cls: cls is not pulp.COIN_CMD)
    assert solver.backend() is bundled


def test_a_backend_pulp_no_longer_has_is_skipped(monkeypatch):
    """PULP_CBC_CMD is gone in 4.0. `getattr` must not be an AttributeError."""
    monkeypatch.delattr(pulp, "PULP_CBC_CMD", raising=False)
    monkeypatch.setattr(solver, "_probe", lambda cls: True)
    assert solver.backend() is pulp.COIN_CMD


def test_no_solver_at_all_says_so_out_loud(monkeypatch):
    """The whole point. Not a wrong answer, not an empty squad — a sentence
    naming the install that fixes it."""
    monkeypatch.setattr(solver, "_probe", lambda cls: False)
    with pytest.raises(RuntimeError, match=r"pulp\[cbc\]"):
        solver.backend()


def test_probe_is_not_fooled_by_a_class_that_constructs(monkeypatch):
    """`COIN_CMD(msg=0)` builds happily with no cbc anywhere. Availability is
    the question, not construction."""
    class Constructs:
        def __init__(self, **kw):
            pass

        def available(self):
            return None            # what COIN_CMD really returns with no cbc

    assert solver._probe(Constructs) is False


def test_probe_survives_a_backend_that_cannot_be_built():
    class Explodes:
        def __init__(self, **kw):
            raise OSError("no solver directory")

    assert solver._probe(Explodes) is False


def test_solve_returns_the_status_name_and_the_answer():
    m = pulp.LpProblem("t", pulp.LpMaximize)
    a = m.add_variable("a", cat="Binary")
    b = m.add_variable("b", cat="Binary")
    m += 3 * a + 2 * b
    m += a + b <= 1
    assert solver.solve(m, 10) == "Optimal"
    assert a.value() == 1 and b.value() == 0


def test_the_choice_is_made_once(monkeypatch):
    """Probing shells out to look for a binary. Doing that per solve would cost
    more than some of the solves."""
    calls = []
    monkeypatch.setattr(solver, "_probe",
                        lambda cls: (calls.append(cls), True)[1])
    solver.backend()
    solver.backend()
    assert len(calls) == 1


def test_the_status_is_a_word_on_pulp_3():
    """An int and a lookup table."""
    assert solver.status_name(1) == "Optimal"
    assert solver.status_name(-1) == "Infeasible"
    assert solver.status_name(0) == "Not Solved"


def test_the_status_is_the_same_word_on_an_enum():
    """PuLP 4 dropped the table. If a status arrives as an enum and we spell it
    `OPTIMAL`, the wildcard drafter's `status == "Optimal"` quietly turns every
    good squad into an unconfirmed one."""
    import enum

    class LpStatus(enum.Enum):
        OPTIMAL = 1
        NOT_SOLVED = 0

    assert solver.status_name(LpStatus.OPTIMAL) == "Optimal"
    assert solver.status_name(LpStatus.NOT_SOLVED) == "Not Solved"


def test_an_unknown_status_is_shown_rather_than_swallowed():
    """A number nobody recognises still has to reach the error message."""
    assert solver.status_name(-99) == "-99"


def test_a_real_solve_survives_pulp_4(monkeypatch):
    """The two names 4.0 actually removed, removed — and a model solved anyway.

    This is the test that would have caught the break. Both CI failures were a
    top-level `pulp` attribute vanishing: first `LpVariable`'s `cat`, then
    `LpStatus`. Neither is reachable from a normal run on PuLP 3, so nothing
    here noticed until the runner installed the new major.
    """
    monkeypatch.delattr(pulp, "LpStatus", raising=False)
    monkeypatch.delattr(pulp, "PULP_CBC_CMD", raising=False)
    solver._chosen = None

    m = pulp.LpProblem("pulp4", pulp.LpMaximize)
    a = m.add_variable("a", cat="Binary")
    b = m.add_variable("b", lowBound=0, upBound=4, cat="Integer")
    m += 5 * a + b
    m += a + b <= 3

    assert solver.solve(m, 10) == "Optimal"
    assert a.value() == 1 and b.value() == 2
