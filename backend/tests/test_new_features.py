"""Backend tests for new features: Defect Spotlight (bbox+confidence), PDF snapshot,
Confidence badges, Manual Regroup. Reuses existing DONE inspections to avoid extra LLM cost."""
import os
import io
import time
import pytest
import requests
from pathlib import Path
from openpyxl import load_workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or next(
    (ln.split("=", 1)[1].strip() for ln in Path("/app/frontend/.env").read_text().splitlines()
     if ln.startswith("REACT_APP_BACKEND_URL=")), None
)
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

EMAIL = "inspector@indigo.com"
PASSWORD = "inspect123"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def done_inspection(auth_headers):
    """Pick a DONE inspection with a pdf_path."""
    r = requests.get(f"{API}/inspections", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    done = [i for i in r.json() if i.get("status") == "done" and i.get("pdf_path")]
    assert done, "need at least one done inspection with pdf_path"
    # prefer the one with 1 product so we can regroup it
    done.sort(key=lambda x: x.get("product_count", 99))
    return done[0]


class TestConfidenceAndDefects:
    def test_products_have_confidence_and_defect_bbox(self, done_inspection, auth_headers):
        r = requests.get(f"{API}/inspections/{done_inspection['id']}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        full = r.json()
        assert full.get("pdf_path"), "pdf_path missing on done inspection"
        assert full["products"], "no products"
        for prod in full["products"]:
            conf = prod.get("confidence") or {}
            # must have at least overall + sku + grouping confidence levels
            for key in ("sku", "visible_unit_count", "grouping", "overall"):
                assert key in conf, f"confidence.{key} missing"
                assert conf[key] in ("high", "medium", "low", "manual", "unknown"), f"bad conf value {conf[key]}"
            # defects must have bbox + confidence when present
            for d in prod.get("defects", []):
                assert "confidence" in d, "defect missing confidence"
                bbox = d.get("bbox")
                assert isinstance(bbox, dict), f"defect missing bbox dict: {d}"
                for k in ("x", "y", "w", "h"):
                    assert k in bbox and 0 <= float(bbox[k]) <= 1.5, f"bbox {k} out of range: {bbox}"


class TestPDFDownload:
    def test_pdf_download_with_query_auth(self, done_inspection, token):
        r = requests.get(
            f"{API}/inspections/{done_inspection['id']}/download/pdf",
            params={"auth": token}, timeout=60,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-", f"not a pdf: {r.content[:20]!r}"
        assert len(r.content) > 2000

    def test_pdf_download_requires_auth(self, done_inspection):
        r = requests.get(f"{API}/inspections/{done_inspection['id']}/download/pdf", timeout=30)
        assert r.status_code == 401


class TestManualRegroup:
    """Split a single-product inspection into 2 groups, confirm no-LLM regen produces
    correct xlsx (2 sheets with proper photo counts) and PDF."""

    def test_regroup_splits_and_regenerates(self, done_inspection, auth_headers, token):
        iid = done_inspection["id"]
        r = requests.get(f"{API}/inspections/{iid}", headers=auth_headers, timeout=30)
        full = r.json()
        photo_count = len(full["photos"])
        assert photo_count >= 4

        # remember original product count to restore later
        original_product_count = full.get("product_count")
        original_name = full["products"][0].get("description") or "Original"
        original_sku = full["products"][0].get("sku") or full["products"][0].get("sku_readable") or "SKU-A"

        half = photo_count // 2
        groups = {
            "groups": [
                {"name": "Group A", "sku": "TEST-GA", "sku_readable": True,
                 "photo_indices": list(range(1, half + 1))},
                {"name": "Group B", "sku": "TEST-GB", "sku_readable": True,
                 "photo_indices": list(range(half + 1, photo_count + 1))},
            ]
        }

        t0 = time.time()
        r = requests.post(f"{API}/inspections/{iid}/regroup", headers=auth_headers, json=groups, timeout=120)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        # Regroup must NOT invoke LLM; should be fast (< 60s even including xlsx+pdf).
        assert elapsed < 90, f"regroup too slow ({elapsed:.1f}s) — may be calling LLM"

        updated = r.json()
        assert updated["status"] == "done"
        assert updated.get("product_count") == 2
        assert updated.get("pdf_path"), "pdf_path missing after regroup"
        prods = updated["products"]
        assert len(prods) == 2
        assert prods[0].get("photo_count") == half
        assert prods[1].get("photo_count") == photo_count - half
        # Each product's defects/measurements should only reference photos within its indices
        for i, prod in enumerate(prods):
            own = set(ph["photo"] for ph in prod.get("photos", []))
            for d in prod.get("defects", []):
                assert d.get("photo") in own, f"defect photo {d.get('photo')} not in group {i} {own}"
            for m in prod.get("measurements", []):
                if m.get("photo") is not None:
                    assert m.get("photo") in own

        # Downloaded xlsx now has 2 sheets with image counts matching
        rx = requests.get(f"{API}/inspections/{iid}/download", params={"auth": token}, timeout=60)
        assert rx.status_code == 200
        wb = load_workbook(io.BytesIO(rx.content))
        assert len(wb.sheetnames) == 2, f"sheets={wb.sheetnames}"
        total_imgs = 0
        for sn in wb.sheetnames:
            ws = wb[sn]
            total_imgs += len(ws._images)
            assert len(ws._images) >= 1, f"no images on {sn}"
        # at least photos + possibly defect crops; must be >= photo_count
        assert total_imgs >= photo_count, f"total imgs {total_imgs} < photos {photo_count}"

        # PDF still valid after regroup
        rp = requests.get(f"{API}/inspections/{iid}/download/pdf", params={"auth": token}, timeout=60)
        assert rp.status_code == 200 and rp.content[:5] == b"%PDF-"

        # restore to single group so other tests / repeated runs stay idempotent
        restore = {"groups": [{"name": original_name, "sku": original_sku,
                               "sku_readable": True,
                               "photo_indices": list(range(1, photo_count + 1))}]}
        rr = requests.post(f"{API}/inspections/{iid}/regroup", headers=auth_headers,
                           json=restore, timeout=120)
        assert rr.status_code == 200
        assert rr.json().get("product_count") == 1

    def test_regroup_rejects_empty(self, done_inspection, auth_headers):
        iid = done_inspection["id"]
        r = requests.post(f"{API}/inspections/{iid}/regroup", headers=auth_headers,
                          json={"groups": [{"name": "x", "sku": "x", "sku_readable": True,
                                            "photo_indices": []}]}, timeout=30)
        assert r.status_code == 400
