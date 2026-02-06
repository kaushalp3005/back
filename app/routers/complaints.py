from fastapi import APIRouter, Depends, HTTPException, Query, Path, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import shutil
from datetime import datetime
from typing import Optional, List

from app.core.database import get_db
from app.schemas.complaints import (
    ComplaintCreate, ComplaintCreateResponse, ComplaintDetail,
    ComplaintUpdate, ComplaintListResponse, ComplaintListItem,
    ComplaintDeleteResponse, StatsResponse, VideoUploadResponse
)

router = APIRouter(prefix="/api", tags=["complaints"])


def table_prefix(company: str) -> str:
    company = (company or "").upper()
    if company == "CDPL":
        return "cdpl"
    if company == "CFPL":
        return "cfpl"
    raise HTTPException(status_code=400, detail="company must be CDPL or CFPL")


def to_upper(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return s.strip().upper()


@router.post("/complaints", response_model=ComplaintCreateResponse)
def create_complaint(payload: ComplaintCreate, db: Session = Depends(get_db)):
    try:
        prefix = table_prefix(payload.company)

        # Generate complaint_id via DB function
        func_sql = text(f"SELECT generate_{prefix}_complaint_id() AS complaint_id")
        complaint_id = db.execute(func_sql).scalar_one()

        # Insert master
        insert_sql = text(f"""
            INSERT INTO {prefix}_complaints (
              complaint_id, customer_id, customer_name, received_date, manufacturing_date,
              item_category, item_subcategory, item_description, batch_code,
              quantity_rejected, quantity_approved, uom, complaint_nature, other_complaint_nature,
              qa_assessment, justified_status, remarks, created_by
            ) VALUES (
              :complaint_id,
              (SELECT id FROM {prefix}_customers WHERE customer_name = :customer_name LIMIT 1),
              :customer_name, :received_date, :manufacturing_date,
              :item_category, :item_subcategory, :item_description, :batch_code,
              :quantity_rejected, :quantity_approved, :uom, :complaint_nature, :other_complaint_nature,
              :qa_assessment, :justified_status, :remarks, :created_by
            ) RETURNING id, created_at, updated_at
        """)

        master = db.execute(
            insert_sql,
            {
                "complaint_id": complaint_id,
                "customer_name": payload.customerName,
                "received_date": payload.receivedDate,
                "manufacturing_date": payload.manufacturingDate,
                "item_category": payload.itemCategory,
                "item_subcategory": payload.itemSubcategory,
                "item_description": payload.itemDescription,
                "batch_code": payload.batchCode,
                "quantity_rejected": payload.quantityRejected,
                "quantity_approved": payload.quantityApproved,
                "uom": payload.uom,
                "complaint_nature": payload.complaintNature,
                "other_complaint_nature": payload.otherComplaintNature,
                "qa_assessment": payload.qaAssessment,
                "justified_status": payload.justifiedStatus,
                "remarks": payload.remarks,
                "created_by": payload.createdBy,
            },
        ).mappings().one()
        complaint_pk = master["id"]

        # Insert articles
        article_rows = []
        if payload.articles:
            art_sql = text(
                f"""
                INSERT INTO {prefix}_complaint_articles (
                  complaint_id, item_category, item_subcategory, item_description, quantity, uom
                ) VALUES (
                  :complaint_id, :item_category, :item_subcategory, :item_description, :quantity, :uom
                ) RETURNING id
                """
            )
            for a in payload.articles:
                row = db.execute(
                    art_sql,
                    {
                        "complaint_id": complaint_pk,
                        "item_category": a.itemCategory,
                        "item_subcategory": a.itemSubcategory,
                        "item_description": a.itemDescription,
                        "quantity": a.quantity,
                        "uom": a.uom,
                    },
                ).scalar_one()
                article_rows.append({
                    "id": row,
                    "itemCategory": to_upper(a.itemCategory),
                    "itemSubcategory": to_upper(a.itemSubcategory) if a.itemSubcategory else None,
                    "itemDescription": to_upper(a.itemDescription),
                    "quantity": a.quantity,
                    "uom": to_upper(a.uom) if a.uom else None,
                })

        # Insert proof images as proofs entries (paths only)
        if payload.proofImages:
            proof_sql = text(
                f"""
                INSERT INTO {prefix}_complaint_proofs (
                  complaint_id, file_name, file_type, file_size, s3_bucket, s3_key, s3_url, uploaded_by
                ) VALUES (
                  :complaint_id, :file_name, :file_type, NULL, NULL, :s3_key, :s3_url, :uploaded_by
                )
                """
            )
            for img_path in payload.proofImages:
                file_name = os.path.basename(img_path)
                db.execute(
                    proof_sql,
                    {
                        "complaint_id": complaint_pk,
                        "file_name": file_name,
                        "file_type": "image/*",
                        "s3_key": img_path,
                        "s3_url": img_path,
                        "uploaded_by": payload.createdBy,
                    },
                )

        db.commit()

        # Build response
        data = ComplaintDetail(
            id=complaint_pk,
            complaintId=complaint_id,
            company=payload.company,
            customerName=to_upper(payload.customerName),
            receivedDate=payload.receivedDate,
            manufacturingDate=payload.manufacturingDate,
            itemCategory=to_upper(payload.itemCategory) if payload.itemCategory else None,
            itemSubcategory=to_upper(payload.itemSubcategory) if payload.itemSubcategory else None,
            itemDescription=to_upper(payload.itemDescription) if payload.itemDescription else None,
            batchCode=to_upper(payload.batchCode) if payload.batchCode else None,
            quantityRejected=payload.quantityRejected,
            quantityApproved=payload.quantityApproved,
            uom=to_upper(payload.uom) if payload.uom else None,
            complaintNature=to_upper(payload.complaintNature) if payload.complaintNature else None,
            otherComplaintNature=to_upper(payload.otherComplaintNature) if payload.otherComplaintNature else None,
            qaAssessment=to_upper(payload.qaAssessment) if payload.qaAssessment else None,
            justifiedStatus=to_upper(payload.justifiedStatus) if payload.justifiedStatus else None,
            remarks=to_upper(payload.remarks) if payload.remarks else None,
            proofImages=payload.proofImages,
            articles=article_rows,
            createdBy=to_upper(payload.createdBy),
            updatedBy=None,
            createdAt=master["created_at"].isoformat() if master.get("created_at") else None,
            updatedAt=master["updated_at"].isoformat() if master.get("updated_at") else None,
            sampleVideo=None,
        )

        return ComplaintCreateResponse(success=True, data=data, message="Complaint created successfully")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create complaint: {str(e)}")


@router.get("/complaints", response_model=ComplaintListResponse)
def list_complaints(
    company: str = Query(..., pattern="^(CFPL|CDPL)$"),
    status: Optional[str] = None,
    customerName: Optional[str] = None,
    fromDate: Optional[str] = None,
    toDate: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    try:
        prefix = table_prefix(company)

        where = ["1=1"]
        params = {}
        if customerName:
            where.append("customer_name ILIKE :cust")
            params["cust"] = f"%{customerName}%"
        if fromDate:
            where.append("received_date >= :from")
            params["from"] = fromDate
        if toDate:
            where.append("received_date <= :to")
            params["to"] = toDate
        where_sql = " AND ".join(where)

        list_sql = text(f"""
            WITH base AS (
                SELECT c.id,
                       c.complaint_id,
                       c.customer_name,
                       c.item_description,
                       c.batch_code,
                       c.qa_assessment,
                       c.justified_status,
                       c.quantity_rejected,
                       c.received_date,
                       c.created_at,
                       c.updated_at,
                       (SELECT p.s3_url FROM {prefix}_complaint_proofs p
                          WHERE p.complaint_id = c.id
                            AND (p.file_type ILIKE 'video/%' OR p.file_name ~* '\\.(mp4|mov|avi|mkv)$')
                          ORDER BY p.uploaded_at DESC
                          LIMIT 1) AS sample_video
                FROM {prefix}_complaints c
                WHERE {where_sql}
            )
            SELECT * FROM base
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        count_sql = text(f"""
            SELECT COUNT(*) FROM {prefix}_complaints c WHERE {where_sql}
        """)

        rows = db.execute(list_sql, {**params, "limit": limit, "offset": (page - 1) * limit}).mappings().all()
        total = db.execute(count_sql, params).scalar_one()

        items: List[ComplaintListItem] = []
        for r in rows:
            items.append(
                ComplaintListItem(
                    id=r["id"],
                    complaintId=r["complaint_id"],
                    company=company,
                    customerName=to_upper(r["customer_name"]) if r["customer_name"] else "",
                    itemDescription=to_upper(r["item_description"]) if r["item_description"] else None,
                    batchCode=to_upper(r["batch_code"]) if r["batch_code"] else None,
                    status=to_upper(status) if status else "OPEN",
                    qaAssessment=to_upper(r["qa_assessment"]) if r["qa_assessment"] else None,
                    justifiedStatus=to_upper(r["justified_status"]) if r["justified_status"] else None,
                    quantityRejected=r["quantity_rejected"],
                    estimatedLoss=None,
                    measuresToResolve=None,
                    receivedDate=r["received_date"].isoformat() if hasattr(r["received_date"], 'isoformat') else str(r["received_date"]),
                    createdAt=r["created_at"].isoformat() if r.get("created_at") else None,
                    updatedAt=r["updated_at"].isoformat() if r.get("updated_at") else None,
                    sampleVideo=r["sample_video"],
                )
            )

        return ComplaintListResponse(
            success=True,
            data=items,
            meta={
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": (total + limit - 1) // limit,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch complaints: {str(e)}")


@router.get("/complaints/{id}", response_model=ComplaintDetail)
def get_complaint(id: int = Path(..., ge=1), company: str = Query(..., pattern="^(CFPL|CDPL)$"), db: Session = Depends(get_db)):
    try:
        prefix = table_prefix(company)

        master = db.execute(text(f"SELECT * FROM {prefix}_complaints WHERE id = :id"), {"id": id}).mappings().first()
        if not master:
            raise HTTPException(status_code=404, detail="Complaint not found")

        arts = db.execute(
            text(f"SELECT id, item_category, item_subcategory, item_description, quantity, uom FROM {prefix}_complaint_articles WHERE complaint_id = :id ORDER BY id"),
            {"id": id},
        ).mappings().all()

        imgs = db.execute(
            text(
                f"""
                SELECT s3_url AS path FROM {prefix}_complaint_proofs
                WHERE complaint_id = :id AND (file_type ILIKE 'image/%' OR file_name ~* '\\.(png|jpg|jpeg|webp)$')
                ORDER BY uploaded_at
                """
            ),
            {"id": id},
        ).scalars().all()

        video = db.execute(
            text(
                f"""
                SELECT s3_url FROM {prefix}_complaint_proofs
                WHERE complaint_id = :id AND (file_type ILIKE 'video/%' OR file_name ~* '\\.(mp4|mov|avi|mkv)$')
                ORDER BY uploaded_at DESC LIMIT 1
                """
            ),
            {"id": id},
        ).scalar()

        d = ComplaintDetail(
            id=master["id"],
            complaintId=master["complaint_id"],
            company=company,
            customerName=to_upper(master["customer_name"]) if master["customer_name"] else "",
            receivedDate=master["received_date"].isoformat() if hasattr(master["received_date"], 'isoformat') else str(master["received_date"]),
            manufacturingDate=master["manufacturing_date"].isoformat() if master.get("manufacturing_date") and hasattr(master["manufacturing_date"], 'isoformat') else (str(master["manufacturing_date"]) if master.get("manufacturing_date") else None),
            itemCategory=to_upper(master.get("item_category")) if master.get("item_category") else None,
            itemSubcategory=to_upper(master.get("item_subcategory")) if master.get("item_subcategory") else None,
            itemDescription=to_upper(master.get("item_description")) if master.get("item_description") else None,
            batchCode=to_upper(master.get("batch_code")) if master.get("batch_code") else None,
            quantityRejected=master.get("quantity_rejected"),
            quantityApproved=master.get("quantity_approved"),
            uom=to_upper(master.get("uom")) if master.get("uom") else None,
            complaintNature=to_upper(master.get("complaint_nature")) if master.get("complaint_nature") else None,
            otherComplaintNature=to_upper(master.get("other_complaint_nature")) if master.get("other_complaint_nature") else None,
            qaAssessment=to_upper(master.get("qa_assessment")) if master.get("qa_assessment") else None,
            justifiedStatus=to_upper(master.get("justified_status")) if master.get("justified_status") else None,
            remarks=to_upper(master.get("remarks")) if master.get("remarks") else None,
            proofImages=imgs,
            articles=[
                {
                    "id": a["id"],
                    "itemCategory": to_upper(a["item_category"]) if a["item_category"] else None,
                    "itemSubcategory": to_upper(a["item_subcategory"]) if a["item_subcategory"] else None,
                    "itemDescription": to_upper(a["item_description"]) if a["item_description"] else None,
                    "quantity": a["quantity"],
                    "uom": to_upper(a["uom"]) if a["uom"] else None,
                }
                for a in arts
            ],
            createdBy=to_upper(master.get("created_by")) if master.get("created_by") else None,
            updatedBy=None,
            createdAt=master.get("created_at").isoformat() if master.get("created_at") else None,
            updatedAt=master.get("updated_at").isoformat() if master.get("updated_at") else None,
            sampleVideo=video,
        )
        return d
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch complaint: {str(e)}")


@router.put("/complaints/{id}")
def update_complaint(id: int, payload: ComplaintUpdate, db: Session = Depends(get_db)):
    try:
        prefix = table_prefix(payload.company)

        upd = text(f"""
            UPDATE {prefix}_complaints
               SET customer_name = :customer_name,
                   received_date = :received_date,
                   manufacturing_date = :manufacturing_date,
                   item_category = :item_category,
                   item_subcategory = :item_subcategory,
                   item_description = :item_description,
                   batch_code = :batch_code,
                   quantity_rejected = :quantity_rejected,
                   quantity_approved = :quantity_approved,
                   uom = :uom,
                   complaint_nature = :complaint_nature,
                   other_complaint_nature = :other_complaint_nature,
                   qa_assessment = :qa_assessment,
                   justified_status = :justified_status,
                   remarks = :remarks,
                   updated_at = NOW()
             WHERE id = :id
        """)
        res = db.execute(
            upd,
            {
                "id": id,
                "customer_name": payload.customerName,
                "received_date": payload.receivedDate,
                "manufacturing_date": payload.manufacturingDate,
                "item_category": payload.itemCategory,
                "item_subcategory": payload.itemSubcategory,
                "item_description": payload.itemDescription,
                "batch_code": payload.batchCode,
                "quantity_rejected": payload.quantityRejected,
                "quantity_approved": payload.quantityApproved,
                "uom": payload.uom,
                "complaint_nature": payload.complaintNature,
                "other_complaint_nature": payload.otherComplaintNature,
                "qa_assessment": payload.qaAssessment,
                "justified_status": payload.justifiedStatus,
                "remarks": payload.remarks,
            },
        )
        if res.rowcount == 0:
            db.rollback()
            raise HTTPException(status_code=404, detail="Complaint not found")

        # Replace articles
        db.execute(text(f"DELETE FROM {prefix}_complaint_articles WHERE complaint_id = :id"), {"id": id})
        if payload.articles:
            art_sql = text(
                f"""
                INSERT INTO {prefix}_complaint_articles (
                  complaint_id, item_category, item_subcategory, item_description, quantity, uom
                ) VALUES (
                  :complaint_id, :item_category, :item_subcategory, :item_description, :quantity, :uom
                )
                """
            )
            for a in payload.articles:
                db.execute(
                    art_sql,
                    {
                        "complaint_id": id,
                        "item_category": a.itemCategory,
                        "item_subcategory": a.itemSubcategory,
                        "item_description": a.itemDescription,
                        "quantity": a.quantity,
                        "uom": a.uom,
                    },
                )

        # Insert any new proof images (idempotency left to caller)
        if payload.proofImages:
            proof_sql = text(
                f"""
                INSERT INTO {prefix}_complaint_proofs (
                  complaint_id, file_name, file_type, file_size, s3_bucket, s3_key, s3_url, uploaded_by
                ) VALUES (
                  :complaint_id, :file_name, :file_type, NULL, NULL, :s3_key, :s3_url, :uploaded_by
                )
                """
            )
            for img_path in payload.proofImages:
                file_name = os.path.basename(img_path)
                db.execute(
                    proof_sql,
                    {
                        "complaint_id": id,
                        "file_name": file_name,
                        "file_type": "image/*",
                        "s3_key": img_path,
                        "s3_url": img_path,
                        "uploaded_by": payload.updatedBy,
                    },
                )

        db.commit()
        # Return refreshed detail
        return get_complaint(id=id, company=payload.company, db=db)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update complaint: {str(e)}")


@router.delete("/complaints/{id}", response_model=ComplaintDeleteResponse)
def delete_complaint(id: int, company: str = Query(..., pattern="^(CFPL|CDPL)$"), db: Session = Depends(get_db)):
    try:
        prefix = table_prefix(company)
        # If you add RCA/CAPA checks, do here
        # Delete master cascades to articles/proofs/history
        res = db.execute(text(f"DELETE FROM {prefix}_complaints WHERE id = :id RETURNING complaint_id"), {"id": id}).scalar()
        if not res:
            db.rollback()
            raise HTTPException(status_code=404, detail="Complaint not found")
        db.commit()
        return ComplaintDeleteResponse(success=True, message="Complaint deleted successfully", data={"id": id, "complaintId": res})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete complaint: {str(e)}")


@router.post("/sample-video", response_model=VideoUploadResponse)
async def upload_sample_video(
    file: UploadFile = File(...),
    complaintId: str = Form(...),
    company: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        prefix = table_prefix(company)
        # Store file
        ext = os.path.splitext(file.filename)[1]
        ts = int(datetime.utcnow().timestamp())
        safe_name = f"{complaintId}_{ts}{ext}"
        rel_dir = os.path.join("uploads", "sample-videos")
        os.makedirs(rel_dir, exist_ok=True)
        abs_path = os.path.join(rel_dir, safe_name)
        with open(abs_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        # Link to complaint via proofs table
        complaint_pk = (
            db.execute(text(f"SELECT id FROM {prefix}_complaints WHERE complaint_id = :cid"), {"cid": complaintId}).scalar()
        )
        if not complaint_pk:
            raise HTTPException(status_code=404, detail="Complaint not found")

        proof_sql = text(
            f"""
            INSERT INTO {prefix}_complaint_proofs (
              complaint_id, file_name, file_type, file_size, s3_bucket, s3_key, s3_url, uploaded_by
            ) VALUES (
              :complaint_id, :file_name, :file_type, :file_size, NULL, :s3_key, :s3_url, :uploaded_by
            )
            """
        )
        db.execute(
            proof_sql,
            {
                "complaint_id": complaint_pk,
                "file_name": safe_name,
                "file_type": file.content_type or "video/*",
                "file_size": None,
                "s3_key": abs_path,
                "s3_url": "/" + abs_path.replace("\\", "/"),
                "uploaded_by": "SYSTEM",
            },
        )
        db.commit()

        return VideoUploadResponse(
            success=True,
            data={
                "path": "/" + abs_path.replace("\\", "/"),
                "fileName": safe_name,
                "size": None,
                "type": file.content_type or "video/*",
                "complaintId": complaintId,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {str(e)}")


@router.get("/complaints/stats", response_model=StatsResponse)
def complaint_stats(company: str = Query(..., pattern="^(CFPL|CDPL)$"), month: str = Query(..., description="YYYY-MM"), db: Session = Depends(get_db)):
    try:
        prefix = table_prefix(company)

        total = db.execute(
            text(f"SELECT COUNT(*) FROM {prefix}_complaints WHERE TO_CHAR(received_date, 'YYYY-MM') = :m"),
            {"m": month},
        ).scalar()

        by_just = db.execute(
            text(
                f"SELECT LOWER(COALESCE(justified_status,'unknown')) AS key, COUNT(*) AS count FROM {prefix}_complaints WHERE TO_CHAR(received_date, 'YYYY-MM') = :m GROUP BY LOWER(COALESCE(justified_status,'unknown'))"
            ),
            {"m": month},
        ).mappings().all()

        top_customers = db.execute(
            text(
                f"SELECT UPPER(customer_name) AS name, COUNT(*) AS count FROM {prefix}_complaints WHERE TO_CHAR(received_date, 'YYYY-MM') = :m GROUP BY UPPER(customer_name) ORDER BY count DESC LIMIT 5"
            ),
            {"m": month},
        ).mappings().all()

        return StatsResponse(
            success=True,
            data={
                "total": total,
                "byStatus": {"open": None, "in_progress": None, "resolved": None, "closed": None},
                "byJustification": {row["key"]: row["count"] for row in by_just},
                "totalLoss": None,
                "avgResponseTime": None,
                "topCustomers": top_customers,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
