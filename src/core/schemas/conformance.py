"""The conformance statement: which spec-declared fields this seller does NOT implement.

Divergence from the spec has two directions and only one of them needs a table.

An ADDED field — the spec does not declare it, we carry it anyway — is written on the
subclass, typed and greppable, in the file the reader is already looking at. That
declaration IS the statement, and the set is derivable exactly as
``set(cls.model_fields) - library_declared_fields(cls)``
(:mod:`src.core.tools._announced_shape`). Listing it a second time here would only create
a second place to drift. **There is deliberately no added side to this module.**

An OMITTED field — the spec declares it, we do not implement it — has no syntax. Pydantic
inheritance is additive: a subclass cannot un-declare an inherited field by leaving it out.
:data:`OMITTED` names those fields, and :func:`omit_declared` removes them.

This module imports nothing from ``src``. It is strings and one function over the class it
decorates, so nothing it declares can create an import cycle with the schemas that consult
it — which is why the table lives here and not beside any one DTO.

Standards practice for implementing a subset of a protocol is a PICS, "a structured
document which asserts which specific requirements are met by a given implementation".
That is what this table is, in the repo, machine-readable.
"""

from collections.abc import Mapping

from pydantic import BaseModel

#: Class name -> {field name: why it is not implemented}.
#:
#: Keyed by NAME, not by the class, because the class imports the decorator and the
#: decorator reads the table; keying by the class would be the import cycle this module
#: exists to avoid. The name is also what the decorator looks itself up by, so a DTO
#: passes no field list of its own and there is nothing at the class to drift from what is
#: written here — there is only what is written here.
#:
#: Empty until the DTOs are narrowed one tool at a time (salesagent-prkv.106.7). A tool
#: with no row is a tool that has not been narrowed yet, not a tool that implements
#: everything.
OMITTED: Mapping[str, Mapping[str, str]] = {}


def omit_declared[ModelT: BaseModel](cls: type[ModelT]) -> type[ModelT]:
    """Remove the fields :data:`OMITTED` names for ``cls``, leaving the spec model untouched.

    Takes NO field names. It looks ``cls`` up in :data:`OMITTED` by name, so the list at
    the class cannot disagree with the list in the table.

    **A name that omitted nothing raises, at import.** ``dict.pop`` already reports whether
    the key was there, so a name the spec model does not declare is free to detect: a typo
    and a field an SDK bump removed are the same failure and get the same error, before the
    application starts. A test asserting the same property would permit the wrong table and
    then report it; refusing to construct it is strictly better, so no guard test replaces
    this.

    **``model_rebuild(force=True)`` is the last statement and is not optional.**
    ``model_fields`` is metadata; the validator and the JSON schema are compiled separately
    and, once compiled, do not notice the pop. Measured here at pydantic 2.12.5 / adcp
    6.6.0: with the validator already built, popping without the rebuild leaves a class
    whose ``model_fields`` reports the field gone while ``model_validate`` still ACCEPTS it
    and sets it on the instance. That is the announced-vs-accepted split this whole design
    exists to remove, occurring inside pydantic. The rebuild makes ``model_fields``, the
    published schema and the validator one thing.
    """
    stale = sorted(name for name in OMITTED[cls.__name__] if cls.model_fields.pop(name, None) is None)
    if stale:
        raise ValueError(f"{cls.__name__}: cannot omit {stale} — the spec model does not declare them")
    cls.model_rebuild(force=True)
    return cls
