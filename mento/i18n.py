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
    "This report presents the detailed results for the first wall of the summary, followed by summary tables for all walls.": "Este informe presenta los resultados detallados del primer tabique del resumen, seguidos de las tablas resumen de todos los tabiques.",
    "Beam Sections": "Secciones de vigas",
    "Slab Summary Analysis": "Análisis del resumen de losas",
    "This report presents the detailed results for the first slab of the summary, followed by summary tables for all slabs.": "Este informe presenta los resultados detallados de la primera losa del resumen, seguidos de las tablas resumen de todas las losas.",
    "Summary - All Slabs": "Resumen - Todas las losas",
    "Slab Sections": "Secciones de losas",
    "Wall Sections": "Secciones de tabiques",
    "Forces": "Solicitaciones",
    "Face": "Cara",
    "Message": "Mensaje",
    "No section misses a detailing limit.": "Ninguna sección incumple un límite de detalle.",
    (
        "Nx > 0 is compression and enters the shear check only; My > 0 puts the bottom face in tension; "
        "Vz is taken in magnitude."
    ): (
        "Nx > 0 es compresión y entra solo en la verificación al corte; My > 0 tracciona la cara inferior; "
        "Vz se toma en valor absoluto."
    ),
    (
        "Nx > 0 is compression; Vz is the in-plane shear, taken in magnitude. My is not used: the summary "
        "checks the in-plane shear only."
    ): (
        "Nx > 0 es compresión; Vz es el corte en el plano, en valor absoluto. My no se usa: el resumen "
        "verifica solo el corte en el plano."
    ),
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

# The summaries of many sections (mento.summary_tables, mento.summary_base):
# the errors and warnings of reading their two tables, the headers of the
# check table and what design() prints. "Solicitaciones" names the forces
# table. The Warnings column holds mento's warning codes, which stay as they are.
ES.update(
    {
        (
            "{element} reads two tables, the sections and the forces, and the table given is the single table of "
            'mento 1.4.0 (it has {columns}). Convert it with `sections, forces = mento.split_single_table(table, "{kind}")` '
            "and pass both; each of its rows becomes a section of its own and that section's forces, which is what "
            "1.4.0 computed."
        ): (
            "{element} lee dos tablas, la de secciones y la de solicitaciones, y la tabla dada es la tabla única de "
            'mento 1.4.0 (tiene {columns}). Convertila con `sections, forces = mento.split_single_table(table, "{kind}")` '
            "y pasá las dos; cada fila pasa a ser una sección propia con sus solicitaciones, que es lo que calculaba "
            "1.4.0."
        ),
        (
            "{element} reads two tables, the sections and the forces, and the table given has both in one (it has "
            "{columns}). Give one row per slab in the sections table, with the layers of both faces, and one row per "
            "combination in the forces table."
        ): (
            "{element} lee dos tablas, la de secciones y la de solicitaciones, y la tabla dada tiene las dos en una "
            "(tiene {columns}). Poné una fila por losa en la tabla de secciones, con las capas de las dos caras, y una "
            "fila por combinación en la de solicitaciones."
        ),
        (
            "{element} reads two tables; the forces table is missing. A section with no combination is a row of "
            "sections and no row of forces."
        ): (
            "{element} lee dos tablas y falta la de solicitaciones. Una sección sin combinaciones es una fila de "
            "secciones sin filas de solicitaciones."
        ),
        (
            "The sections table has the force columns ({columns}) and the forces table the geometry: pass sections "
            "first, then forces."
        ): (
            "La tabla de secciones tiene las columnas de solicitaciones ({columns}) y la de solicitaciones la geometría: "
            "pasá primero las secciones y después las solicitaciones."
        ),
        "The file {path} has no sheet {sheet}: a summary file holds two sheets, {sections} and {forces}.": (
            "El archivo {path} no tiene la hoja {sheet}: un archivo de resumen tiene dos hojas, {sections} y {forces}."
        ),
        "The {table} table has no column {columns}. Its columns are {expected}.": (
            "La tabla {table} no tiene la columna {columns}. Sus columnas son {expected}."
        ),
        (
            "The {table} table has columns {element} does not read: {columns}{hint}. Its columns are {expected}; "
            "free text goes in Notes."
        ): (
            "La tabla {table} tiene columnas que {element} no lee: {columns}{hint}. Sus columnas son {expected}; "
            "el texto libre va en Notes."
        ),
        "The {table} table has the columns of a {other} ({columns}); {element} reads {expected}.": (
            "La tabla {table} tiene las columnas de otro elemento, {other} ({columns}); {element} lee {expected}."
        ),
        "A one-way slab strip is detailed without stirrups, so its sections table has no {columns}.": (
            "Una faja de losa en una dirección se arma sin estribos, así que su tabla de secciones no tiene {columns}."
        ),
        "Column {column} of the {table} table is a {kind}, and its unit row says {unit}. Use one of {allowed}.": (
            "La columna {column} de la tabla {table} es de tipo {kind} y su fila de unidades dice {unit}. "
            "Usá una de {allowed}."
        ),
        "Row {row} ({nth} data row) of the {table} table has no Label.": (
            "La fila {row} ({nth} fila de datos) de la tabla {table} no tiene Label."
        ),
        (
            "The sections table gives {label} more than once (rows {rows}). If they are different sections (e.g. a "
            "support and a midspan with different bars), give each its own label; if one section takes several "
            "combinations, give it one row here and its combinations in the forces table."
        ): (
            "La tabla de secciones da {label} más de una vez (filas {rows}). Si son secciones distintas (por ejemplo, "
            "un apoyo y un tramo con barras distintas), dale a cada una su label; si es una sección con varias "
            "combinaciones, dale una fila acá y sus combinaciones en la tabla de solicitaciones."
        ),
        "The forces table names {label} (rows {rows}), which is not in the sections table.": (
            "La tabla de solicitaciones nombra {label} (filas {rows}), que no está en la tabla de secciones."
        ),
        "{column} of {label} is empty in the {table} table.": "{column} de {label} está vacía en la tabla {table}.",
        "{column} of {label} is {value} in the {table} table, not a number.": (
            "{column} de {label} es {value} en la tabla {table}, que no es un número."
        ),
        "{column} of {label} is {value}; it cannot be negative.": "{column} de {label} es {value}; no puede ser negativa.",
        "{column} of {label} is {value}; it has to be greater than zero.": (
            "{column} de {label} es {value}; tiene que ser mayor que cero."
        ),
        "{column} of {label} is {value}; a number of bars or stirrups is a whole number.": (
            "{column} de {label} es {value}; una cantidad de barras o de estribos es un número entero."
        ),
        "{label}: {given} is given without {missing}.": "{label}: se da {given} sin {missing}.",
        "Node {label} is of {its_material}; the summary is of {material}.": (
            "El nodo {label} es de {its_material}; el resumen es de {material}."
        ),
        "Node {label} cannot be written as a table row: {reason}.": (
            "El nodo {label} no se puede escribir como una fila de la tabla: {reason}."
        ),
        "{label} has no forces in the forces table, so it has no results to report.": (
            "{label} no tiene solicitaciones en la tabla de solicitaciones, así que no tiene resultados."
        ),
        "The summary has no section {index}; its sections are {labels}.": (
            "El resumen no tiene la sección {index}; sus secciones son {labels}."
        ),
        "{labels}: no forces in the forces table; kept as given and shown as not checked.": (
            "{labels}: sin solicitaciones en la tabla de solicitaciones; se conservan tal cual y figuran como no "
            "verificadas."
        ),
        (
            "The forces table gives combination {combination} of {label} more than once (rows {rows}): a section "
            "takes each combination once. Give each row its own name (an envelope's Max and Min, each station of a "
            "member), or make them two sections."
        ): (
            "La tabla de solicitaciones da la combinación {combination} de {label} más de una vez (filas {rows}): "
            "una sección toma cada combinación una sola vez. Dale a cada fila su nombre (el Máx y el Mín de una "
            "envolvente, cada estación de una barra) o hacé de ellas dos secciones."
        ),
        (
            "legs of {label} is {value}: the stirrups are closed, two legs each (legs = 2 x stirrups), so the number "
            "of legs is even."
        ): (
            "legs de {label} es {value}: los estribos son cerrados, de dos ramas cada uno (legs = 2 x estribos), "
            "así que la cantidad de ramas es par."
        ),
        (
            "The forces table has no Nx column: N is taken as 0. A tension omitted makes the shear check unconservative."
        ): (
            "La tabla de solicitaciones no tiene la columna Nx: se toma N = 0. Una tracción omitida deja la "
            "verificación al corte del lado inseguro."
        ),
        (
            "{pairs}: Nx >= 0.10 f'c Ag in compression. ACI 318-19 / CIRSOC 201-25 §9.5.2.2 compute the moment "
            "strength with the axial load (§22.4, P-M interaction); closed stirrups or spirals follow Table 22.4.2.1. "
            "R/C9.5.2.2 does not require Chapter 10. mento checks bending alone (§22.3); this case needs separate verification."
        ): (
            "{pairs}: Nx >= 0,10 f'c Ag en compresión. ACI 318-19 / CIRSOC 201-25 §9.5.2.2 calculan la resistencia "
            "a flexión con el axil (§22.4, interacción P-M); estribos cerrados o zunchos según la Tabla 22.4.2.1. "
            "R/C9.5.2.2 no exige el Capítulo 10. mento verifica flexión sola (§22.3); este caso requiere verificación aparte."
        ),
        (
            "{labels}: Vu > φVc with the bars designed; more longitudinal steel, more thickness, a higher f'c, or shear "
            "reinforcement detailed as a beam (ACI 318-19 §7.6.3). check() gives them as failing."
        ): (
            "{labels}: Vu > φVc con las barras diseñadas; hace falta más armadura longitudinal, más espesor, un f'c "
            "mayor o armadura de corte detallada como en una viga (ACI 318-19 §7.6.3). check() las da como no "
            "verificadas."
        ),
        "{pairs}: repeated labels renamed; each row is a section of its own, as in 1.4.0.": (
            "{pairs}: labels repetidos renombrados; cada fila es una sección propia, como en 1.4.0."
        ),
        (
            "{labels}: 1.4.0 read n3/n4 as a second layer of the face in tension, not the opposite face; check them "
            "against your drawings."
        ): (
            "{labels}: 1.4.0 leía n3/n4 como una segunda capa de la cara traccionada, no como la cara opuesta; "
            "controlalas contra los planos."
        ),
        "{cells}: cells 1.4.0 ignored (a diameter with no bars, a stirrup with ns = 0) were dropped.": (
            "{cells}: se borraron celdas que 1.4.0 ignoraba (un diámetro sin barras, un estribo con ns = 0)."
        ),
        # -- what design(), export_design() and import_design() print -----
        "✅ Design completed for every section of the summary.": (
            "✅ Diseño completo para todas las secciones del resumen."
        ),
        "Slabs designed.": "Losas diseñadas.",
        "✅ Sections and forces written to {path}": "✅ Secciones y solicitaciones escritas en {path}",
        "✅ Sections and forces read from {path}": "✅ Secciones y solicitaciones leídas de {path}",
        # -- the check table ----------------------------------------------
        "Warnings": "Advertencias",
        "Horiz. (each face)": "Horiz. (c/cara)",
        "Vert. (each face)": "Vert. (c/cara)",
        "no forces": "sin esfuerzos",
        "no reinforcement: run design()": "sin armadura: correr design()",
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
