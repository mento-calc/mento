from types import SimpleNamespace
import pytest
from mento.design_warnings import _MESSAGES, DesignWarning
from mento.verification import WARNING_CATEGORY, verification_status, warning_category


@pytest.mark.parametrize("code", sorted(_MESSAGES))
def test_every_published_warning_has_explicit_category(code):
    assert code in WARNING_CATEGORY
    category = warning_category(code)
    assert category in {"resistance", "failed", "pending", "informative"}
    face = SimpleNamespace(DCR=0.2)
    b = SimpleNamespace(
        flexure_checks=[SimpleNamespace(complies=True, bottom=face, top=face)],
        shear_checks=[SimpleNamespace(DCR=0.2)],
        warnings=[DesignWarning(code, "probe")],
        _compression_faces=set(),
        _stirrups_optional=True,
    )
    state = verification_status(b)
    assert state["detailing"] == (category if category in {"failed", "pending"} else "passed")
    if category == "resistance":
        assert state["resistance"] == ("pending" if code == "force_component_not_checked" else "failed")


def test_unknown_warning_does_not_silently_pass():
    assert warning_category("new_warning") == "pending"


def test_skin_review_is_informative_and_emitted_once():
    from mento.design_warnings import _Raw, collect
    from mento import mm

    raws = [
        _Raw("skin_distribution_review", {"rows": 1, "gap": 400 * mm}, face="bottom", combination="P", severity=400),
        _Raw("skin_distribution_review", {"rows": 1, "gap": 450 * mm}, face="top", combination="N", severity=450),
    ]
    warnings = collect(raws)
    assert len(warnings) == 1
    assert warnings[0].face == "top"
    assert warnings[0].combinations == ("P", "N")
    assert warning_category(warnings[0].code) == "informative"
    assert warning_category("skin_detailing_invalid") == "pending"
    assert warning_category("skin_reinforcement_required") == "failed"  # DP-2 no cambia.
