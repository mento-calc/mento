from types import SimpleNamespace
import pytest
from mento.design_warnings import _MESSAGES, DesignWarning
from mento.verification import WARNING_CATEGORY, verification_status, warning_category


@pytest.mark.parametrize(
    "code",
    sorted(
        set(_MESSAGES)
        | {"stirrup_spacing_exceeds_max", "mesh_ratio_below_min", "mesh_spacing_exceeds_max", "axial_load_beyond_beam"}
    ),
)
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
        assert state["resistance"] == (
            "pending" if code in {"force_component_not_checked", "axial_load_beyond_beam"} else "failed"
        )


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
    assert warnings[0].face is None
    assert "worst of 2 service cases" in warnings[0].message
    assert "top" not in warnings[0].message and "bottom" not in warnings[0].message
    assert warnings[0].combinations == ("P", "N")
    assert warning_category(warnings[0].code) == "informative"
    assert warning_category("skin_detailing_invalid") == "pending"
    assert warning_category("skin_reinforcement_required") == "informative"
    assert warning_category("skin_en_required") == "informative"


@pytest.mark.parametrize(
    "language, expected", [("en", "worst of 1 service case:"), ("es", "peor de 1 caso de servicio:")]
)
def test_single_skin_review_uses_singular_and_keeps_global_scope(language, expected):
    from mento import mm, set_language
    from mento.design_warnings import _Raw, collect

    try:
        set_language(language)
        warnings = collect(
            [_Raw("skin_distribution_review", {"rows": 1, "gap": 400 * mm}, face="bottom", combination="S")]
        )
        assert len(warnings) == 1
        assert expected in warnings[0].message
        assert warnings[0].face is None
        assert warnings[0].combinations == ("S",)
    finally:
        set_language("en")
