# """
# Schema-based field completeness scorer.

# Supports two schema formats:
#   - GDPR DPIA  (dpia_schema.json)    – nested JSON Schema; required fields derived from
#                                        Art. 35(7) and EDPB WP248 guidelines.
#   - ESPR AAS   (aas_dpp_schema.json) – flat 'fields' array with per-subfield required flags.

# Scoring strategy
# ----------------
# LLM outputs are JSON (often wrapped in markdown fences) but use their own key names
# (e.g. "article_35_7_a", "Risk Assessment", "necessity_and_proportionality"), not the
# schema field IDs.  Presence is therefore detected by keyword matching against the
# flattened lowercase text of the parsed JSON — keys *and* values are included, so both
# structural keys and inline prose are searched.

# For individual runs: score(raw_response) → ScoringResult
# For grouped runs  : score_group([text, …]) → ScoringResult  (union: field counted
#                     present if it appears in ANY run of the same condition)
# """

# from __future__ import annotations

# import json
# import re
# from dataclasses import dataclass, field
# from pathlib import Path


# # ── Field definition ──────────────────────────────────────────────────────────

# @dataclass
# class FieldDef:
#     id: str
#     label: str
#     required: bool
#     keywords: list[str]   # any match in flattened output text → field present


# # ── Scoring result ────────────────────────────────────────────────────────────

# @dataclass
# class ScoringResult:
#     field_scores: dict[str, bool] = field(default_factory=dict)
#     completeness_score: float = 0.0
#     missing_required: list[str] = field(default_factory=list)
#     missing_optional: list[str] = field(default_factory=list)

#     def to_dict(self) -> dict:
#         return {
#             "field_scores":       self.field_scores,
#             "completeness_score": self.completeness_score,
#             "missing_required":   self.missing_required,
#             "missing_optional":   self.missing_optional,
#         }


# # ── DPIA field definitions ────────────────────────────────────────────────────
# # Required/optional assignments follow GDPR Art. 35(7)(a-d) and EDPB WP248.
# # Keywords are chosen to match both article-key-style outputs ("article_35_7_a",
# # "risk_assessment") and natural-language-section outputs ("Description of
# # Processing", "Risk Assessment").

# _DPIA_FIELDS: list[FieldDef] = [
#     # ── Art. 35(7)(a): Processing description ─────────────────────────────────
#     FieldDef(
#         "processing_description.nature",
#         "Nature of processing",
#         required=True,
#         keywords=["nature", "nature of processing", "how personal data", "collection",
#                   "storage", "new technolog", "processing operation"],
#     ),
#     FieldDef(
#         "processing_description.scope.data_categories",
#         "Categories of personal data",
#         required=True,
#         keywords=["data categor", "categor", "personal data", "biometric", "location",
#                   "gps", "health data", "special categor"],
#     ),
#     FieldDef(
#         "processing_description.scope.retention_period",
#         "Retention period",
#         required=True,
#         keywords=["retention", "retention period", "kept for", "stored for",
#                   "storage limit", "deleted after", "data deleted"],
#     ),
#     FieldDef(
#         "processing_description.purposes.stated_purposes",
#         "Purposes of processing",
#         required=True,
#         keywords=["purpose", "aim", "objective", "purposes of processing",
#                   "stated purpose"],
#     ),
#     FieldDef(
#         "processing_description.data_subjects.categories",
#         "Categories of data subjects",
#         required=True,
#         keywords=["data subject", "individual", "employee", "worker", "driver",
#                   "person", "data subjects"],
#     ),
#     FieldDef(
#         "processing_description.actors",
#         "Controllers, processors, and recipients",
#         required=True,
#         keywords=["controller", "processor", "recipient", "parties", "third part",
#                   "actors", "data controller"],
#     ),
#     FieldDef(
#         "processing_description.data_flows",
#         "Data flows",
#         required=False,
#         keywords=["data flow", "transfer", "collection method", "data source",
#                   "deletion mechanism"],
#     ),
#     FieldDef(
#         "dpia_record",
#         "DPIA administrative record",
#         required=False,
#         keywords=["controller name", "dpo", "version", "review schedule",
#                   "submission date", "dpia scope"],
#     ),

#     # ── Art. 35(7)(b): Necessity and proportionality ──────────────────────────
#     FieldDef(
#         "necessity_proportionality.lawful_basis",
#         "Lawful basis (Art. 6 / Art. 9)",
#         required=True,
#         keywords=["lawful basis", "legal basis", "art. 6", "article 6", "consent",
#                   "legitimate interest", "legal obligation", "public task",
#                   "lawful ground"],
#     ),
#     FieldDef(
#         "necessity_proportionality.necessity_justification",
#         "Necessity justification",
#         required=True,
#         keywords=["necessity", "necessary", "required for", "could not reasonably",
#                   "least intrusive", "no other way"],
#     ),
#     FieldDef(
#         "necessity_proportionality.proportionality_justification",
#         "Proportionality justification",
#         required=True,
#         keywords=["proportionalit", "proportionate", "reasonable proportion",
#                   "privacy impact"],
#     ),
#     FieldDef(
#         "necessity_proportionality.data_minimisation",
#         "Data minimisation",
#         required=True,
#         keywords=["minimis", "minimiz", "data minimis", "minimum data",
#                   "privacy by default", "only necessary data"],
#     ),
#     FieldDef(
#         "necessity_proportionality.storage_limitation",
#         "Storage limitation",
#         required=True,
#         keywords=["storage limitation", "retention limit", "deletion", "anonymis",
#                   "anonymiz", "data deleted when", "no longer necessar"],
#     ),
#     FieldDef(
#         "necessity_proportionality.data_subject_rights",
#         "Data subject rights (Arts. 15–22)",
#         required=True,
#         keywords=["right to access", "right of access", "rectification", "erasure",
#                   "right to erasure", "portability", "right to object",
#                   "restrict processing", "data subject right"],
#     ),
#     FieldDef(
#         "necessity_proportionality.transparency",
#         "Transparency / privacy notice",
#         required=False,
#         keywords=["privacy notice", "transparent", "transparency", "informed",
#                   "privacy information", "art. 13", "art. 14"],
#     ),
#     FieldDef(
#         "necessity_proportionality.purpose_limitation",
#         "Purpose limitation",
#         required=False,
#         keywords=["purpose limitation", "function creep", "secondary purpose",
#                   "compatible purpose", "art. 5(1)(b)"],
#     ),
#     FieldDef(
#         "necessity_proportionality.alternatives_considered",
#         "Less privacy-intrusive alternatives considered",
#         required=False,
#         keywords=["alternative", "less intrusive", "other option",
#                   "alternatives considered"],
#     ),

#     # ── Art. 35(7)(c): Risk assessment ────────────────────────────────────────
#     FieldDef(
#         "risk_assessment.identified_risks",
#         "Identified risks to rights and freedoms",
#         required=True,
#         keywords=["identified risk", "risk", "threat", "vulnerability",
#                   "rights and freedom"],
#     ),
#     FieldDef(
#         "risk_assessment.risk_likelihood",
#         "Risk likelihood",
#         required=True,
#         keywords=["likelihood", "probable", "possible", "remote",
#                   "likelihood of", "probability"],
#     ),
#     FieldDef(
#         "risk_assessment.risk_severity",
#         "Risk severity / impact",
#         required=True,
#         keywords=["severity", "impact", "severe", "significant", "minimal",
#                   "severity of", "impact on"],
#     ),
#     FieldDef(
#         "risk_assessment.residual_risk",
#         "Residual risk after mitigation",
#         required=True,
#         keywords=["residual", "residual risk", "remaining risk",
#                   "after mitigation", "after measure"],
#     ),

#     # ── Art. 35(7)(d): Risk mitigation ────────────────────────────────────────
#     FieldDef(
#         "risk_mitigation.technical_measures",
#         "Technical security measures",
#         required=True,
#         keywords=["technical measure", "technical security", "encryption",
#                   "access control", "pseudonym", "anonymis", "anonymiz",
#                   "security measure"],
#     ),
#     FieldDef(
#         "risk_mitigation.organisational_measures",
#         "Organisational measures",
#         required=True,
#         keywords=["organisational", "organizational", "staff training", "training",
#                   "internal polic", "data processing agreement", "procedure"],
#     ),
#     FieldDef(
#         "risk_mitigation.compliance_mechanisms",
#         "Mechanisms to demonstrate GDPR compliance",
#         required=True,
#         keywords=["compliance mechanism", "demonstrate compliance", "ongoing compliance",
#                   "gdpr compliance", "compliance with gdpr"],
#     ),
#     FieldDef(
#         "risk_mitigation.consultation.dpo",
#         "DPO consultation",
#         required=False,
#         keywords=["dpo consult", "data protection officer consult",
#                   "dpo advice", "dpo review"],
#     ),
#     FieldDef(
#         "risk_mitigation.consultation.data_subjects",
#         "Data subject consultation (Art. 35(9))",
#         required=False,
#         keywords=["consult data subject", "views of data subject",
#                   "data subject consult", "representative consult",
#                   "art. 35(9)"],
#     ),
#     FieldDef(
#         "risk_mitigation.consultation.supervisory_authority",
#         "Supervisory authority consultation (Art. 36)",
#         required=False,
#         keywords=["supervisory authority", "prior consultation", "art. 36",
#                   "article 36", "dpa consult"],
#     ),
#     FieldDef(
#         "risk_mitigation.review_and_sign_off",
#         "Review and sign-off",
#         required=False,
#         keywords=["sign off", "sign-off", "approved by", "review schedule",
#                   "annual review", "approval"],
#     ),
# ]


# # ── Scorer ────────────────────────────────────────────────────────────────────

# class SchemaScorer:
#     def __init__(self, schema_path: str | Path):
#         with open(schema_path, encoding="utf-8") as fh:
#             self.schema = json.load(fh)
#         self._fields: list[FieldDef] = self._flatten_fields()

#     # ── Public API ─────────────────────────────────────────────────────────────

#     def score(self, raw_response: str) -> ScoringResult:
#         """Score a single raw LLM response against the schema."""
#         text = self._to_searchable_text(raw_response)
#         return self._compute_result(
#             {f.id: any(kw in text for kw in f.keywords) for f in self._fields}
#         )

#     def score_group(self, raw_responses: list[str]) -> ScoringResult:
#         """
#         Score the union of multiple runs of the same condition.
#         A field is counted as present if it appears in ANY run — this gives the
#         'combined completeness' figure described in the paper.
#         """
#         if not raw_responses:
#             raise ValueError("raw_responses must not be empty")
#         per_run = [self.score(r) for r in raw_responses]
#         union_scores = {
#             f.id: any(r.field_scores.get(f.id, False) for r in per_run)
#             for f in self._fields
#         }
#         return self._compute_result(union_scores)

#     # ── Internal ───────────────────────────────────────────────────────────────

#     def _compute_result(self, field_scores: dict[str, bool]) -> ScoringResult:
#         required  = [f for f in self._fields if f.required]
#         optional  = [f for f in self._fields if not f.required]
#         miss_req  = [f.id for f in required if not field_scores[f.id]]
#         miss_opt  = [f.id for f in optional if not field_scores[f.id]]
#         score     = (len(required) - len(miss_req)) / len(required) if required else 0.0
#         return ScoringResult(
#             field_scores=field_scores,
#             completeness_score=round(score, 4),
#             missing_required=miss_req,
#             missing_optional=miss_opt,
#         )

#     def _to_searchable_text(self, raw_response: str) -> str:
#         """
#         Strip markdown fences, parse JSON (falling back to raw text), and return
#         a single lowercase string containing all keys and values.
#         """
#         stripped = re.sub(r"```[a-zA-Z]*\n?", "", raw_response).strip()
#         stripped = re.sub(r"```\s*$", "", stripped).strip()
#         try:
#             parsed = json.loads(stripped)
#             return json.dumps(parsed, ensure_ascii=False).lower()
#         except (json.JSONDecodeError, ValueError):
#             return raw_response.lower()

#     def _flatten_fields(self) -> list[FieldDef]:
#         if "fields" in self.schema:
#             return self._flatten_aas()
#         return list(_DPIA_FIELDS)

#     def _flatten_aas(self) -> list[FieldDef]:
#         """Build FieldDef list from the flat AAS schema format."""
#         result: list[FieldDef] = []
#         for section in self.schema["fields"]:
#             for sf in section.get("subfields", []):
#                 label = sf["label"]
#                 # Derive keywords from the label (words > 3 chars) plus common synonyms
#                 raw_words = re.sub(r"[/()\[\]]", " ", label).lower().split()
#                 keywords  = [w for w in raw_words if len(w) > 3]
#                 result.append(FieldDef(
#                     id=sf["id"],
#                     label=label,
#                     required=sf.get("required", False),
#                     keywords=keywords,
#                 ))
#         return result

#New
"""
Schema-based field completeness scorer.

Supports two schema formats:
  - GDPR DPIA  (dpia_schema.json)    – nested JSON Schema; required fields derived from
                                       Art. 35(7) and EDPB WP248 guidelines.
  - ESPR AAS   (aas_dpp_schema.json) – flat 'fields' array with per-subfield required flags.

Scoring strategy
----------------
LLM outputs are JSON (often wrapped in markdown fences) but use their own key names
(e.g. "article_35_7_a", "Risk Assessment", "necessity_and_proportionality"), not the
schema field IDs. Presence is therefore detected by keyword matching against the
flattened lowercase text of the parsed JSON — keys *and* values are included, so both
structural keys and inline prose are searched.

For individual runs: score(raw_response) → ScoringResult
For grouped runs  : score_group([text, …]) → ScoringResult  (union: field counted
                    present if it appears in ANY run of the same condition)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Field definition ──────────────────────────────────────────────────────────

@dataclass
class FieldDef:
    id: str
    label: str
    required: bool
    keywords: list[str]   # any match in flattened output text → field present


# ── Scoring result ────────────────────────────────────────────────────────────

@dataclass
class ScoringResult:
    field_scores: dict[str, bool] = field(default_factory=dict)
    completeness_score: float = 0.0
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field_scores":       self.field_scores,
            "completeness_score": self.completeness_score,
            "missing_required":   self.missing_required,
            "missing_optional":   self.missing_optional,
        }


# ── DPIA field definitions ────────────────────────────────────────────────────
# Required/optional assignments follow GDPR Art. 35(7)(a-d) and EDPB WP248.
# Keywords are chosen to match both article-key-style outputs ("article_35_7_a",
# "risk_assessment") and natural-language-section outputs ("Description of
# Processing", "Risk Assessment").

_DPIA_FIELDS: list[FieldDef] = [
    # ── Art. 35(7)(a): Processing description ─────────────────────────────────
    FieldDef(
        "processing_description.nature",
        "Nature of processing",
        required=True,
        keywords=["nature", "nature of processing", "how personal data", "collection",
                  "storage", "new technolog", "processing operation"],
    ),
    FieldDef(
        "processing_description.scope.data_categories",
        "Categories of personal data",
        required=True,
        keywords=["data categor", "categor", "personal data", "biometric", "location",
                  "gps", "health data", "special categor"],
    ),
    FieldDef(
        "processing_description.scope.retention_period",
        "Retention period",
        required=True,
        keywords=["retention", "retention period", "kept for", "stored for",
                  "storage limit", "deleted after", "data deleted"],
    ),
    FieldDef(
        "processing_description.purposes.stated_purposes",
        "Purposes of processing",
        required=True,
        keywords=["purpose", "aim", "objective", "purposes of processing",
                  "stated purpose"],
    ),
    FieldDef(
        "processing_description.data_subjects.categories",
        "Categories of data subjects",
        required=True,
        keywords=["data subject", "individual", "employee", "worker", "driver",
                  "person", "data subjects"],
    ),
    FieldDef(
        "processing_description.actors",
        "Controllers, processors, and recipients",
        required=True,
        keywords=["controller", "processor", "recipient", "parties", "third part",
                  "actors", "data controller"],
    ),
    FieldDef(
        "processing_description.data_flows",
        "Data flows",
        required=False,
        keywords=["data flow", "transfer", "collection method", "data source",
                  "deletion mechanism"],
    ),
    FieldDef(
        "dpia_record",
        "DPIA administrative record",
        required=False,
        keywords=["controller name", "dpo", "version", "review schedule",
                  "submission date", "dpia scope"],
    ),

    # ── Art. 35(7)(b): Necessity and proportionality ──────────────────────────
    FieldDef(
        "necessity_proportionality.lawful_basis",
        "Lawful basis (Art. 6 / Art. 9)",
        required=True,
        keywords=["lawful basis", "legal basis", "art. 6", "article 6", "consent",
                  "legitimate interest", "legal obligation", "public task",
                  "lawful ground"],
    ),
    FieldDef(
        "necessity_proportionality.necessity_justification",
        "Necessity justification",
        required=True,
        keywords=["necessity", "necessary", "required for", "could not reasonably",
                  "least intrusive", "no other way"],
    ),
    FieldDef(
        "necessity_proportionality.proportionality_justification",
        "Proportionality justification",
        required=True,
        keywords=["proportionalit", "proportionate", "reasonable proportion",
                  "privacy impact"],
    ),
    FieldDef(
        "necessity_proportionality.data_minimisation",
        "Data minimisation",
        required=True,
        keywords=["minimis", "minimiz", "data minimis", "minimum data",
                  "privacy by default", "only necessary data"],
    ),
    FieldDef(
        "necessity_proportionality.storage_limitation",
        "Storage limitation",
        required=True,
        keywords=["storage limitation", "retention limit", "deletion", "anonymis",
                  "anonymiz", "data deleted when", "no longer necessar"],
    ),
    FieldDef(
        "necessity_proportionality.data_subject_rights",
        "Data subject rights (Arts. 15–22)",
        required=True,
        keywords=["right to access", "right of access", "rectification", "erasure",
                  "right to erasure", "portability", "right to object",
                  "restrict processing", "data subject right"],
    ),
    FieldDef(
        "necessity_proportionality.transparency",
        "Transparency / privacy notice",
        required=False,
        keywords=["privacy notice", "transparent", "transparency", "informed",
                  "privacy information", "art. 13", "art. 14"],
    ),
    FieldDef(
        "necessity_proportionality.purpose_limitation",
        "Purpose limitation",
        required=False,
        keywords=["purpose limitation", "function creep", "secondary purpose",
                  "compatible purpose", "art. 5(1)(b)"],
    ),
    FieldDef(
        "necessity_proportionality.alternatives_considered",
        "Less privacy-intrusive alternatives considered",
        required=False,
        keywords=["alternative", "less intrusive", "other option",
                  "alternatives considered"],
    ),

    # ── Art. 35(7)(c): Risk assessment ────────────────────────────────────────
    FieldDef(
        "risk_assessment.identified_risks",
        "Identified risks to rights and freedoms",
        required=True,
        keywords=["identified risk", "risk", "threat", "vulnerability",
                  "rights and freedom"],
    ),
    FieldDef(
        "risk_assessment.risk_likelihood",
        "Risk likelihood",
        required=True,
        keywords=["likelihood", "probable", "possible", "remote",
                  "likelihood of", "probability"],
    ),
    FieldDef(
        "risk_assessment.risk_severity",
        "Risk severity / impact",
        required=True,
        keywords=["severity", "impact", "severe", "significant", "minimal",
                  "severity of", "impact on"],
    ),
    FieldDef(
        "risk_assessment.residual_risk",
        "Residual risk after mitigation",
        required=True,
        keywords=["residual", "residual risk", "remaining risk",
                  "after mitigation", "after measure"],
    ),

    # ── Art. 35(7)(d): Risk mitigation ────────────────────────────────────────
    FieldDef(
        "risk_mitigation.technical_measures",
        "Technical security measures",
        required=True,
        keywords=["technical measure", "technical security", "encryption",
                  "access control", "pseudonym", "anonymis", "anonymiz",
                  "security measure"],
    ),
    FieldDef(
        "risk_mitigation.organisational_measures",
        "Organisational measures",
        required=True,
        keywords=["organisational", "organizational", "staff training", "training",
                  "internal polic", "data processing agreement", "procedure"],
    ),
    FieldDef(
        "risk_mitigation.compliance_mechanisms",
        "Mechanisms to demonstrate GDPR compliance",
        required=True,
        keywords=["compliance mechanism", "demonstrate compliance", "ongoing compliance",
                  "gdpr compliance", "compliance with gdpr"],
    ),
    FieldDef(
        "risk_mitigation.consultation.dpo",
        "DPO consultation",
        required=False,
        keywords=["dpo consult", "data protection officer consult",
                  "dpo advice", "dpo review"],
    ),
    FieldDef(
        "risk_mitigation.consultation.data_subjects",
        "Data subject consultation (Art. 35(9))",
        required=False,
        keywords=["consult data subject", "views of data subject",
                  "data subject consult", "representative consult",
                  "art. 35(9)"],
    ),
    FieldDef(
        "risk_mitigation.consultation.supervisory_authority",
        "Supervisory authority consultation (Art. 36)",
        required=False,
        keywords=["supervisory authority", "prior consultation", "art. 36",
                  "article 36", "dpa consult"],
    ),
    FieldDef(
        "risk_mitigation.review_and_sign_off",
        "Review and sign-off",
        required=False,
        keywords=["sign off", "sign-off", "approved by", "review schedule",
                  "annual review", "approval"],
    ),
]


# ── Scorer ────────────────────────────────────────────────────────────────────

class SchemaScorer:
    def __init__(self, schema_path: str | Path):
        with open(schema_path, encoding="utf-8") as fh:
            self.schema = json.load(fh)
        self._fields: list[FieldDef] = self._flatten_fields()

    # ── Public API ─────────────────────────────────────────────────────────────

    def score(self, raw_response: str) -> ScoringResult:
        """Score a single raw LLM response against the schema."""
        text = self._to_searchable_text(raw_response)
        return self._compute_result(
            {f.id: any(kw in text for kw in f.keywords) for f in self._fields}
        )

    def score_group(self, raw_responses: list[str]) -> ScoringResult:
        """
        Score the union of multiple runs of the same condition.
        A field is counted as present if it appears in ANY run — this gives the
        'combined completeness' figure described in the paper.
        """
        if not raw_responses:
            raise ValueError("raw_responses must not be empty")

        per_run = [self.score(r) for r in raw_responses]

        union_scores = {
            f.id: any(r.field_scores.get(f.id, False) for r in per_run)
            for f in self._fields
        }

        return self._compute_result(union_scores)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _compute_result(self, field_scores: dict[str, bool]) -> ScoringResult:
        required = [f for f in self._fields if f.required]
        optional = [f for f in self._fields if not f.required]

        miss_req = [f.id for f in required if not field_scores[f.id]]
        miss_opt = [f.id for f in optional if not field_scores[f.id]]

        score = (
            (len(required) - len(miss_req)) / len(required)
            if required else 0.0
        )

        return ScoringResult(
            field_scores=field_scores,
            completeness_score=round(score, 4),
            missing_required=miss_req,
            missing_optional=miss_opt,
        )

    def _to_searchable_text(self, raw_response: str) -> str:
        """
        Strip markdown fences, parse JSON (falling back to raw text), and return
        a single lowercase string containing all keys and values.
        """
        stripped = re.sub(r"```[a-zA-Z]*\n?", "", raw_response).strip()
        stripped = re.sub(r"```\s*$", "", stripped).strip()

        try:
            parsed = json.loads(stripped)
            return json.dumps(parsed, ensure_ascii=False).lower()

        except (json.JSONDecodeError, ValueError):
            return raw_response.lower()

    def _flatten_fields(self) -> list[FieldDef]:
        if "fields" in self.schema:
            return self._flatten_aas()

        if "submodels" in self.schema:
            return self._flatten_idta()

        return list(_DPIA_FIELDS)

    def _flatten_aas(self) -> list[FieldDef]:
        """Build FieldDef list from the flat AAS schema format."""
        result: list[FieldDef] = []

        for section in self.schema["fields"]:
            for sf in section.get("subfields", []):

                label = sf["label"]

                # Derive keywords from the label (words > 3 chars)
                raw_words = re.sub(r"[/()\[\]]", " ", label).lower().split()
                keywords = [w for w in raw_words if len(w) > 3]

                result.append(
                    FieldDef(
                        id=sf["id"],
                        label=label,
                        required=sf.get("required", False),
                        keywords=keywords,
                    )
                )

        return result

    def _flatten_idta(self) -> list[FieldDef]:
        """Build FieldDef list from the native IDTA AAS submodel format."""
        result: list[FieldDef] = []

        for submodel in self.schema.get("submodels", []):
            for elem in submodel.get("submodelElements", []):
                self._walk_idta_elem(elem, prefix="", result=result)

        return result

    def _walk_idta_elem(
        self,
        elem: dict,
        prefix: str,
        result: list,
        ctx_keywords: list[str] | None = None,
    ) -> None:

        id_short = elem.get("idShort", "unknown")
        path_id = (prefix + "." + id_short.lower()).lstrip(".")
        label = self._idta_label(elem)
        required = self._idta_required(elem)
        mtype = elem.get("modelType", "")

        ctx_keywords = ctx_keywords or []

        if mtype == "Property":

            keywords = list(ctx_keywords)

            for kw in self._label_to_keywords(label):
                if kw not in keywords:
                    keywords.append(kw)

            # Add CamelCase idShort words
            for kw in re.sub(
                r"(?<=[a-z])(?=[A-Z])",
                " ",
                id_short
            ).lower().split():

                if len(kw) > 3 and kw not in keywords:
                    keywords.append(kw)

            result.append(
                FieldDef(
                    id=path_id,
                    label=label,
                    required=required,
                    keywords=keywords,
                )
            )

        else:
            # Accumulate section context so children get richer keywords
            section_kws = list(ctx_keywords)

            for kw in self._label_to_keywords(label):
                if kw not in section_kws:
                    section_kws.append(kw)

            for child in elem.get("value", []):
                self._walk_idta_elem(
                    child,
                    prefix=path_id,
                    result=result,
                    ctx_keywords=section_kws,
                )

    @staticmethod
    def _idta_label(elem: dict) -> str:
        names = elem.get("displayName", [])

        if names:
            return names[0].get("text", elem.get("idShort", ""))

        return elem.get("idShort", "")

    @staticmethod
    def _idta_required(elem: dict) -> bool:
        for q in elem.get("qualifiers", []):

            if q.get("type") == "SMT/Cardinality":
                return q.get("value", "") in ("One", "OneToMany")

        return False

    @staticmethod
    def _label_to_keywords(label: str) -> list[str]:
        raw = re.sub(r"[/()\[\]]", " ", label).lower().split()
        return [w for w in raw if len(w) > 3]


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    scorer = SchemaScorer("dpia_schema.json")

    sample_response = """
    {
        "risk_assessment": {
            "identified_risks": "Unauthorized access to personal data",
            "risk_likelihood": "Medium",
            "risk_severity": "High"
        }
    }
    """

    result = scorer.score(sample_response)

    print(json.dumps(result.to_dict(), indent=2))