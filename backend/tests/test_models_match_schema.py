"""The SQLAlchemy models must describe the database that schema.sql + migrations actually build."""
import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect

from database import engine
from models import Base


@pytest.fixture(scope="module")
def db_inspector():
    return inspect(engine)


def model_foreign_keys(table):
    return {
        (tuple(fk.column_keys), fk.elements[0].column.table.name, tuple(e.column.name for e in fk.elements))
        for fk in table.constraints
        if isinstance(fk, ForeignKeyConstraint)
    }


def model_uniques(table):
    result = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    result |= {(column.name,) for column in table.columns if column.unique}
    return result


@pytest.mark.parametrize("table_name", sorted(Base.metadata.tables))
def test_model_matches_database(db_inspector, table_name):
    table = Base.metadata.tables[table_name]
    problems = []

    # Columns, nullability and server-side defaults (primary keys are generated, not defaulted).
    db_columns = {c["name"]: c for c in db_inspector.get_columns(table_name)}
    if set(db_columns) != {c.name for c in table.columns}:
        problems.append(f"columns differ: db={sorted(db_columns)} model={sorted(c.name for c in table.columns)}")
    for column in table.columns:
        db_column = db_columns.get(column.name)
        if db_column is None or column.primary_key:
            continue
        if column.nullable != db_column["nullable"]:
            problems.append(f"{column.name}: nullable model={column.nullable} db={db_column['nullable']}")
        if (column.server_default is not None) != (db_column["default"] is not None):
            problems.append(f"{column.name}: server default model={column.server_default is not None} db={db_column['default']!r}")

    # Primary key
    db_pk = tuple(db_inspector.get_pk_constraint(table_name)["constrained_columns"])
    if set(db_pk) != {c.name for c in table.primary_key.columns}:
        problems.append(f"primary key differs: db={db_pk} model={[c.name for c in table.primary_key.columns]}")

    # Foreign keys
    db_fks = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
        for fk in db_inspector.get_foreign_keys(table_name)
    }
    if db_fks != model_foreign_keys(table):
        problems.append(f"foreign keys differ: db-only={sorted(db_fks - model_foreign_keys(table))} model-only={sorted(model_foreign_keys(table) - db_fks)}")

    # Unique constraints
    db_uniques = {tuple(u["column_names"]) for u in db_inspector.get_unique_constraints(table_name)}
    if db_uniques != model_uniques(table):
        problems.append(f"unique constraints differ: db-only={sorted(db_uniques - model_uniques(table))} model-only={sorted(model_uniques(table) - db_uniques)}")

    # CHECK constraints (by name)
    db_checks = {c["name"] for c in db_inspector.get_check_constraints(table_name)}
    model_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    if db_checks != model_checks:
        problems.append(f"check constraints differ: db-only={sorted(db_checks - model_checks)} model-only={sorted(model_checks - db_checks)}")

    # Indexes that are not just the backing index of a primary key or unique constraint
    db_indexes = {i["name"] for i in db_inspector.get_indexes(table_name) if not i.get("duplicates_constraint")}
    model_indexes = {i.name for i in table.indexes}
    if db_indexes != model_indexes:
        problems.append(f"indexes differ: db-only={sorted(db_indexes - model_indexes)} model-only={sorted(model_indexes - db_indexes)}")

    assert not problems, f"{table_name}: " + "; ".join(problems)


def test_every_database_table_has_a_model(db_inspector):
    assert set(db_inspector.get_table_names()) == set(Base.metadata.tables)
