import pytest
from mento import Concrete_EN_1992_2004, Footing, Forces, SteelBar, MPa, cm, kN
from mento.i18n import get_language, set_language
from mento.verification import validate_supported_forces


@pytest.mark.parametrize("language", ["es", "en"])
def test_en_footing_rejection_does_not_advise_removing_axial_force(language):
    b = Footing(
        label="F",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="500", f_y=500 * MPa),
        width=100 * cm,
        height=40 * cm,
        c_c=5 * cm,
    )
    previous = get_language()
    try:
        set_language(language)
        with pytest.raises(NotImplementedError) as error:
            validate_supported_forces(b, [Forces(N_x=-10 * kN)])
        message = str(error.value)
        assert "Ingrese axil nulo" not in message and "Supply zero" not in message
        assert ("tracción" if language == "es" else "tension") in message
        assert ("compresión" if language == "es" else "compression") in message
    finally:
        set_language(previous)
