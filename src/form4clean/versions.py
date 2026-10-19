"""Version numbers that travel with every dataset.

* ``SCHEMA_VERSION`` changes when columns are added, removed, renamed or retyped.
* ``CLEANING_VERSION`` changes when any cleaning, classification, reconciliation or quality rule
  changes, so the same source data could produce different output.
"""

SCHEMA_VERSION = "1.0.0"
CLEANING_VERSION = "1.0.0"
