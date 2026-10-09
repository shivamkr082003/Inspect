from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, APIRouter, UploadFile, File, Request, HTTPException, Depends, Query
from fastapi.responses import Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

import auth as auth_mod
import storage as storage_mod
import vision as vision_mod
import report as report_mod
import pdf as pdf_mod

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")


# ---------------- Models ----------------
class LoginInput(BaseModel):
    email: str
    password: str


class RegisterInput(BaseModel):
    email: str
    password: str
    name: str = "Inspector"


# ---------------- Auth dependency ----------------
async def current_user(request: Request):
    return await auth_mod.get_user_from_request(request, db)


# ---------------- Auth routes ----------------
@api_router.post("/auth/login")
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower().strip()})
    if not user or not auth_mod.verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth_mod.create_access_token(user["id"], user["email"])
    return {"access_token": token, "user": {"id": user["id"], "email": user["email"], "name": user.get("name")}}


@api_router.post("/auth/register")
async def register(data: RegisterInput):
    email = data.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "email": email, "name": data.name,
        "password_hash": auth_mod.hash_password(data.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    token = auth_mod.create_access_token(uid, email)
    return {"access_token": token, "user": {"id": uid, "email": email, "name": data.name}}


@api_router.get("/auth/me")
async def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name")}


# ---------------- Inspection processing ----------------
async def process_inspection(inspection_id: str):
    try:
        insp = await db.inspections.find_one({"id": inspection_id})
        if not insp:
            return
        await db.inspections.update_one({"id": inspection_id}, {"$set": {"status": "analyzing", "progress": 15}})

        # fetch photo bytes
        loop = asyncio.get_event_loop()
        photos = []
        for i, p in enumerate(insp["photos"], 1):
            data, _ = await loop.run_in_executor(None, storage_mod.get_object, p["storage_path"])
            photos.append({"index": i, "bytes": data, "filename": p["original_filename"]})

        await db.inspections.update_one({"id": inspection_id}, {"$set": {"status": "analyzing", "progress": 35}})
        analysis = await vision_mod.analyze_photos(photos)

        await db.inspections.update_one({"id": inspection_id}, {"$set": {"status": "generating", "progress": 70}})

        bytes_by_index = {p["index"]: p["bytes"] for p in photos}
        fname_by_index = {p["index"]: p["filename"] for p in photos}
        products = analysis.get("products") or []
        for prod in products:
            items = []
            for ph in prod.get("photos", []):
                n = ph.get("photo")
                if n in bytes_by_index:
                    items.append({
                        "photo": n, "category": ph.get("category", "bulk_images"),
                        "bytes": bytes_by_index[n], "filename": fname_by_index.get(n, f"photo{n}"),
                    })
            prod["photo_items"] = items

        await _finalize(inspection_id, products, {
            "photo_count": len(photos),
            "batch_notes": analysis.get("batch_notes", ""),
            "overall_unresolved": analysis.get("overall_unresolved", []),
        })
        logger.info(f"inspection {inspection_id} done: {len(products)} products")
    except Exception as e:
        logger.exception(f"processing failed for {inspection_id}")
        await db.inspections.update_one({"id": inspection_id}, {"$set": {
            "status": "error", "progress": 100, "error": str(e),
        }})


async def _finalize(inspection_id: str, products: list, meta: dict):
    """Generate xlsx + pdf from products (each carrying photo_items with bytes),
    upload both, store UI summaries, mark done. Shared by initial run and regroup."""
    loop = asyncio.get_event_loop()

    # batch-level severity rollup (used by Excel/PDF/UI)
    rollup = {"critical": 0, "major": 0, "minor": 0}
    for prod in products:
        t = report_mod.severity_tally(prod.get("defects"))
        for k in rollup:
            rollup[k] += t[k]

    xlsx = await loop.run_in_executor(None, report_mod.generate_report, products)
    report_path = f"{storage_mod.APP_NAME}/reports/{inspection_id}.xlsx"
    await loop.run_in_executor(
        None, storage_mod.put_object, report_path, xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    pdf_meta = {"id": inspection_id, "photo_count": meta.get("photo_count", 0),
                "severity_rollup": rollup}
    pdf_bytes = await loop.run_in_executor(None, pdf_mod.generate_pdf, products, pdf_meta)
    pdf_path = f"{storage_mod.APP_NAME}/reports/{inspection_id}.pdf"
    await loop.run_in_executor(None, storage_mod.put_object, pdf_path, pdf_bytes, "application/pdf")

    summaries = []
    for i, prod in enumerate(products, 1):
        summaries.append({
            "sheet_name": (prod.get("sku") if prod.get("sku_readable") else f"Product {i}"),
            "sku": prod.get("sku") if prod.get("sku_readable") else None,
            "sku_readable": prod.get("sku_readable", False),
            "distinct_design_count": prod.get("distinct_design_count", 1),
            "visible_unit_count": prod.get("visible_unit_count", 0),
            "description": prod.get("description"),
            "characteristics": prod.get("characteristics"),
            "packaging": prod.get("packaging"),
            "extracted_text": prod.get("extracted_text", {}),
            "measurements": prod.get("measurements", []),
            "weights": prod.get("weights", []),
            "defects": prod.get("defects", []),
            "severity_tally": report_mod.severity_tally(prod.get("defects")),
            "barcode_check": report_mod.barcode_check(prod),
            "confidence": prod.get("confidence", {}),
            "grouping_uncertain": prod.get("grouping_uncertain", False),
            "grouping_uncertain_reason": prod.get("grouping_uncertain_reason", ""),
            "unresolved": prod.get("unresolved", []),
            "photo_count": len(prod.get("photo_items", [])),
            "photos": [{"photo": it["photo"], "category": it.get("category"),
                        "filename": it.get("filename")}
                       for it in prod.get("photo_items", [])],
        })

    update = {
        "status": "done", "progress": 100,
        "report_path": report_path, "pdf_path": pdf_path,
        "products": summaries, "product_count": len(summaries),
        "severity_rollup": rollup,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if "batch_notes" in meta:
        update["batch_notes"] = meta["batch_notes"]
    if "overall_unresolved" in meta:
        update["overall_unresolved"] = meta["overall_unresolved"]
    await db.inspections.update_one({"id": inspection_id}, {"$set": update})



@api_router.post("/inspections")
async def create_inspection(files: List[UploadFile] = File(...), user=Depends(current_user)):
    if not files:
        raise HTTPException(status_code=400, detail="No photos uploaded")
    inspection_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    photos = []
    loop = asyncio.get_event_loop()
    for f in files:
        ext = f.filename.split(".")[-1].lower() if "." in f.filename else "jpg"
        data = await f.read()
        pid = str(uuid.uuid4())
        path = f"{storage_mod.APP_NAME}/uploads/{inspection_id}/{pid}.{ext}"
        ct = f.content_type or "image/jpeg"
        await loop.run_in_executor(None, storage_mod.put_object, path, data, ct)
        photos.append({
            "id": pid, "original_filename": f.filename, "content_type": ct,
            "storage_path": path, "size": len(data), "uploaded_at": now,
        })

    doc = {
        "id": inspection_id, "user_id": user["id"], "status": "queued", "progress": 5,
        "created_at": now, "photo_count": len(photos), "photos": photos,
        "products": [], "report_path": None,
    }
    await db.inspections.insert_one(doc)
    asyncio.create_task(process_inspection(inspection_id))
    return {"id": inspection_id, "status": "queued", "photo_count": len(photos)}


def _clean(doc):
    doc.pop("_id", None)
    return doc


@api_router.get("/inspections")
async def list_inspections(user=Depends(current_user)):
    docs = await db.inspections.find(
        {"user_id": user["id"]},
        {"_id": 0, "photos": 0},
    ).sort("created_at", -1).to_list(200)
    return docs


@api_router.get("/inspections/{inspection_id}")
async def get_inspection(inspection_id: str, user=Depends(current_user)):
    doc = await db.inspections.find_one({"id": inspection_id, "user_id": user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _clean(doc)


@api_router.get("/inspections/{inspection_id}/download")
async def download_report(inspection_id: str, request: Request, auth: str = Query(None)):
    user = await auth_mod.get_user_from_request(request, db, auth_query=auth)
    doc = await db.inspections.find_one({"id": inspection_id, "user_id": user["id"]})
    if not doc or not doc.get("report_path"):
        raise HTTPException(status_code=404, detail="Report not ready")
    loop = asyncio.get_event_loop()
    data, _ = await loop.run_in_executor(None, storage_mod.get_object, doc["report_path"])
    filename = f"inspection_report_{inspection_id[:8]}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/inspections/{inspection_id}/download/pdf")
async def download_pdf(inspection_id: str, request: Request, auth: str = Query(None)):
    user = await auth_mod.get_user_from_request(request, db, auth_query=auth)
    doc = await db.inspections.find_one({"id": inspection_id, "user_id": user["id"]})
    if not doc or not doc.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not ready")
    loop = asyncio.get_event_loop()
    data, _ = await loop.run_in_executor(None, storage_mod.get_object, doc["pdf_path"])
    filename = f"inspection_report_{inspection_id[:8]}.pdf"
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class RegroupGroup(BaseModel):
    name: str = ""
    sku: str | None = None
    sku_readable: bool = False
    photo_indices: List[int] = []


class RegroupInput(BaseModel):
    groups: List[RegroupGroup]


@api_router.post("/inspections/{inspection_id}/regroup")
async def regroup_inspection(inspection_id: str, data: RegroupInput, user=Depends(current_user)):
    doc = await db.inspections.find_one({"id": inspection_id, "user_id": user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if doc.get("status") not in ("done", "error"):
        raise HTTPException(status_code=409, detail="Inspection is still processing")

    photos = doc.get("photos", [])
    n = len(photos)
    all_idx = [i for g in data.groups for i in g.photo_indices]
    for i in all_idx:
        if i < 1 or i > n:
            raise HTTPException(status_code=400, detail=f"Photo index {i} out of range (1..{n})")
    if len(all_idx) != len(set(all_idx)):
        raise HTTPException(status_code=400, detail="A photo was assigned to more than one group")
    if not any(g.photo_indices for g in data.groups):
        raise HTTPException(status_code=400, detail="No valid groups provided")

    groups_spec = [{"name": g.name, "sku": g.sku, "sku_readable": g.sku_readable,
                    "photo_indices": g.photo_indices} for g in data.groups]
    await db.inspections.update_one({"id": inspection_id},
                                    {"$set": {"status": "generating", "progress": 55, "error": None}})
    asyncio.create_task(_run_regroup(inspection_id, groups_spec))
    updated = await db.inspections.find_one({"id": inspection_id})
    return _clean(updated)


async def _run_regroup(inspection_id: str, groups_spec: list):
    try:
        doc = await db.inspections.find_one({"id": inspection_id})
        old_products = doc.get("products", [])
        photos = doc.get("photos", [])
        cat_by_idx, orig_by_idx = {}, {}
        for pi, prod in enumerate(old_products):
            for ph in prod.get("photos", []):
                cat_by_idx[ph["photo"]] = ph.get("category", "bulk_images")
                orig_by_idx[ph["photo"]] = pi

        loop = asyncio.get_event_loop()
        new_products = []
        for g in groups_spec:
            idxs = sorted(set(i for i in g["photo_indices"] if 1 <= i <= len(photos)))
            if not idxs:
                continue
            contributing = [orig_by_idx.get(i) for i in idxs if orig_by_idx.get(i) is not None]
            dominant_pi = max(set(contributing), key=contributing.count) if contributing else None
            dom = old_products[dominant_pi] if dominant_pi is not None else {}
            idx_set = set(idxs)

            def keep(items, _s=idx_set):
                return [it for it in (items or []) if it.get("photo") in _s]

            distinct_originals = len(set(contributing))
            same_single = distinct_originals == 1 and set(
                ph["photo"] for ph in old_products[contributing[0]].get("photos", [])
            ) == idx_set
            if same_single:
                vuc = dom.get("visible_unit_count", len(idxs))
            else:
                vuc = sum(old_products[pi].get("visible_unit_count", 0) for pi in set(contributing)) or len(idxs)

            unresolved = list(dom.get("unresolved", []))
            unresolved.append("Visible unit count may need review after manual regroup.")

            items = []
            for i in idxs:
                p = photos[i - 1]
                b, _ = await loop.run_in_executor(None, storage_mod.get_object, p["storage_path"])
                items.append({"photo": i, "category": cat_by_idx.get(i, "bulk_images"),
                              "bytes": b, "filename": p["original_filename"]})

            conf = dict(dom.get("confidence") or {})
            conf["grouping"] = "manual"
            new_products.append({
                "sku": g["sku"] if g["sku_readable"] else None,
                "sku_readable": g["sku_readable"],
                "distinct_design_count": max(1, distinct_originals),
                "visible_unit_count": vuc,
                "description": g["name"] or dom.get("description"),
                "characteristics": dom.get("characteristics"),
                "packaging": dom.get("packaging"),
                "extracted_text": dom.get("extracted_text", {}),
                "measurements": keep(dom.get("measurements")),
                "weights": keep(dom.get("weights")),
                "defects": keep(dom.get("defects")),
                "confidence": conf,
                "grouping_uncertain": False,
                "grouping_uncertain_reason": "Manually regrouped by inspector.",
                "unresolved": unresolved,
                "photo_items": items,
            })

        await _finalize(inspection_id, new_products, {"photo_count": len(photos)})
        logger.info(f"regroup {inspection_id} done: {len(new_products)} products")
    except Exception as e:
        logger.exception("regroup failed")
        await db.inspections.update_one({"id": inspection_id},
                                        {"$set": {"status": "error", "error": str(e), "progress": 100}})



@api_router.get("/inspections/{inspection_id}/photos/{photo_id}")
async def get_photo(inspection_id: str, photo_id: str, request: Request, auth: str = Query(None)):
    user = await auth_mod.get_user_from_request(request, db, auth_query=auth)
    doc = await db.inspections.find_one({"id": inspection_id, "user_id": user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Inspection not found")
    photo = next((p for p in doc["photos"] if p["id"] == photo_id), None)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    loop = asyncio.get_event_loop()
    data, ct = await loop.run_in_executor(None, storage_mod.get_object, photo["storage_path"])
    return Response(content=data, media_type=photo.get("content_type", ct))


class ReviewPackInput(BaseModel):
    ids: List[str]


@api_router.post("/inspections/review-pack")
async def review_pack(data: ReviewPackInput, user=Depends(current_user)):
    if not data.ids:
        raise HTTPException(status_code=400, detail="No inspections selected")
    loop = asyncio.get_event_loop()
    sections = []
    for iid in data.ids[:20]:
        doc = await db.inspections.find_one({"id": iid, "user_id": user["id"]})
        if not doc or doc.get("status") != "done":
            continue
        photos = doc.get("photos", [])
        products = []
        for prod in doc.get("products", []):
            items = []
            for ph in prod.get("photos", []):
                idx = ph.get("photo")
                if idx and 1 <= idx <= len(photos):
                    p = photos[idx - 1]
                    b, _ = await loop.run_in_executor(None, storage_mod.get_object, p["storage_path"])
                    items.append({"photo": idx, "category": ph.get("category", "bulk_images"),
                                  "bytes": b, "filename": p["original_filename"]})
            prod = dict(prod)
            prod["photo_items"] = items
            products.append(prod)
        sections.append({
            "meta": {"id": doc["id"], "created_at": doc.get("created_at", ""),
                     "photo_count": doc.get("photo_count", 0),
                     "severity_rollup": doc.get("severity_rollup", {})},
            "products": products,
        })
    if not sections:
        raise HTTPException(status_code=404, detail="No completed inspections found for the selection")
    pdf_bytes = await loop.run_in_executor(None, pdf_mod.generate_review_pack, sections)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="supplier_review_pack.pdf"'},
    )


@api_router.get("/")
async def root():
    return {"message": "InspectAI API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        storage_mod.init_storage()
        logger.info("storage initialized")
    except Exception as e:
        logger.error(f"storage init failed: {e}")
    await db.users.create_index("email", unique=True)
    await db.inspections.create_index("id", unique=True)
    # Processing runs as in-process tasks, so anything still in flight died with the previous process.
    await db.inspections.update_many(
        {"status": {"$in": ["queued", "analyzing", "generating"]}},
        {"$set": {"status": "error", "progress": 100,
                  "error": "Server restarted while this report was processing. Please upload the photos again."}},
    )
    admin_email = os.environ.get("ADMIN_EMAIL", "inspector@indigo.com").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "inspect123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": admin_email, "name": "Lead Inspector",
            "password_hash": auth_mod.hash_password(admin_pw),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("seeded admin user")
    elif not auth_mod.verify_password(admin_pw, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": auth_mod.hash_password(admin_pw)}})


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
