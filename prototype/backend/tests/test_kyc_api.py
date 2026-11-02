import pytest
from fastapi.testclient import TestClient

from app.config import KYC_DOCS_DIR
from app.kyc_routes import CONSENT_NOTICE_VERSION, RETENTION, _applications
from app.main import app

client = TestClient(app)


def new_application(**applicant) -> str:
    response = client.post("/api/kyc/applications", json={
        "consent_accepted": True,
        "notice_version": CONSENT_NOTICE_VERSION,
        "applicant": applicant,
    })
    assert response.status_code == 201
    return response.json()["application_id"]


def test_consent_notice_covers_purpose_data_retention_and_rights():
    notice = client.get("/api/kyc/consent-notice").json()
    assert notice["version"] == CONSENT_NOTICE_VERSION
    assert {"purpose", "data", "processing", "retention", "rights"} <= notice.keys()


def test_no_consent_means_no_application():
    response = client.post("/api/kyc/applications", json={"consent_accepted": False, "notice_version": CONSENT_NOTICE_VERSION})
    assert response.status_code == 403


def test_consent_to_an_old_notice_is_refused():
    response = client.post("/api/kyc/applications", json={"consent_accepted": True, "notice_version": "old"})
    assert response.status_code == 409


def test_documents_cannot_be_uploaded_to_an_unknown_application():
    response = client.post("/api/kyc/applications/nope/documents", data={"slot": "gst"}, files={"file": ("a.png", b"x", "image/png")})
    assert response.status_code == 404


def test_non_images_are_refused():
    application_id = new_application()
    response = client.post(f"/api/kyc/applications/{application_id}/documents", data={"slot": "gst"}, files={"file": ("a.pdf", b"x", "application/pdf")})
    assert response.status_code == 415


def test_unknown_slot_is_refused():
    application_id = new_application()
    response = client.post(f"/api/kyc/applications/{application_id}/documents", data={"slot": "passport"}, files={"file": ("a.png", b"x", "image/png")})
    assert response.status_code == 422


def test_erasing_an_application_removes_everything():
    application_id = new_application()
    assert client.delete(f"/api/kyc/applications/{application_id}").status_code == 204
    assert client.post(f"/api/kyc/applications/{application_id}/submit").status_code == 404


def test_expired_applications_are_purged():
    application_id = new_application()
    _applications[application_id].consent_at -= RETENTION * 2
    assert client.post(f"/api/kyc/applications/{application_id}/submit").status_code == 404


def test_sample_ids_cannot_reach_other_files():
    application_id = new_application()
    response = client.post(f"/api/kyc/applications/{application_id}/load-sample", json={"sample_id": "../secrets"})
    assert response.status_code == 404


def test_samples_list_does_not_reveal_expected_verdicts():
    samples = client.get("/api/kyc/samples").json()
    assert len(samples) == 12
    assert set(samples[0]) == {"id", "business"}


@pytest.mark.slow
def test_real_upload_shows_masked_identifiers_and_keeps_no_image():
    application_id = new_application(contact_name="Joseph Singh", gstin_on_file="27XUIXG0767D1ZP", udyam_on_file="UDYAM-MH-00-9516696")
    with (KYC_DOCS_DIR / "K03_gst_certificate.png").open("rb") as f:
        response = client.post(f"/api/kyc/applications/{application_id}/documents", data={"slot": "gst"}, files={"file": ("gst.png", f, "image/png")})
    body = response.json()
    assert response.status_code == 200
    assert body["readable"]
    assert body["fields"]["gstin"] == "27**********1ZP"
    assert body["fields"]["trade_name"] == "Ganesh Woodcraft"
    stored = _applications[application_id].documents["gst"]
    assert not hasattr(stored, "image") and not hasattr(stored, "data")


@pytest.mark.slow
def test_sample_journey_catches_the_altered_gstin():
    application_id = new_application()
    documents = client.post(f"/api/kyc/applications/{application_id}/load-sample", json={"sample_id": "K06"}).json()
    assert len(documents) == 4
    result = client.post(f"/api/kyc/applications/{application_id}/submit").json()
    assert result["verdict"] == "MANUAL_REVIEW"
    assert "GSTIN_INVALID" in {check["code"] for check in result["checks"]}
    assert result["verified_fields"] == {}


@pytest.mark.slow
def test_sample_journey_for_a_clean_applicant_returns_verified_fields():
    application_id = new_application()
    client.post(f"/api/kyc/applications/{application_id}/load-sample", json={"sample_id": "K03"})
    result = client.post(f"/api/kyc/applications/{application_id}/submit").json()
    assert result["verdict"] == "PASS"
    assert result["verified_fields"]["constitution"] == "Proprietorship"
