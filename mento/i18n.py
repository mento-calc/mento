"""Language of the text mento presents: reports, drawings, warnings, stirrup notation.

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

Scope. Translated: the detailed reports and the summaries, the text of the
section drawing (``beam.plot()``), the warning messages (``DesignWarning.message``,
worded when ``warnings`` is read), and the stirrup notation and cage description
when asked for through ``notation()`` / ``arrangement()`` of a transverse result,
which follow the language of the moment unless given one. Not translated: the
``str()`` of the result objects of :mod:`mento.design_results` -- the reinforcement,
design and check results -- which stays English (``DesignWarning`` is the exception:
its ``str()`` is its ``message``, worded as above), variable names (``fc``,
``Av``, ``DCR``), units, numbers, the design code designation, generated file
names, attribute names and error messages.
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
    "Detailing notes": "Notas de detallado",
    "Supplied skin does not comply: {reason}": "Piel ingresada: NO CUMPLE: {reason}",
    "{placed} proposed legs; A_v uses {entered}. Compression support: {status}.": "{placed} ramas propuestas; A_v usa {entered}. Sujeción comprimida: {status}.",
    "passed": "cumple",
    "failed": "no cumple",
    "pending": "pendiente",
    "Detailing proposes {placed_legs} legs instead of {input_legs}: {pieces}. Enter the proposed legs to confirm; A_v still uses {input_legs}.": "El detallado propone {placed_legs} ramas en vez de {input_legs}: {pieces}. Ingrese las ramas propuestas para confirmar; A_v sigue usando {input_legs}.",
    "Open-leg hooks and anchorage are outside this sectional model; verify them separately.": "Los ganchos y anclajes de patas abiertas quedan fuera de este modelo seccional; verifíquelos aparte.",
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
        (
            "No layout that fits the section, with room for the vibrator between the top bars, and keeps within "
            "the code's limits on the reinforcement carries M = {M}: the closest one carries {M_capacity}. "
            "Enlarge the section."
        ): (
            "Ningún armado que entre en la sección, dejando lugar al vibrador entre las barras superiores, y "
            "respete los límites de armadura de la norma resiste M = {M}: el más cercano resiste {M_capacity}. "
            "Hay que agrandar la sección."
        ),
        (
            "Clear spacing between the bars on the {face}: {s} leaves no room for the vibrator, {s_min}. "
            "The concrete cannot be consolidated."
        ): (
            "Separación libre entre las barras de la {face}: {s} no deja pasar el vibrador, {s_min}. "
            "El hormigón no se puede vibrar."
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

# The stirrup notation and the description of the cage (mento.design_results),
# asked for through ``notation()`` / ``arrangement()``. The wording is the one the notation was specified with:
# legs first, "c/" for the spacing along the member. "Gancho suplementario" is
# the CIRSOC 201 name of the ACI crosstie.
ES.update(
    {
        "{n_legs} legs Ø{d_b} @ {s_l}": "{n_legs} ramas Ø{d_b} c/{s_l}",
        "{s_w} between legs": "{s_w} entre ramas",
        "(max {s_max_w})": "(máx. {s_max_w})",
        "{n_legs} legs Ø{d_b}/{s_l}": "{n_legs} ramas Ø{d_b}/{s_l}",
        "no stirrups": "sin estribos",
        "single perimeter stirrup": "estribo perimetral",
        "perimeter stirrup": "estribo perimetral",
        "1 inner stirrup": "1 interior",
        "{n} inner stirrups": "{n} interiores",
        "1 open leg": "1 pata abierta",
        "{n} open legs": "{n} patas abiertas",
        "1 crosstie": "1 gancho suplementario",
        "{n} crossties": "{n} ganchos suplementarios",
        "135°/90° crossties: alternate the 90° ends along the member; seismic detailing not verified.": "Trabas 135°/90°: alternar los extremos de 90° a lo largo de la viga; detallado sísmico no verificado.",
        "The crosstie hook size is outside the supported model": "El tamaño del gancho de la traba está fuera del modelo admitido",
    }
)

# The rows that say how many legs the cage has, how far apart, and which row of
# Table 9.7.6.2.2 set the spacing limits (mento.reports.tables). Across the width
# is "en el ancho", along the member "en la dirección longitudinal", as in the
# rows and warnings above.
ES.update(
    {
        "Number of legs": "Número de ramas",
        "Leg spacing across width": "Separación de ramas en el ancho",
        "Leg spacing across width (Table 9.7.6.2.2)": "Separación de ramas en el ancho (Tabla 9.7.6.2.2)",
        "Leg spacing across width (§9.2.2(8))": "Separación de ramas en el ancho (§9.2.2(8))",
        "Stirrup spacing along width (Table 9.7.6.2.2)": (
            "Separación de estribos en la dirección transversal (Tabla 9.7.6.2.2)"
        ),
        "Nominal shear the stirrups must carry (Vu/φ − Vc)": "Corte nominal que deben resistir los estribos (Vu/φ − Vc)",
        "Threshold of Table 9.7.6.2.2 (0.33√f'c·bw·d)": "Umbral de la Tabla 9.7.6.2.2 (0.33√f'c·bw·d)",
        "Threshold of Table 9.7.6.2.2 (4√f'c·bw·d)": "Umbral de la Tabla 9.7.6.2.2 (4√f'c·bw·d)",
        "Vs,req > Vs,lim → Table 9.7.6.2.2: d/4 along, d/2 across": (
            "Vs,req > Vs,lim → Tabla 9.7.6.2.2: d/4 a lo largo, d/2 en el ancho"
        ),
        "Vs,req ≤ Vs,lim → Table 9.7.6.2.2: d/2 along, d across": (
            "Vs,req ≤ Vs,lim → Tabla 9.7.6.2.2: d/2 a lo largo, d en el ancho"
        ),
        "Absolute cap of Table 9.7.6.2.2 in this row": "Tope absoluto de la Tabla 9.7.6.2.2 en esta fila",
        "Stirrup spacing, lateral support of compression bars (§9.7.6.4.3)": (
            "Separación de estribos, sujeción de barras comprimidas (§9.7.6.4.3)"
        ),
        "Expression (9.6N) along: 0.75·d·(1 + cot α), capped at 400 mm by mento": (
            "Expresión (9.6N) a lo largo: 0.75·d·(1 + cot α), tope de 400 mm de mento"
        ),
        "Expression (9.8N) across: 0.75·d, at most 600 mm": "Expresión (9.8N) en el ancho: 0.75·d, como máximo 600 mm",
    }
)

ES.update(
    {
        "mounting": "montaje",
        "Orange: mounting steel · excluded from resistance": "Montaje en naranja · sin aporte resistente",
        "Calculation model only · cage detailing not feasible": "Solo modelo de cálculo · jaula no detallable",
        "Skin proposal not shown · skin detailing not feasible": "No se muestra la propuesta de piel · detalle de piel inviable",
        "The base cage cannot be detailed: {reason}": "La jaula principal no puede detallarse: {reason}",
        "Tension-bar spacing pending · no flexure verification": "Separación por tracción pendiente · sin verificación de flexión",
    }
)

# English is the source language, so its catalog is empty: every lookup falls
# through to the key itself.
ES.update(
    {
        "Longitudinal skin reinforcement is required on both side faces (§9.7.2.3), "
        "at spacing no greater than {s_max}. See detailing_geometry for the supplementary proposal; "
        "it is excluded from resistance.": "Se requiere armadura longitudinal de piel en ambos laterales (§9.7.2.3), "
        "con separación no mayor que {s_max}. Ver la propuesta complementaria en detailing_geometry; "
        "no se computa en la resistencia.",
        "Skin reinforcement is pending: verify flexure to identify the tension face.": "Armadura de piel pendiente: verificar flexión para identificar la cara traccionada.",
        "Skin detailing cannot be evaluated: {reason}": "No se puede evaluar el detalle de piel: {reason}",
        "Skin reinforcement is not supported for this design case; this is not an exemption.": "La armadura de piel no está implementada para este caso de diseño; esto no constituye una exención.",
        "The supplementary skin proposal cannot be fitted in the cage: {reason}": "La propuesta complementaria de piel no entra en la jaula: {reason}",
        "The skin reinforcement preference cannot satisfy the detailing limits.": "La configuración de armadura de piel no permite cumplir los límites del detalle.",
    }
)

ES.update(
    {
        "EN §7.3.3(3): longitudinal skin steel is required; minimum {area} per side, adjusted maximum diameter {diameter}. Excluded from resistance.": "EN §7.3.3(3): se requiere piel longitudinal; mínimo {area} por lateral, diámetro máximo corregido {diameter}. Sin aporte resistente.",
        "EN skin detailing is pending: supply cracked-service steel stress and neutral-axis depth; ultimate forces cannot replace them.": "Detalle de piel EN pendiente: indicar tensión del acero y profundidad del eje neutro en servicio fisurado; los esfuerzos últimos no los reemplazan.",
        "EN skin detailing with axial force is not supported; the pure-bending skin proposal cannot be used.": "La piel EN con esfuerzo axial no está implementada; no corresponde aplicar la propuesta de flexión pura.",
        "Skin reinforcement is pending: the checked combinations identify no tension face. A zero-moment or capacity check does not establish an exemption.": "La armadura de piel está pendiente: las combinaciones verificadas no identifican una cara traccionada. Una comprobación con momento nulo o de capacidad no establece una exención.",
        "Review skin ({face}): {rows} rows · max interval {gap}": "Revisar piel ({face}): {rows} filas · intervalo máx. {gap}",
        "Informative review · crack width is not calculated": "Aviso informativo · no se calcula el ancho de fisura",
        "Skin not checked · unsupported design case": "Piel no comprobada · caso de diseño no implementado",
        "Review skin-steel distribution, worst of {cases} service cases: {rows} rows per side in that zone, largest vertical interval {gap}, including zone boundaries. This is informative, not an additional code spacing limit; the diameter-route proposal does not verify crack width directly.": "Revisar la distribución de piel, peor de {cases} casos de servicio: {rows} filas por lateral en esa zona, mayor intervalo vertical {gap}, incluyendo los bordes de la zona. Es informativo, no un límite normativo adicional de separación; la propuesta por diámetro no comprueba directamente el ancho de fisura.",
        "EN surface reinforcement outside the links requires separate review: Annex J covers bars >32 mm, equivalent bundles >32 mm (bundles are not modelled; check separately), or cover >70 mm. Section 8.8(8) specifies 0.01*A_ct,ext perpendicular and 0.02*A_ct,ext parallel to large bars. Longitudinal skin bars do not replace this mesh.": "La armadura superficial EN fuera de los estribos requiere revisión aparte: Anexo J para barras >32 mm, paquetes equivalentes >32 mm (mento no modela paquetes; revisarlos aparte) o recubrimiento >70 mm. El §8.8(8) especifica 0,01*A_ct,ext perpendicular y 0,02*A_ct,ext paralela a barras grandes. La piel longitudinal no sustituye esa malla.",
    }
)

_CATALOGS: Dict[str, Dict[str, str]] = {
    "en": {},
    "es": ES,
}

_language: str = DEFAULT_LANGUAGE


def available_languages() -> Tuple[str, ...]:
    """Language codes ``set_language`` accepts."""
    return tuple(sorted(_CATALOGS))


def set_language(language: str) -> None:
    """Set the language of the text mento presents from now on.

    Every detailed report and summary, the drawing, the warning messages, and
    the ``notation()`` / ``arrangement()`` of a transverse result asked for
    without a language. ``str()`` of the results of :mod:`mento.design_results`
    stays English; that of a ``DesignWarning`` is its message, which follows.

    Parameters
    ----------
    language : str
        ISO 639-1 code, ``"en"`` or ``"es"``.

    Raises
    ------
    ValueError
        If the language has no catalog.
    """
    checked_language(language)
    global _language
    _language = language


def checked_language(language: Optional[str]) -> Optional[str]:
    """``language`` itself, once it is known to have a catalog; ``None`` stays ``None``.

    For a function that takes a ``language`` argument: an explicit code is held
    to the same rule as :func:`set_language`, so a typo or a locale such as
    ``"es-AR"`` raises instead of falling back to English, while ``None`` --
    the language of the moment, which ``set_language`` already checked --
    passes through.

    Raises
    ------
    ValueError
        If ``language`` is given and has no catalog.
    """
    if language is not None and language not in _CATALOGS:
        raise ValueError(f"Unknown language {language!r}. Available: {', '.join(available_languages())}.")
    return language


def get_language() -> str:
    """The language mento currently presents its text in (see :func:`set_language`)."""
    return _language


#: Compatibility with the former count-first notation. Current transverse
#: notation uses translated leg counts and does not call this helper.
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


# Required compression-bar support; statuses and reasons are localized.
ES.update(
    {
        "EN compression-bar support (§9.2.1.2(3), 15φ) is not verified by Mento.": "Mento no verifica la sujeción de barras comprimidas EN (§9.2.1.2(3), 15φ).",
        "Required compression-bar support fails (§9.7.6.4.4): {reason}.": "No cumple el arriostramiento de barras requeridas por compresión (§9.7.6.4.4): {reason}.",
        "Required compression-bar support is not fully verified (§9.7.6.4.4): {reason}.": "El arriostramiento de barras requeridas por compresión no está completamente verificado (§9.7.6.4.4): {reason}.",
        "Required compression-bar support: {status}": "Arriostramiento de barras requeridas por compresión: {status}",
        "failed": "no cumple",
        "pending": "pendiente",
        "A corner bar is not braced by a stirrup corner": "Una barra de esquina no está arriostrada por una esquina de estribo",
        "Two successive compression bars lack corner support": "Dos barras comprimidas consecutivas carecen de arriostramiento por esquina",
        "A required compression bar lies outside the closed stirrup": "Una barra requerida por compresión queda fuera del estribo cerrado",
        "The clear distance on a side exceeds the permitted limit": "La distancia libre a uno de los lados supera el límite permitido",
        "The 15 d_be and 150 mm limits give different outcomes; interpretation pending": "Los límites 15 d_be y 150 mm dan resultados distintos; interpretación pendiente",
        "Second-row compression support requires a separate detail": "El arriostramiento de la segunda capa comprimida requiere un detalle específico",
        "Crosstie anchorage is not verified": "El anclaje de los estribos suplementarios no está verificado",
        "The required first compression row is missing": "Falta la primera capa requerida por compresión",
        "Required compression steel has no closed stirrups": "La armadura requerida por compresión no tiene estribos cerrados",
        "The stirrup bend is outside the supported model": "El doblado del estribo queda fuera del modelo admitido",
    }
)


ES.update(
    {
        "Resistance and detailing": "Resistencia y detallado",
        "Verification": "Verificación",
        "Resistance": "Resistencia",
        "Detailing (modelled checks)": "Detallado (chequeos modelados)",
        "Pass (modelled checks)": "Cumple (chequeos modelados)",
        "Fail": "No cumple",
        "Pending": "Pendiente",
        "Mento does not yet model axial force in EN footings (a Mento limitation, not a Eurocode prohibition). Omitting it is conservative only for compression; with tension, verify outside Mento.": "Mento todavía no modela el axil en zapatas EN (limitación de Mento, no del Eurocódigo). Omitirlo solo es conservador si es compresión; con tracción, verificar fuera de Mento.",
    }
)

ES["Mandatory detailing: compression-bar support spacing (§9.7.6.4.3)"] = (
    "Detallado obligatorio: separación del arriostramiento de barras comprimidas (§9.7.6.4.3)"
)


ES.update(
    {
        "The base cage cannot yet be verified: {reason}": "La jaula principal todavía no puede verificarse: {reason}",
        "The base cage cannot be detailed: {reason}": "La jaula principal no puede detallarse: {reason}",
    }
)


# Singular del aviso global; conserva las etiquetas, sin atribuir una cara.
ES.update(
    {
        "Skin layout is not verified: the detailing geometry does not contain the specified skin bars.": "La piel no está verificada: la geometría de detallado no contiene las barras de piel especificadas.",
        "The supplied skin reinforcement does not comply: {reason}": "La armadura de piel ingresada no cumple: {reason}",
        "No height is available for the supplied skin zone.": "No hay altura disponible para la zona de piel ingresada.",
        "The supplied skin bars cannot fit with the required clear spacing.": "Las barras de piel ingresadas no entran con la separación libre requerida.",
        "The supplied skin diameter exceeds the supported EN diameter limit.": "El diámetro de piel ingresado excede el límite de la propuesta EN implementada.",
        "The supplied skin does not cover the bottom tension zone.": "La piel ingresada no cubre la zona inferior traccionada.",
        "The supplied skin does not cover the top tension zone.": "La piel ingresada no cubre la zona superior traccionada.",
        "The supplied skin spacing exceeds the limit in the bottom tension zone.": "La separación de piel excede el límite en la zona inferior traccionada.",
        "The supplied skin spacing exceeds the limit in the top tension zone.": "La separación de piel excede el límite en la zona superior traccionada.",
        "The supplied skin area is insufficient in the bottom tension zone.": "El área de piel es insuficiente en la zona inferior traccionada.",
        "The supplied skin area per lateral face is insufficient.": "El área de piel por cara lateral es insuficiente.",
        "The supplied skin area is insufficient in the top tension zone.": "El área de piel es insuficiente en la zona superior traccionada.",
    }
)
ES.update(
    {
        "Review skin-steel distribution, worst of {cases} service case: {rows} rows per side in that zone, largest vertical interval {gap}, including zone boundaries. This is informative, not an additional code spacing limit; the diameter-route proposal does not verify crack width directly.": "Revisar la distribución de piel, peor de {cases} caso de servicio: {rows} filas por lateral en esa zona, mayor intervalo vertical {gap}, incluyendo los bordes de la zona. Es informativo, no un límite normativo adicional de separación; la propuesta por diámetro no comprueba directamente el ancho de fisura.",
    }
)
