"""Explicit PTB-XL age sentinel policy for research-only cohort assignment.

PTB-XL records the de-identified 90+ age range as 300. Do not use 300
as a numeric age for means, standard deviations, or clinical decisions.
Missing ages are not inferred as <75; fail closed until a separately
approved missingness/subgroup policy exists.
"""
from __future__ import annotations
import math


def ptbxl_age75_membership(age: object) -> bool:
    """Return AGE75_PLUS membership; raise ValueError on unknown/invalid age."""
    if type(age) not in (int, float) or not math.isfinite(age):
        raise ValueError("missing or non-finite numeric age")
    if age == 300:
        return True  # PTB-XL age anonymization sentinel (90+), not literal age
    if not (0 <= age <= 120):
        raise ValueError("valid age must be in [0, 120] or PTB-XL sentinel 300")
    return age >= 75
