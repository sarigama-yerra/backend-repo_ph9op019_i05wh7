import os
from typing import List, Optional, Any, Dict
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from database import db, create_document, get_documents
from schemas import Trek, BlogPost, Inquiry, AdminUser

app = FastAPI(title="Juma Trek API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Helpers --------------------
class IdResponse(BaseModel):
    id: str

class AdminAuth(BaseModel):
    email: EmailStr
    password: str


def get_collection_name(model_cls) -> str:
    return model_cls.__name__.lower()


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


def require_admin(x_admin_key: Optional[str] = Header(None)):
    expected = os.getenv("ADMIN_API_KEY")
    if expected and x_admin_key == expected:
        return True
    if not expected:
        # If no key set, allow all (dev mode)
        return True
    raise HTTPException(status_code=401, detail="Unauthorized")


# -------------------- Root & Health --------------------
@app.get("/")
def read_root():
    return {"message": "Juma Trek API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, "name", "unknown")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# -------------------- Schema Endpoint --------------------
@app.get("/schema")
def get_schema_definitions():
    return {
        "trek": Trek.model_json_schema(),
        "blogpost": BlogPost.model_json_schema(),
        "inquiry": Inquiry.model_json_schema(),
        "adminuser": AdminUser.model_json_schema(),
    }


# -------------------- Treks --------------------
@app.get("/api/treks")
def list_treks(
    region: Optional[str] = None,
    difficulty: Optional[str] = None,
    min_days: Optional[int] = Query(None, ge=1),
    max_days: Optional[int] = Query(None, ge=1),
    search: Optional[str] = None,
    featured: Optional[bool] = None,
):
    filter_q: Dict[str, Any] = {}
    if region:
        filter_q["region"] = {"$regex": region, "$options": "i"}
    if difficulty:
        filter_q["difficulty"] = {"$regex": f"^{difficulty}$", "$options": "i"}
    if min_days is not None or max_days is not None:
        dur_cond: Dict[str, Any] = {}
        if min_days is not None:
            dur_cond["$gte"] = min_days
        if max_days is not None:
            dur_cond["$lte"] = max_days
        filter_q["duration_days"] = dur_cond
    if search:
        filter_q["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"overview": {"$regex": search, "$options": "i"}},
            {"highlights": {"$elemMatch": {"$regex": search, "$options": "i"}}},
        ]
    if featured is not None:
        filter_q["is_featured"] = featured

    docs = get_documents(get_collection_name(Trek), filter_q)
    return [serialize_doc(d) for d in docs]


@app.get("/api/treks/{trek_id}")
def get_trek(trek_id: str):
    doc = db[get_collection_name(Trek)].find_one({"_id": to_object_id(trek_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Trek not found")
    return serialize_doc(doc)


@app.post("/api/treks", response_model=IdResponse)
def create_trek(payload: Trek, _: bool = Depends(require_admin)):
    new_id = create_document(get_collection_name(Trek), payload)
    return {"id": new_id}


@app.put("/api/treks/{trek_id}")
def update_trek(trek_id: str, payload: Trek, _: bool = Depends(require_admin)):
    col = db[get_collection_name(Trek)]
    res = col.update_one(
        {"_id": to_object_id(trek_id)},
        {"$set": {**payload.model_dump(), "updated_at": datetime.utcnow()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trek not found")
    doc = col.find_one({"_id": to_object_id(trek_id)})
    return serialize_doc(doc)


@app.delete("/api/treks/{trek_id}", response_model=IdResponse)
def delete_trek(trek_id: str, _: bool = Depends(require_admin)):
    col = db[get_collection_name(Trek)]
    res = col.delete_one({"_id": to_object_id(trek_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trek not found")
    return {"id": trek_id}


# -------------------- Blog Posts --------------------
@app.get("/api/blog-posts")
def list_blog_posts(tag: Optional[str] = None, search: Optional[str] = None):
    filter_q: Dict[str, Any] = {}
    if tag:
        filter_q["tags"] = {"$elemMatch": {"$regex": tag, "$options": "i"}}
    if search:
        filter_q["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"content": {"$regex": search, "$options": "i"}},
        ]
    docs = get_documents(get_collection_name(BlogPost), filter_q)
    return [serialize_doc(d) for d in docs]


@app.get("/api/blog-posts/{post_id}")
def get_blog_post(post_id: str):
    doc = db[get_collection_name(BlogPost)].find_one({"_id": to_object_id(post_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return serialize_doc(doc)


@app.post("/api/blog-posts", response_model=IdResponse)
def create_blog_post(payload: BlogPost, _: bool = Depends(require_admin)):
    new_id = create_document(get_collection_name(BlogPost), payload)
    return {"id": new_id}


@app.put("/api/blog-posts/{post_id}")
def update_blog_post(post_id: str, payload: BlogPost, _: bool = Depends(require_admin)):
    col = db[get_collection_name(BlogPost)]
    res = col.update_one(
        {"_id": to_object_id(post_id)},
        {"$set": {**payload.model_dump(), "updated_at": datetime.utcnow()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    doc = col.find_one({"_id": to_object_id(post_id)})
    return serialize_doc(doc)


@app.delete("/api/blog-posts/{post_id}", response_model=IdResponse)
def delete_blog_post(post_id: str, _: bool = Depends(require_admin)):
    col = db[get_collection_name(BlogPost)]
    res = col.delete_one({"_id": to_object_id(post_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"id": post_id}


# -------------------- Inquiries --------------------
class InquiryResponse(BaseModel):
    message: str
    id: Optional[str] = None


def try_send_email(subject: str, body_html: str, to_email: str) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "0") or 0)
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    from_email = os.getenv("SMTP_FROM", user or "noreply@example.com")
    if not (host and port and user and pwd):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, pwd)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception:
        return False


@app.post("/api/inquiries", response_model=InquiryResponse)
def create_inquiry(payload: Inquiry):
    new_id = create_document(get_collection_name(Inquiry), payload)
    # Send notification emails if SMTP configured
    admin_email = os.getenv("ADMIN_NOTIFY_EMAIL")
    client_ok = False
    admin_ok = False
    if admin_email:
        admin_ok = try_send_email(
            subject="New Trek Inquiry",
            body_html=f"""
            <h2>New Inquiry</h2>
            <p><b>Name:</b> {payload.name}</p>
            <p><b>Email:</b> {payload.email}</p>
            <p><b>Trek ID:</b> {payload.trek_id or '-'}
            <p><b>Travelers:</b> {payload.travelers or 1}</p>
            <p><b>Preferred Start:</b> {payload.preferred_start_date or '-'}
            <p><b>Message:</b><br/>{payload.message}</p>
            """,
            to_email=admin_email,
        )
    client_ok = try_send_email(
        subject="We received your inquiry - Juma Trek",
        body_html=f"""
        <p>Hi {payload.name},</p>
        <p>Thanks for reaching out to Juma Trek! Our team will get back to you shortly.</p>
        <p>Summary of your request:</p>
        <ul>
          <li>Trek ID: {payload.trek_id or '-'}
          <li>Travelers: {payload.travelers or 1}
          <li>Preferred Start: {payload.preferred_start_date or '-'}
        </ul>
        <p>— Juma Trek Team</p>
        """,
        to_email=payload.email,
    )
    note = " Email notifications sent." if (client_ok or admin_ok) else " Email notifications skipped."
    return {"message": "Inquiry submitted successfully." + note, "id": new_id}


@app.get("/api/inquiries")
def list_inquiries(_: bool = Depends(require_admin)):
    docs = get_documents(get_collection_name(Inquiry), {})
    return [serialize_doc(d) for d in docs]


# -------------------- Admin Users (basic) --------------------
import os as _os
import hashlib
import secrets


def hash_password(password: str, salt: Optional[str] = None) -> (str, str):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return dk.hex(), salt


class CreateAdmin(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


@app.post("/api/admin/users", response_model=IdResponse)
def create_admin_user(payload: CreateAdmin, _: bool = Depends(require_admin)):
    pw_hash, salt = hash_password(payload.password)
    admin_doc = AdminUser(
        email=payload.email,
        password_hash=pw_hash,
        password_salt=salt,
        full_name=payload.full_name,
    )
    new_id = create_document(get_collection_name(AdminUser), admin_doc)
    return {"id": new_id}


@app.post("/api/admin/login")
def admin_login(payload: AdminAuth):
    col = db[get_collection_name(AdminUser)]
    user = col.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    calc_hash, _ = hash_password(payload.password, user.get("password_salt"))
    if calc_hash != user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # For simplicity, return a static token if ADMIN_API_KEY is set
    token = os.getenv("ADMIN_API_KEY") or "dev-admin"
    return {"token": token, "user": {"email": user.get("email"), "id": str(user.get("_id"))}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
