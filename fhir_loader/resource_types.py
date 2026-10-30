"""Resource types handled by Metriport's fhir-to-csv step.

These are the base resource types of the config files in
packages/data-transformation/fhir-to-csv/src/parseFhir/configurations/ at commit e1f26d5
(33 config files, 28 base types). parseNdjsonBundle.py makes one full pass over the input
file for each base type.
"""

RESOURCE_TYPES: tuple[str, ...] = (
    "AllergyIntolerance",
    "Binary",
    "CarePlan",
    "Communication",
    "Composition",
    "Condition",
    "Consent",
    "Coverage",
    "Device",
    "DiagnosticReport",
    "DocumentReference",
    "Encounter",
    "FamilyMemberHistory",
    "Goal",
    "Immunization",
    "Location",
    "Medication",
    "MedicationAdministration",
    "MedicationDispense",
    "MedicationRequest",
    "MedicationStatement",
    "Observation",
    "Organization",
    "Patient",
    "Practitioner",
    "Procedure",
    "Provenance",
    "ServiceRequest",
)

# The tables this project materializes.
TABLES: tuple[str, ...] = ("Patient", "Condition", "Encounter")
