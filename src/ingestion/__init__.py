"""
Controlled Ground-Truth Ingestion Adapters & Pipeline (Milestone 8 — Phase 4)
"""
from src.ingestion.adapters import (
    AdapterValidationError,
    AuthorizedBrokerFeedAdapter,
    BaseSourceAdapter,
    GovtBMVReferenceAdapter,
    NormalizedIngestionItem,
    ORERAProjectDisclosureAdapter,
    UserDocumentEvidenceAdapter,
)
from src.ingestion.pipeline import ControlledIngestionPipeline

__all__ = [
    "AdapterValidationError",
    "AuthorizedBrokerFeedAdapter",
    "BaseSourceAdapter",
    "ControlledIngestionPipeline",
    "GovtBMVReferenceAdapter",
    "NormalizedIngestionItem",
    "ORERAProjectDisclosureAdapter",
    "UserDocumentEvidenceAdapter",
]
