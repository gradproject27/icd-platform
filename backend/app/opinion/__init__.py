"""LLM opinion (AI1, risk-v1 step 4): a calibrated "is this a real attack?" per evidence group.

Feeds C3's event confidence C (design note section 9A.2, step 3; decision RV1-D2). It is not the
AI report and not the report confidence (OD-16): the two are never combined. See
docs/ai1-llm-opinion.md.
"""

from app.opinion.calibration import Calibrator, fit_platt
from app.opinion.client import OpinionClient, StubOpinionClient, client_from_env
from app.opinion.estimate import OpinionSettings, estimate, estimate_incident
from app.opinion.groups import OpinionGroup, incident_groups, labelled_groups
from app.opinion.models import OPINION_FORMAT, GroupOpinion

__all__ = [
    "OPINION_FORMAT",
    "Calibrator",
    "GroupOpinion",
    "OpinionClient",
    "OpinionGroup",
    "OpinionSettings",
    "StubOpinionClient",
    "client_from_env",
    "estimate",
    "estimate_incident",
    "fit_platt",
    "incident_groups",
    "labelled_groups",
]
