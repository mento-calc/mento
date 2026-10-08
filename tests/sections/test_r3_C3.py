from types import SimpleNamespace
import pytest
from mento.design_warnings import _MESSAGES, DesignWarning
from mento.verification import WARNING_CATEGORY, verification_status, warning_category


@pytest.mark.parametrize(
    "code",
    sorted(
        set(_MESSAGES)
        | {
            "stirrup_spacing_exceeds_max",
            "mesh_ratio_below_min",
            "mesh_ratio_above_max",
            "mesh_spacing_exceeds_max",
            "axial_load_beyond_beam",
        }
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
