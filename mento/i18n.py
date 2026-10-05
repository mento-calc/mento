"""Language of the detailed report output.

``flexure_results_detailed``, ``shear_results_detailed`` and their ``_doc``
counterparts print English by default. Switch the whole package once and every
later report comes out translated::

    import mento

    mento.set_language("es")
    node.shear_results_detailed()        # console tables in Spanish
    node.shear_results_detailed_doc()    # Word document in Spanish

The English text a report builder produces *is* the catalog key, so the design
code modules in ``mento/codes`` stay untouched and monolingual. A catalog only
has to carry the strings that differ; anything missing falls back to English
instead of raising, so a new label always renders, translated or not.

Adding a language is data, not code: write a ``{english: translation}`` mapping
and register it in ``_CATALOGS``.

Scope: report text only. Variable names (``fc``, ``Av``, ``DCR``), units,
numbers, the design code designation and generated file names stay as they are.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

if TYPE_CHECKING:
    import pandas as pd

DEFAULT_LANGUAGE = "en"

# --------------------------------------------------------------------------
# Spanish catalog
# --------------------------------------------------------------------------
# Terminology follows CIRSOC 201 usage: "hormigón", "estribo", "cuantía",
# "solicitaciones", "recubrimiento", "altura útil".

ES: Dict[str, str] = {
    # -- console section titles --------------------------------------------
    "===== BEAM FLEXURE DETAILED RESULTS =====": "===== RESULTADOS DETALLADOS DE FLEXIÓN DE VIGA =====",
    "===== BEAM SHEAR DETAILED RESULTS =====": "===== RESULTADOS DETALLADOS DE CORTE DE VIGA =====",
    "===== SLAB FLEXURE DETAILED RESULTS =====": "===== RESULTADOS DETALLADOS DE FLEXIÓN DE LOSA =====",
    "===== SLAB SHEAR DETAILED RESULTS =====": "===== RESULTADOS DETALLADOS DE CORTE DE LOSA =====",
    "===== SHEAR WALL DETAILED RESULTS =====": "===== RESULTADOS DETALLADOS DE TABIQUE =====",
    "MATERIALS": "MATERIALES",
    "GEOMETRY": "GEOMETRÍA",
    "FORCES": "SOLICITACIONES",
    "MAX AND MIN LIMIT CHECKS": "VERIFICACIONES DE LÍMITES MÁXIMOS Y MÍNIMOS",
    "SHEAR STRENGTH": "RESISTENCIA AL CORTE",
    "CONCRETE STRENGTH": "RESISTENCIA DEL HORMIGÓN",
    "FLEXURAL CAPACITY - TOP": "CAPACIDAD A FLEXIÓN - SUPERIOR",
    "FLEXURAL CAPACITY - BOTTOM": "CAPACIDAD A FLEXIÓN - INFERIOR",
    # -- table column headers ----------------------------------------------
    "Materials": "Materiales",
    "Geometry": "Geometría",
    "Design forces": "Solicitaciones",
    "Variable": "Variable",
    "Value": "Valor",
    "Unit": "Unidad",
    "Check": "Verificación",
    "Min.": "Mín.",
    "Max.": "Máx.",
    "Ok?": "¿Ok?",
    "Shear reinforcement strength": "Resistencia de la armadura de corte",
    "Shear strength": "Resistencia al corte",
    "Top reinforcement check": "Verificación de la armadura superior",
    "Bottom reinforcement check": "Verificación de la armadura inferior",
    # -- Word document headings --------------------------------------------
    "Concrete beam flexure check": "Verificación a flexión de viga de hormigón",
    "Concrete beam shear check": "Verificación a corte de viga de hormigón",
    "Concrete slab flexure check": "Verificación a flexión de losa de hormigón",
    "Concrete slab shear check": "Verificación a corte de losa de hormigón",
    "Concrete shear wall check": "Verificación de tabique de hormigón",
    "Beam {label} flexure check": "Verificación a flexión de viga {label}",
    "Beam {label} shear check": "Verificación a corte de viga {label}",
    "Slab {label} flexure check": "Verificación a flexión de losa {label}",
    "Slab {label} shear check": "Verificación a corte de losa {label}",
    "Shear Wall {label} shear check": "Verificación a corte de tabique {label}",
    "Made with mento {version}. Design code: {design_code}": (
        "Generado con mento {version}. Código de diseño: {design_code}"
    ),
    "Limit checks": "Verificaciones de límites",
    "Strength Checks": "Verificaciones de resistencia",
    "Section Data": "Datos de la sección",
    "Flexural Capacity Top": "Capacidad a flexión superior",
    "Flexural Capacity Bottom": "Capacidad a flexión inferior",
    # -- row labels: materials and geometry --------------------------------
    "Section Label": "Identificación de la sección",
    "Concrete strength": "Resistencia del hormigón",
    "Steel reinforcement yield strength": "Tensión de fluencia del acero",
    "Concrete density": "Densidad del hormigón",
    "Normalweight concrete": "Hormigón de densidad normal",
    "Safety factor for shear": "Coeficiente de seguridad para corte",
    "Safety factor for concrete": "Coeficiente de seguridad del hormigón",
    "Safety factor for steel": "Coeficiente de seguridad del acero",
    "Section height": "Altura de la sección",
    "Section width": "Ancho de la sección",
    "Clear cover": "Recubrimiento geométrico",
    "Mechanical top cover": "Recubrimiento mecánico superior",
    "Mechanical bottom cover": "Recubrimiento mecánico inferior",
    "Longitudinal tension rebar": "Armadura longitudinal traccionada",
    "Effective height": "Altura útil",
    # -- row labels: forces -------------------------------------------------
    "Axial, positive for compression": "Axil, positivo en compresión",
    "Shear": "Corte",
    "Top max moment": "Momento máximo superior",
    "Bottom max moment": "Momento máximo inferior",
    # -- row labels: limit checks ------------------------------------------
    "Stirrup spacing along length": "Separación de estribos en la dirección longitudinal",
    "Stirrup spacing along width": "Separación de estribos en la dirección transversal",
    "Minimum shear reinforcement": "Armadura mínima de corte",
    "Minimum rebar diameter": "Diámetro mínimo de barra",
    "Min/Max As rebar top": "As mín/máx de la armadura superior",
    "Min/Max As rebar bottom": "As mín/máx de la armadura inferior",
    "Minimum spacing top": "Separación mínima superior",
    "Minimum spacing bottom": "Separación mínima inferior",
    # -- row labels: shear reinforcement -----------------------------------
    "Number of stirrups": "Número de estribos",
    "Stirrup diameter": "Diámetro del estribo",
    "Stirrup spacing": "Separación de estribos",
    "Minimum shear reinforcing": "Armadura mínima de corte",
    "Required shear reinforcing": "Armadura de corte requerida",
    "Defined shear reinforcing": "Armadura de corte adoptada",
    "Shear rebar strength": "Resistencia de la armadura de corte",
    "Steel shear strength": "Resistencia al corte del acero",
    "Concrete shear strength": "Resistencia al corte del hormigón",
    # -- row labels: shear capacity ----------------------------------------
    "Effective shear area": "Área efectiva de corte",
    "Gross shear area": "Área bruta de corte",
    "Longitudinal reinforcement ratio": "Cuantía de armadura longitudinal",
    "Size modification factor": "Factor de modificación por tamaño",
    "Axial stress": "Tensión axial",
    "Concrete effective shear stress": "Tensión de corte efectiva del hormigón",
    "Maximum shear strength": "Resistencia máxima al corte",
    "Maximum shear capacity": "Capacidad máxima de corte",
    "Total shear strength": "Resistencia total al corte",
    "Total shear capacity": "Capacidad total de corte",
    "Max shear check": "Verificación de corte máximo",
    "Demand Capacity Ratio": "Factor de Utilización",
    "Concrete strut angle": "Ángulo de la biela de hormigón",
    "k value": "Valor de k",
    "Coefficient for long term effects and loading effects": (
        "Coeficiente de efectos de larga duración y de aplicación de la carga"
    ),
    # -- row labels: flexural capacity -------------------------------------
    "First layer bars": "Barras de la primera capa",
    "Second layer bars": "Barras de la segunda capa",
    "Minimum rebar reinforcing": "Armadura mínima",
    "Required rebar reinforcing top": "Armadura superior requerida",
    "Required rebar reinforcing bottom": "Armadura inferior requerida",
    "Defined rebar reinforcing top": "Armadura superior adoptada",
    "Defined rebar reinforcing bottom": "Armadura inferior adoptada",
    "Depth of equivalent strength block ratio": "Relación de profundidad del bloque equivalente",
    "Total flexural strength": "Resistencia total a flexión",
    # -- row labels: shear wall --------------------------------------------
    "Wall thickness": "Espesor del tabique",
    "Wall length": "Longitud del tabique",
    "Wall height": "Altura del tabique",
    "Aspect ratio": "Relación de aspecto",
    "Horizontal bar spacing (E.F.)": "Separación de barras horizontales (en cada cara)",
    "Vertical bar spacing (E.F.)": "Separación de barras verticales (en cada cara)",
    "Horizontal reinforcement ratio": "Cuantía de armadura horizontal",
    "Minimum vertical reinf. ratio": "Cuantía vertical mínima",
    # -- summary tables: headers and cell values ---------------------------
    # Only the columns that hold words. The symbol columns (b, h, As,bot, Av,
    # Mu, DCRv) are variable names and stay as they are, like everywhere else.
    "Beam": "Viga",
    "Slab": "Losa",
    "Label": "Etiqueta",
    "Level": "Nivel",
    "Position": "Posición",
    "Top": "Superior",
    "Bottom": "Inferior",
    "Status": "Estado",
    # -- summary Word reports ----------------------------------------------
    "Beam Summary Analysis": "Análisis del resumen de vigas",
    "Shear Wall Summary Analysis": "Análisis del resumen de tabiques",
    "This report presents the detailed results for the first beam of the summary, followed by summary tables for all beams.": "Este informe presenta los resultados detallados de la primera viga del resumen, seguidos de las tablas resumen de todas las vigas.",
    "Wall {storey} - {label} shear check": "Verificación a corte del tabique {storey} - {label}",
    "Summary - All Beams": "Resumen - Todas las vigas",
    "Summary - All Walls": "Resumen - Todos los tabiques",
    "Beam Data": "Datos de las vigas",
    "Slab Summary Analysis": "Análisis del resumen de losas",
    "This report presents the detailed results for the first slab of the summary, followed by summary tables for all slabs.": "Este informe presenta los resultados detallados de la primera losa del resumen, seguidos de las tablas resumen de todas las losas.",
    "Summary - All Slabs": "Resumen - Todas las losas",
    "Slab Data": "Datos de las losas",
    "Wall Data": "Datos de los tabiques",
    "Flexure Results": "Resultados de flexión",
    "Shear Results": "Resultados de corte",
    "Design Check Summary": "Resumen de verificaciones",
}

# Structured warnings (mento.design_warnings). The English templates are the
# keys; the placeholders are filled after translation.
ES.update(
    {
        "bottom face": "cara inferior",
        "top face": "cara superior",
        "Steel on the {face}: A_s = {A_s} is below the minimum it has to meet, A_s,min,eff = {A_s_min_eff}.": (
            "Armadura en la {face}: A_s = {A_s} es menor que la mínima que tiene que cumplir, "
            "A_s,mín,ef = {A_s_min_eff}."
        ),
        "Steel on the {face}: A_s = {A_s} exceeds the maximum A_s,max = {A_s_max}.": (
            "Armadura en la {face}: A_s = {A_s} supera la máxima A_s,máx = {A_s_max}."
        ),
        "{component} = {value} is given but not checked: this element reads only N_x, V_z and M_y.": (
            "{component} = {value} está dado pero no se verifica: este elemento lee sólo N_x, V_z y M_y."
        ),
        (
            "The section is not tension-controlled (§{clause}): A_s = {A_s} on the {face} exceeds "
            "A_s,max = {A_s_max}. It does not comply, even where its capacity covers the moment."
        ): (
            "La sección no es controlada por tracción (§{clause}): A_s = {A_s} en la {face} supera "
            "A_s,máx = {A_s_max}. No cumple, aunque su capacidad alcance el momento."
        ),
        "Clear spacing between the bars on the {face}: {s} is below the minimum {s_min}.": (
            "Separación libre entre las barras de la {face}: {s} es menor que la mínima {s_min}."
        ),
        "Bar spacing on the {face}: {s} is below the minimum {s_min}.": (
            "Separación de barras en la {face}: {s} es menor que la mínima {s_min}."
        ),
        "Bar spacing on the {face}: {s} exceeds the maximum {s_max}.": (
            "Separación de barras en la {face}: {s} supera la máxima {s_max}."
        ),
        "The bars on the {face} do not fit in the width of the section.": (
            "Las barras de la {face} no entran en el ancho de la sección."
        ),
        (
            "Steel on the {face}: no layout that fits the section carries the moment "
            "(A_s,req = {A_s_req}); the design left A_s = {A_s}. Enlarge the section."
        ): (
            "Armadura en la {face}: ninguna disposición que entre en la sección resiste el momento "
            "(A_s,req = {A_s_req}); el diseño dejó A_s = {A_s}. Hay que agrandar la sección."
        ),
        "The section has no stirrups and requires shear reinforcement A_v = {A_v_req}.": (
            "La sección no tiene estribos y requiere armadura de corte A_v = {A_v_req}."
        ),
        "The stirrups provide A_v = {A_v}, below the minimum A_v,min = {A_v_min}.": (
            "Los estribos aportan A_v = {A_v}, menos que el mínimo A_v,mín = {A_v_min}."
        ),
        "Stirrup spacing along the member: {s} exceeds the maximum {s_max}.": (
            "Separación de estribos a lo largo del elemento: {s} supera la máxima {s_max}."
        ),
        "Stirrup leg spacing across the width: {s} exceeds the maximum {s_max}.": (
            "Separación de las ramas de estribo en el ancho: {s} supera la máxima {s_max}."
        ),
        "Shear V = {V} exceeds the most the section can carry, {V_max}: enlarge the section.": (
            "El corte V = {V} supera el máximo que admite la sección, {V_max}: hay que agrandarla."
        ),
        "Horizontal wall mesh: ρt = {rho} is below the required ρt = {rho_min}.": (
            "Malla horizontal del muro: ρt = {rho} es menor que la requerida ρt = {rho_min}."
        ),
        "Vertical wall mesh: ρl = {rho} is below the minimum ρl,min = {rho_min}.": (
            "Malla vertical del muro: ρl = {rho} es menor que la mínima ρl,mín = {rho_min}."
        ),
        ("Horizontal wall mesh spacing: {s} exceeds the maximum {s_max} (§11.7.3.1; lw/5 where Vu > φVc)."): (
            "Separación de la malla horizontal del muro: {s} supera la máxima {s_max} (§11.7.3.1; lw/5 donde Vu > φVc)."
        ),
        ("Vertical wall mesh spacing: {s} exceeds the maximum {s_max} (§11.7.2.1; lw/3 where Vu > φVc)."): (
            "Separación de la malla vertical del muro: {s} supera la máxima {s_max} (§11.7.2.1; lw/3 donde Vu > φVc)."
        ),
        (
            "Stirrup spacing along the member: {s} exceeds the {s_max} that lateral support of the "
            "{d_b_comp} compression bars allows (16 d_b, 48 d_b of the stirrup, least dimension of the beam)."
        ): (
            "Separación de estribos a lo largo del elemento: {s} supera los {s_max} que admite el "
            "arriostramiento de las barras comprimidas {d_b_comp} (16 d_b, 48 d_b del estribo, menor "
            "dimensión de la viga)."
        ),
        (
            "Stirrup diameter {d_b} is below the minimum {d_b_min} that lateral support of "
            "{d_b_comp} compression bars requires."
        ): (
            "Diámetro de estribo {d_b} menor que el mínimo {d_b_min} que exige el arriostramiento de "
            "barras comprimidas {d_b_comp}."
        ),
        (
            "The section relies on {d_b_comp} compression bars and has no stirrups to brace them: "
            "closed stirrups of at least {d_b_min} at no more than {s_max} are required."
        ): (
            "La sección depende de barras comprimidas {d_b_comp} y no tiene estribos que las arriostren: "
            "hacen falta estribos cerrados de al menos {d_b_min} separados a lo sumo {s_max}."
        ),
    }
)

# The §24.3.2 rows of a beam's flexure limits table (mento.reports.tables).
ES.update(
    {
        "Maximum spacing top": "Separación máxima superior",
        "Maximum spacing bottom": "Separación máxima inferior",
    }
)

# English is the source language, so its catalog is empty: every lookup falls
# through to the key itself.
_CATALOGS: Dict[str, Dict[str, str]] = {
    "en": {},
    "es": ES,
}

_language: str = DEFAULT_LANGUAGE


def available_languages() -> Tuple[str, ...]:
    """Language codes ``set_language`` accepts."""
    return tuple(sorted(_CATALOGS))


def set_language(language: str) -> None:
    """Set the language of every detailed report produced from now on.

    Parameters
    ----------
    language : str
        ISO 639-1 code, ``"en"`` or ``"es"``.

    Raises
    ------
    ValueError
        If the language has no catalog.
    """
    if language not in _CATALOGS:
        raise ValueError(f"Unknown language {language!r}. Available: {', '.join(available_languages())}.")
    global _language
    _language = language


def get_language() -> str:
    """The language detailed reports are currently rendered in."""
    return _language


#: The letter a stirrup count is written with: ``2eØ10`` for *estribo*,
#: ``2sØ10`` for *stirrup*. It is part of the notation, not of a sentence, so
#: it lives here rather than in a catalogue that falls back to English words.
_STIRRUP_MARK: Dict[str, str] = {"en": "s", "es": "e"}


def stirrup_mark() -> str:
    """The stirrup letter of the current language: ``"s"`` in English, ``"e"`` in Spanish."""
    return _STIRRUP_MARK[_language]


def translate(text: str, language: Optional[str] = None, **fields: Any) -> str:
    """Translate one report string, filling ``{placeholders}`` from ``fields``.

    Falls back to ``text`` when the catalog has no entry for it, so an
    untranslated label still renders.
    """
    catalog = _CATALOGS.get(get_language() if language is None else language, {})
    translated = catalog.get(text, text)
    return translated.format(**fields) if fields else translated


def translate_table(data: Mapping[str, List[Any]], language: Optional[str] = None) -> Dict[str, List[Any]]:
    """Translate a report table: its column headers and its label column.

    The first column holds the row labels; the rest are values, units and check
    marks, which stay as they are. Returns a new dict — the caller's table, which
    the section keeps as state, is never modified.
    """
    if not data:
        return dict(data)

    label_column = next(iter(data))
    translated: Dict[str, List[Any]] = {}
    for column, values in data.items():
        if column == label_column:
            values = [translate(v, language) if isinstance(v, str) else v for v in values]
        translated[translate(column, language)] = values
    return translated


def translate_dataframe(df: "pd.DataFrame", language: Optional[str] = None) -> "pd.DataFrame":
    """Same as :func:`translate_table`, for the DataFrames the Word builder takes."""
    from pandas import Index

    if not len(df.columns):
        return df

    out = df.copy()
    label_column = out.columns[0]
    out[label_column] = [translate(v, language) if isinstance(v, str) else v for v in out[label_column]]
    out.columns = Index([translate(str(c), language) for c in out.columns])
    return out
