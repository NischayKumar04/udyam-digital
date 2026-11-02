"""Paths and fixed assumptions shared across the backend."""
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE_CSV = REPO_ROOT / "product_catalogue.csv"
LEADS_CSV = REPO_ROOT / "smb_leads.csv"
GSTIN_REGISTRY_CSV = REPO_ROOT / "mock_gstin_registry.csv"
UDYAM_REGISTRY_CSV = REPO_ROOT / "mock_udyam_registry.csv"
KYC_DOCS_DIR = REPO_ROOT / "kyc_documents"

# The data pack's README fixes "today" for every date-based check.
TODAY = date(2026, 7, 15)
ADDRESS_PROOF_MAX_AGE_DAYS = 90

# Assumption: catalogue prices exclude GST, which is 18% on telecom services.
GST_RATE = 0.18
