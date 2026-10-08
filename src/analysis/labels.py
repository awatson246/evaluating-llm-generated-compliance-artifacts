"""
Display names shared by the tables (export_tables.py) and figures (plot_results.py),
so a model or field is labelled identically everywhere.
"""

from __future__ import annotations

# Keyed by the model_id recorded in each run (config.yaml models[].model_id).
MODEL_LABELS: dict[str, str] = {
    "gpt-4o":                           "GPT-4o",
    "claude-sonnet-4-6":                "Claude Sonnet 4.6",
    "meta-llama/Llama-3.1-8B-Instruct": "Llama 3.1 8B",
    "ministral-8b-2512":                "Ministral 8B",
    "Qwen/Qwen2.5-7B-Instruct":         "Qwen 2.5 7B",
}

# Keyed by the field IDs the schema scorer emits.
FIELD_LABELS: dict[str, str] = {
    # GDPR / DPIA (Art. 35(7))
    "dpia_record":                                             "DPIA record",
    "processing_description.nature":                           "Nature of processing",
    "processing_description.scope.data_categories":            "Data categories",
    "processing_description.scope.retention_period":           "Retention period",
    "processing_description.purposes.stated_purposes":         "Processing purposes",
    "processing_description.data_subjects.categories":         "Data subject categories",
    "processing_description.actors":                           "Controllers & processors",
    "processing_description.data_flows":                       "Data flows",
    "necessity_proportionality.lawful_basis":                  "Lawful basis (Art. 6)",
    "necessity_proportionality.necessity_justification":       "Necessity justification",
    "necessity_proportionality.proportionality_justification": "Proportionality",
    "necessity_proportionality.alternatives_considered":       "Alternatives considered",
    "necessity_proportionality.purpose_limitation":            "Purpose limitation",
    "necessity_proportionality.data_minimisation":             "Data minimisation",
    "necessity_proportionality.storage_limitation":            "Storage limitation",
    "necessity_proportionality.transparency":                  "Transparency",
    "necessity_proportionality.data_subject_rights":           "Data subject rights",
    "risk_assessment.identified_risks":                        "Identified risks",
    "risk_assessment.risk_likelihood":                         "Risk likelihood",
    "risk_assessment.risk_severity":                           "Risk severity",
    "risk_assessment.residual_risk":                           "Residual risk",
    "risk_mitigation.technical_measures":                      "Technical measures",
    "risk_mitigation.organisational_measures":                 "Organisational measures",
    "risk_mitigation.compliance_mechanisms":                   "Compliance mechanisms",
    "risk_mitigation.consultation.dpo":                        "DPO consultation",
    "risk_mitigation.consultation.data_subjects":              "Data subject consultation",
    "risk_mitigation.consultation.supervisory_authority":      "Supervisory authority consultation",
    "risk_mitigation.review_and_sign_off":                     "Review & sign-off",
    # ESPR / DBP Material Composition submodel (IDTA 02035-6)
    "batterychemistry.shortname":                              "Battery chemistry (short name)",
    "batterychemistry.clearname":                              "Battery chemistry (full name)",
    "batterymaterials.batterymaterial.batterymaterialname":       "Material name",
    "batterymaterials.batterymaterial.batterymaterialidentifier": "Material identifier",
    "batterymaterials.batterymaterial.batterymaterialmass":       "Material mass",
    "batterymaterials.batterymaterial.iscriticalrawmaterial":     "Critical raw material",
    "batterymaterials.batterymaterial.batterymateriallocation.componentname": "Material location (component name)",
    "batterymaterials.batterymaterial.batterymateriallocation.componentid":   "Material location (component ID)",
    "hazardoussubstances.hazardoussubstance.hazardoussubstancename":          "Hazardous substance name",
    "hazardoussubstances.hazardoussubstance.hazardoussubstanceidentifier":    "Hazardous substance identifier",
    "hazardoussubstances.hazardoussubstance.hazardoussubstanceclass":         "Hazardous substance class",
    "hazardoussubstances.hazardoussubstance.hazardoussubstanceconcentration": "Hazardous substance concentration",
    "hazardoussubstances.hazardoussubstance.hazardoussubstanceimpact.impact": "Hazardous substance impact",
    "hazardoussubstances.hazardoussubstance.hazardoussubstancelocation.componentname": "Hazardous substance location (component name)",
    "hazardoussubstances.hazardoussubstance.hazardoussubstancelocation.componentid":   "Hazardous substance location (component ID)",
}

_LATEX_ESCAPES = {"&": r"\&", "%": r"\%"}


def model_label(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id.split("/")[-1])


def field_label(field_id: str, latex: bool = False) -> str:
    label = FIELD_LABELS.get(field_id, field_id.split(".")[-1].replace("_", " ").title())
    if latex:
        for ch, esc in _LATEX_ESCAPES.items():
            label = label.replace(ch, esc)
    return label
