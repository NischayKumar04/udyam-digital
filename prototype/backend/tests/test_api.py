from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_catalogue_lists_25_products():
    products = client.get("/api/catalogue").json()
    assert len(products) == 25
    assert products[0]["id"] == "P01"
    assert products[0]["city_tiers"] == [1, 2]


def test_gstin_lookup_active():
    body = client.post("/api/lookup/gstin", json={"gstin": "27XUIXG0767D1ZP"}).json()
    assert body["found"] and body["active"]
    assert body["trade_name"] == "Ganesh Woodcraft"


def test_gstin_lookup_cancelled():
    body = client.post("/api/lookup/gstin", json={"gstin": "37IHKXV5167L1ZS"}).json()
    assert body["found"] and not body["active"]
    assert body["status"] == "Cancelled"


def test_gstin_lookup_altered_number_explains_itself():
    body = client.post("/api/lookup/gstin", json={"gstin": "08YKZXS8189L1ZO"}).json()
    assert not body["valid"]
    assert "checksum" in body["errors"][0]


def test_lookup_rejects_get_so_identifiers_stay_out_of_urls():
    assert client.get("/api/lookup/gstin?gstin=27XUIXG0767D1ZP").status_code == 405


def test_udyam_lookup():
    body = client.post("/api/lookup/udyam", json={"udyam_number": "udyam-kl-00-5521886"}).json()
    assert body["found"]
    assert body["enterprise_name"] == "Balaji Realty LLP"
    assert client.post("/api/lookup/udyam", json={"udyam_number": "nonsense"}).json() == {"valid": False, "found": False}
    assert client.post("/api/lookup/udyam", json={"udyam_number": "UDYAM-KL-00-0000000"}).json()["found"] is False


def test_recommend_then_toggle_an_add_on_through_the_quote_endpoint():
    profile = {"business_type": "Kirana store", "city": "Nagpur", "employee_count": 2}
    rec = client.post("/api/recommend", json={"profile": profile}).json()
    assert rec["quote"]["monthly_subtotal"] == 1423

    lines = [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in rec["bundle"]]
    addon = next(item for item in rec["addons"] if item["product_id"] == "P19")
    quote = client.post("/api/quote", json={
        "profile": profile,
        "lines": lines + [{"product_id": addon["product_id"], "quantity": addon["quantity"]}],
    }).json()
    assert quote["valid"]
    assert quote["monthly_subtotal"] > 1423
    assert quote["one_time_setup"] == 2500


def test_removing_the_connection_flags_what_depends_on_it():
    profile = {"business_type": "Salon", "city": "Delhi", "employee_count": 3}
    quote = client.post("/api/quote", json={"profile": profile, "lines": [{"product_id": "P23", "quantity": 2}]}).json()
    assert not quote["valid"]
    assert quote["violations"][0]["code"] == "MISSING_BASE_PRODUCT"


def test_unknown_product_in_a_quote_is_a_client_error():
    profile = {"employee_count": 2, "city_tier": 1}
    response = client.post("/api/quote", json={"profile": profile, "lines": [{"product_id": "P99", "quantity": 1}]})
    assert response.status_code == 422


def test_bad_input_is_rejected():
    assert client.post("/api/recommend", json={"profile": {"employee_count": 0}}).status_code == 422
    assert client.post("/api/recommend", json={"profile": {"employee_count": 2}, "needs": ["telepathy"]}).status_code == 422
