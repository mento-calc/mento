"""Mento structural analysis package.

This package provides tools for structural analysis and design of concrete elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._version import __version__

# Expose units and Quantity directly to the user
from .units import (
    GPa,
    MPa,
    cm,
    deg,
    ft,
    inch,
    kg,
    kgf,
    kip,
    kN,
    kNm,
    kPa,
    ksi,
    lb,
    m,
    mm,
    psi,
    sec,
    ureg,
)

# Re-export Quantity for user convenience
__all__ = [
    "__version__",
    "ureg",
    "m",
    "cm",
    "mm",
    "kgf",
    "kN",
    "kNm",
    "kPa",
    "MPa",
    "GPa",
    "kg",
    "sec",
    "psi",
    "lb",
    "kip",
    "ksi",
    "inch",
    "ft",
    "deg",
    "Node",
    "Forces",
    "OneWaySlab",
    "Footing",
    "Concrete_ACI_318_19",
    "SteelBar",
    "Concrete_CIRSOC_201_25",
    "Concrete_EN_1992_2004",
    "RectangularBeam",
    "Formatter",
    "TablePrinter",
    "DocumentBuilder",
    "EN_1992_2004_beam",
    "ACI_318_19_beam",
    "BeamSettings",
    "BeamSummary",
    "OneWaySlabSummary",
    "Column",
    "PunchingSlab",
    "Opening",
    "Capital",
    "PunchingNode",
    "ShearWall",
    "ShearWallSummary",
    "set_language",
    "get_language",
    "available_languages",
    "TableStyle",
    "set_table_style",
    "get_table_style",
    "DesignWarning",
    "RebarOption",
    "StirrupOption",
    "WallMesh",
    "MeshDirection",
    "WallShearCheck",
    "WallShearDesign",
    "DesignNotRunError",
    "NotABeamError",
    "SummaryInputError",
    "SummaryInputWarning",
    "split_single_table",
    "SectionGeometry",
    "CageDetailingError",
    "CompressionDetailing",
    "CompressionFaceDetail",
    "SkinReinforcementRequirement",
    "SkinServiceCase",
    "SkinDistributionReview",
    "bar_designation",
    "bar_diameter",
]

if TYPE_CHECKING:
    from mento.bar_sizes import bar_designation, bar_diameter
    from mento.beam import RectangularBeam
    from mento.beam_summary import BeamSummary
    from mento.cage_detailing import CageDetailingError
    from mento.compression_detailing import CompressionDetailing, CompressionFaceDetail
    from mento.codes import ACI_318_19_beam, EN_1992_2004_beam
    from mento.column import Column
    from mento.design_results import DesignNotRunError, RebarOption, StirrupOption
    from mento.design_warnings import DesignWarning
    from mento.forces import Forces
    from mento.i18n import available_languages, get_language, set_language
    from mento.material import (
        Concrete_ACI_318_19,
        Concrete_CIRSOC_201_25,
        Concrete_EN_1992_2004,
        SteelBar,
    )
    from mento.node import Node
    from mento.results import DocumentBuilder, Formatter, TablePrinter
    from mento.slab_summary import OneWaySlabSummary
    from mento.punching import Capital, Opening, PunchingNode, PunchingSlab
    from mento.reports.table_style import TableStyle, get_table_style, set_table_style
    from mento.section_geometry import SectionGeometry
    from mento.settings import BeamSettings
    from mento.shear_wall import NotABeamError, ShearWall
    from mento.shear_wall_summary import ShearWallSummary
    from mento.skin_reinforcement import SkinDistributionReview, SkinReinforcementRequirement
    from mento.skin_service import SkinServiceCase
    from mento.slab import Footing, OneWaySlab
    from mento.wall_results import MeshDirection, WallMesh, WallShearCheck, WallShearDesign
    from mento.summary_tables import SummaryInputError, SummaryInputWarning, split_single_table


def __getattr__(name: str) -> object:
    # Map class names to their actual module files
    module_mapping = {
        "RectangularBeam": "beam",
        "bar_designation": "bar_sizes",
        "bar_diameter": "bar_sizes",
        "OneWaySlab": "slab",
        "Footing": "slab",
        "Node": "node",
        "BeamSettings": "settings",
        "Forces": "forces",
        "Concrete_ACI_318_19": "material",
        "SteelBar": "material",
        "Concrete_CIRSOC_201_25": "material",
        "Concrete_EN_1992_2004": "material",
        "Formatter": "results",
        "TablePrinter": "results",
        "DocumentBuilder": "results",
        "EN_1992_2004_beam": "codes.EN_1992_2004_beam",
        "ACI_318_19_beam": "codes.ACI_318_19_beam",
        "BeamSummary": "beam_summary",
        "OneWaySlabSummary": "slab_summary",
        "Column": "column",
        "PunchingSlab": "punching",
        "Opening": "punching",
        "Capital": "punching",
        "PunchingNode": "punching",
        "ShearWall": "shear_wall",
        "ShearWallSummary": "shear_wall_summary",
        "set_language": "i18n",
        "get_language": "i18n",
        "available_languages": "i18n",
        "TableStyle": "reports.table_style",
        "set_table_style": "reports.table_style",
        "get_table_style": "reports.table_style",
        "DesignWarning": "design_warnings",
        "RebarOption": "design_results",
        "StirrupOption": "design_results",
        "WallMesh": "wall_results",
        "MeshDirection": "wall_results",
        "WallShearCheck": "wall_results",
        "WallShearDesign": "wall_results",
        "DesignNotRunError": "design_results",
        "NotABeamError": "shear_wall",
        "SummaryInputError": "summary_tables",
        "SummaryInputWarning": "summary_tables",
        "split_single_table": "summary_tables",
        "SectionGeometry": "section_geometry",
        "CageDetailingError": "cage_detailing",
        "CompressionDetailing": "compression_detailing",
        "CompressionFaceDetail": "compression_detailing",
        "SkinReinforcementRequirement": "skin_reinforcement",
        "SkinServiceCase": "skin_service",
        "SkinDistributionReview": "skin_reinforcement",
    }

    if name in module_mapping:
        import importlib

        module = importlib.import_module(f".{module_mapping[name]}", __name__)
        # A name that is a module itself (the code modules) is the module: reading it
        # off its package only worked once something else had imported it.
        if module.__name__.rsplit(".", 1)[-1] == name:
            return module
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
