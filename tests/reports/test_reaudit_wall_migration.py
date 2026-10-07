"""Legacy migration must retain a mesh declared on a later combination."""

import pandas as pd
import pytest

from mento import Concrete_ACI_318_19, MPa, ShearWallSummary, SteelBar, split_single_table


def table():
    units = dict(
        Level="",
        Label="",
        t="cm",
        lw="cm",
        hw="cm",
        cc="mm",
        dbh="mm",
        sh="cm",
        dbv="mm",
        sv="cm",
        Nx="kN",
        Vz="kN",
        My="kNm",
    )
    base = dict(Level="L1", Label="W1", t=20, lw=200, hw=300, cc=30, dbh=0, sh=0, dbv=0, sv=0, Nx=0, Vz=10, My=0)
    later = dict(base, dbh=10, sh=20, dbv=12, sv=20, Vz=20)
    return pd.DataFrame([units, base, later])


def test_migration_keeps_mesh_from_later_row_through_excel(tmp_path):
    sections, forces = split_single_table(table(), "wall")
    assert list(sections.iloc[1][["dbh", "sh", "dbv", "sv"]]) == [10, 20, 12, 20]
    concrete, steel = Concrete_ACI_318_19(name="C25", f_c=25 * MPa), SteelBar(name="B420", f_y=420 * MPa)
    summary = ShearWallSummary(concrete, steel, sections, forces)
    path = tmp_path / "wall.xlsx"
    summary.to_excel(path)
    restored = ShearWallSummary.from_excel(concrete, steel, path)
    assert restored.check().equals(summary.check())


def test_migration_rejects_conflicting_meshes():
    source = table()
    source.loc[1, ["dbh", "sh", "dbv", "sv"]] = [8, 20, 12, 20]
    with pytest.raises(ValueError, match="different meshes"):
        split_single_table(source, "wall")
