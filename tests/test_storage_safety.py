import re

import numpy as np

from neuroback.safety import SCREENING_QUESTIONS, Screening
from neuroback.storage import Store


def test_participants_are_pseudonymous_and_erasable(tmp_path):
    store = Store(tmp_path)
    pid = store.add_participant("20-29", screening_passed=True, consent=True)
    assert re.fullmatch(r"P-[0-9A-F]{6}", pid)
    sid = store.save_session(pid, np.zeros(250), 250.0, [{"t": 0.1, "event": "flash"}], 10.1, {"k": 1})
    assert store.sessions(pid)[0][0] == sid
    store.delete_participant(pid)
    assert store.participants() == [] and not (tmp_path / pid).exists()


def test_hostile_strings_cannot_touch_schema(tmp_path):
    store = Store(tmp_path)
    store.add_participant("x'); DROP TABLE participants; --", screening_passed=False, consent=False)
    assert len(store.participants()) == 1


def test_stimulation_requires_screening_and_consent(tmp_path):
    store = Store(tmp_path)
    ok = store.add_participant(None, screening_passed=True, consent=True)
    no_consent = store.add_participant(None, screening_passed=True, consent=False)
    failed = store.add_participant(None, screening_passed=False, consent=True)
    assert store.can_stimulate(ok) and not store.can_stimulate(no_consent) and not store.can_stimulate(failed)


def test_any_yes_answer_fails_screening():
    n = len(SCREENING_QUESTIONS)
    assert Screening((False,) * n, consent=True).passed
    assert not Screening((False,) * (n - 1) + (True,), consent=True).passed
    assert not Screening((False,) * n, consent=False).passed
