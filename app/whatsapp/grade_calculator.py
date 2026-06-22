"""
Dynamic grade-range calculator based on Mexican school cycle rules.

Base data: cycle 2026-2027 (from Edades_Colegio_Americano_26-27.csv).
School cycles run August–June. A child's grade is determined by their
birth date falling within the range Aug 1 → Jul 31 of the corresponding year.

For cycle 20XX-20(XX+1), all birth-year bounds shift by (XX - 2026).
"""

from datetime import date
from typing import Dict, List, Optional, Tuple


# Base cycle start year (matches the CSV)
_BASE_CYCLE_START = 2026

# (grade_name, division, birth_year_start, birth_year_end)
# birth_year_start  → year of the Aug-1 lower bound
# birth_year_end    → year of the Jul-31 upper bound
_BASE_GRADES: List[Tuple[str, str, int, int]] = [
    ("Prenursery",     "prenursery",    2023, 2024),
    ("Nursery",        "early_child",   2022, 2023),
    ("Preschool",      "early_child",   2021, 2022),
    ("Kindergarten",   "early_child",   2020, 2021),
    ("Primaria 1",     "elementary",    2019, 2020),
    ("Primaria 2",     "elementary",    2018, 2019),
    ("Primaria 3",     "elementary",    2017, 2018),
    ("Primaria 4",     "elementary",    2016, 2017),
    ("Primaria 5",     "elementary",    2015, 2016),
    ("Primaria 6",     "elementary",    2014, 2015),
    ("Secundaria 1",   "middle_school", 2013, 2014),
    ("Secundaria 2",   "middle_school", 2012, 2013),
    ("Secundaria 3",   "middle_school", 2011, 2012),
    ("Bachillerato 1", "high_school",   2010, 2011),
    ("Bachillerato 2", "high_school",   2009, 2010),
    ("Bachillerato 3", "high_school",   2008, 2009),
]


def get_grade_ranges(cycle_start_year: int) -> List[Dict]:
    """Return grade ranges for the cycle starting in *cycle_start_year*."""
    offset = cycle_start_year - _BASE_CYCLE_START
    result = []
    for grade_name, division, base_start, base_end in _BASE_GRADES:
        result.append({
            "grade": grade_name,
            "division": division,
            "dob_start": date(base_start + offset, 8, 1),
            "dob_end": date(base_end + offset, 7, 31),
        })
    return result


def determine_grade(dob: date, cycle_start_year: int) -> Optional[Dict]:
    """Given a birth date and cycle, return the matching grade or None."""
    for entry in get_grade_ranges(cycle_start_year):
        if entry["dob_start"] <= dob <= entry["dob_end"]:
            return entry
    return None


def build_grade_ranges_prompt(cycle_start_year: int) -> str:
    """Build a prompt-friendly string with DOB ranges for *cycle_start_year*."""
    ranges = get_grade_ranges(cycle_start_year)
    label = f"{cycle_start_year}-{cycle_start_year + 1}"
    parts = [f"Rangos de fechas de nacimiento para ciclo {label} (estrictos):"]
    for entry in ranges:
        s = entry["dob_start"].strftime("%d-%b-%Y")
        e = entry["dob_end"].strftime("%d-%b-%Y")
        parts.append(f"{entry['grade']}: {s} a {e};")
    return " ".join(parts)
