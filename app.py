from flask import Flask, render_template, request, redirect, send_from_directory, session, url_for, flash, jsonify
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import re

import time

import io
import zipfile
import requests
from flask import send_file

import cloudinary
import cloudinary.uploader
import cloudinary.api
import json
import re

# =========================
# PERMISSION SECURITY LAYER
# =========================
def has_access(hospital=None, doctor=None):
    role = session.get("role")
    user = session.get("user")

    # Admin can do everything
    if role == "admin":
        return True

    # Hospital can only its own
    if role == "hospital":
        return hospital == user

    # Doctor can only own hospital+doctor
    if role == "doctor":
        return hospital == session.get("hospital") and doctor == user

    return False


# =========================
# SHARE TOKEN STORAGE
# =========================
SHARE_PATH = "shares.json"

def load_shares():
    if not os.path.exists(SHARE_PATH):
        return {"tokens": {}}
    with open(SHARE_PATH, "r") as f:
        return json.load(f)

def save_shares(data):
    with open(SHARE_PATH, "w") as f:
        json.dump(data, f, indent=2)



AUTH_FILE = "data/auth.json"

def load_auth():
    with open(AUTH_FILE, "r") as f:
        return json.load(f)

def save_auth(data):
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)


def build_auth_maps():
    auth = load_auth()

    doctor_map = {}
    doctor_passwords = {}
    hospital_passwords = {}

    # Hospitals
    for hospital, data in auth["hospitals"].items():
        hospital_passwords[hospital] = data["password_hash"]

    # Doctors
    for doctor, data in auth["doctors"].items():
        doctor_map[doctor] = data["hospital"]
        doctor_passwords[doctor] = data["password_hash"]

    return doctor_map, doctor_passwords, hospital_passwords



DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS = build_auth_maps()



app = Flask(__name__)
# For production, use a strong, randomly-generated secret loaded from an environment variable.
# You can generate a good key using: python -c 'import secrets; print(secrets.token_hex())'
app.secret_key = os.environ.get("SECRET_KEY", "a-default-fallback-key-for-development")

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key = os.environ.get("CLOUDINARY_API_KEY"),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)
PASSWORD_HASH = os.environ.get("DOCTOR_PASSWORD_HASH")
ALLOWED_EXTENSIONS = {
    'pdf',
    'png', 'jpg', 'jpeg', 'gif',
    'mp4', 'mov', 'webm',
    'txt', 'csv', 'log'
}



def validate_password_version():
    auth = load_auth()

    if session.get("doctor_auth"):
        d = session["doctor_auth"]
        if session.get("password_version") != auth["doctors"][d]["password_updated_at"]:
            session.clear()
            return False

    if session.get("hospital_auth"):
        h = session["hospital_auth"]
        if session.get("password_version") != auth["hospitals"][h]["password_updated_at"]:
            session.clear()
            return False

    return True




def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (
            session.get("doctor")
            or session.get("doctor_auth")
            or session.get("hospital_auth")
        ):
            return redirect(url_for("login"))

        if not validate_password_version():
            flash("Password changed. Please log in again.", "error")
            return redirect(url_for("login"))

        return f(*args, **kwargs)
    return decorated_function






def clean_name(name):


    name = name.strip().upper()   # 👈 convert to UPPERCASE


    """
    Sanitizes a string to be used as a patient name or filename.
    Replaces any character that is not a letter, number, or underscore with an underscore.
    """
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', name)

def allowed_file(filename):
    """Checks if a file's extension is in the ALLOWED_EXTENSIONS set."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_next_index(folder_prefix):
    result = cloudinary.api.resources(
        type="upload",
        prefix=f"{folder_prefix}/",
        max_results=500
    )
    return len(result.get("resources", [])) + 1



def get_latest_patient_upload(patient_data):
    """
    Returns datetime of latest uploaded file for a patient
    """
    if not patient_data["files"]:
        return datetime.min
    return max(f["created_at_dt"] for f in patient_data["files"])






def build_reports_data(prefix=None):
    data = {}

    resources_img = cloudinary.api.resources(
        type="upload",
        resource_type="image",
        prefix=prefix,
        max_results=500
    )

    resources_vid = cloudinary.api.resources(
        type="upload",
        resource_type="video",
        prefix=prefix,
        max_results=500
    )

    resources_raw = cloudinary.api.resources(
        type="upload",
        resource_type="raw",
        prefix=prefix,
        max_results=500
    )


    all_resources = (
        resources_img.get("resources", []) +
        resources_vid.get("resources", []) +
        resources_raw.get("resources", [])
    )


    for res in all_resources:
        public_id = res["public_id"]
        parts = public_id.split("/")

        # hospital / doctor / patient / file
        if len(parts) < 4:
            continue

        hospital, doctor, patient = parts[0], parts[1], parts[2]

        data.setdefault(hospital, {})
        data[hospital].setdefault(doctor, {})
        data[hospital][doctor].setdefault(patient, {
            "files": [],
            "pdf_count": 0,
            "image_count": 0,
            "video_count": 0,
            "text_count": 0,
        })



        upload_date = datetime.strptime(
            res["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).strftime("%b %d, %Y")
        upload_dt = datetime.strptime(res["created_at"], "%Y-%m-%dT%H:%M:%SZ")

        # ---------- SAFE filename handling (FIX for raw files) ----------
        filename = parts[-1]   # base filename from public_id

        # ✅ FIX: force extension for RAW files
        if res["resource_type"] == "raw":
            if not re.search(r"\.(txt|csv|log)$", filename, re.I):
                filename = f"{filename}.txt"

        elif "format" in res:
            if not filename.endswith(f".{res['format']}"):
                filename = f"{filename}.{res['format']}"


        file_obj = {
            "name": filename,
            "date": upload_date,
            "url": res["secure_url"],
            "public_id": public_id,
            "is_pdf": res.get("format") == "pdf",
            "is_video": res["resource_type"] == "video",
            "is_text": res["resource_type"] == "raw",
            "resource_type": res["resource_type"],
            "created_at_dt": upload_dt,

        }
        # ---------------------------------------------------------------



        if file_obj["is_pdf"]:
            data[hospital][doctor][patient]["pdf_count"] += 1

        elif file_obj["is_video"]:
            data[hospital][doctor][patient]["video_count"] += 1

        elif file_obj["is_text"]:
            data[hospital][doctor][patient]["text_count"] += 1

        else:
            data[hospital][doctor][patient]["image_count"] += 1



        if file_obj["is_pdf"]:
            file_obj["thumbnail_url"] = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="image",
                format="jpg",
                page=1,
                secure=True
            )[0]
        elif file_obj["is_video"]:
            file_obj["thumbnail_url"] = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="video",
                format="jpg",
                secure=True
            )[0]

        data[hospital][doctor][patient]["files"].append(file_obj)

    # ==================================================
    # 🔥 SORT PATIENTS BY LATEST UPLOAD (NEWEST FIRST)
    # ==================================================
    for hospital, doctors in data.items():
        for doctor, patients in doctors.items():
            doctors[doctor] = dict(
                sorted(
                    patients.items(),
                    key=lambda item: get_latest_patient_upload(item[1]),
                    reverse=True
                )
            )

            # ==================================================
    # 3️⃣ SORT DOCTOR + HOSPITAL BY LATEST UPLOAD
    # ==================================================

    def get_latest_doctor_upload(patients):
        if not patients:
            return datetime.min
        return max(get_latest_patient_upload(p) for p in patients.values())

    def get_latest_hospital_upload(doctors):
        if not doctors:
            return datetime.min
        return max(get_latest_doctor_upload(p) for p in doctors.values())

    # ============================
    # SORT LEVELS (NEWEST FIRST)
    # ============================

    # 1️⃣ PATIENTS (you already had, keep this)
    for hospital, doctors in data.items():
        for doctor, patients in doctors.items():
            data[hospital][doctor] = dict(
                sorted(
                    patients.items(),
                    key=lambda item: get_latest_patient_upload(item[1]),
                    reverse=True
                )
            )

    # 2️⃣ DOCTORS
    for hospital, doctors in data.items():
        data[hospital] = dict(
            sorted(
                doctors.items(),
                key=lambda item: get_latest_doctor_upload(item[1]),
                reverse=True
            )
        )

    # 3️⃣ HOSPITALS
    data = dict(
        sorted(
            data.items(),
            key=lambda item: get_latest_hospital_upload(item[1]),
            reverse=True
        )
    )


    # ==================================================
    # AGGREGATE COUNTS (Hospital & Doctor)
    # ==================================================
    for hospital, doctors in data.items():
        hospital_doctors = 0
        hospital_patients = 0
        hospital_files = 0

        for doctor, patients in doctors.items():
            hospital_doctors += 1

            doctor_patients = 0
            doctor_files = 0

            for patient_data in patients.values():
                doctor_patients += 1
                doctor_files += len(patient_data["files"])

            # attach meta to doctor
            patients["_meta"] = {
                "patient_count": doctor_patients,
                "file_count": doctor_files
            }

            hospital_patients += doctor_patients
            hospital_files += doctor_files

        # attach meta to hospital
        doctors["_meta"] = {
            "doctor_count": hospital_doctors,
            "patient_count": hospital_patients,
            "file_count": hospital_files
        }


    return data





@app.route("/upload/h/<hospital_code>", methods=["GET", "POST"])
def upload_hospital(hospital_code):
    # 1️⃣ Validate hospital
    if hospital_code not in set(DOCTOR_MAP.values()):
        return "Invalid hospital upload link", 404
    
    # ✅ make title usable in BOTH GET + POST
    display_name = hospital_code.replace("_", " ").title()

    if request.method == "POST":
        patient = request.form.get("patient", "").strip()
        if not patient:
            return jsonify({"error": "Patient name is required."}), 400

        files = request.files.getlist("report")
        if not files or all(f.filename == "" for f in files):
            return jsonify({"error": "No files selected."}), 400

        patient_folder = clean_name(patient)

        # ✅ OPTION A — HOSPITAL HOLDING BUCKET
        base_folder = f"{hospital_code}/_unassigned/{patient_folder}"
        current_index = get_next_index(base_folder)

        uploaded = 0

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                public_id = f"{patient_folder}_{current_index}"

                cloudinary.uploader.upload(
                    f,
                    folder=base_folder,
                    public_id=public_id,
                    resource_type="auto",
                    access_mode="public",
                )

                current_index += 1
                uploaded += 1

        return jsonify({
            "success": f"{uploaded} file(s) uploaded for {display_name}."
        })

    # GET → same upload UI
    display_name = hospital_code.replace("_", " ").title()

    return render_template(
        "index.html",
        upload_title=f"📤 Upload Files to {display_name}"
    )





@app.route("/", methods=["GET", "POST"])
def index():
    """
    Handles the main page, which includes the file upload form.
    On POST request, it processes and saves uploaded reports for a patient.
    """
    error = None
    if request.method == "POST":
        patient = request.form.get("patient", "").strip()
        if not patient:
            return jsonify({"error": "Patient name is required."}), 400

        files = request.files.getlist("report")
        if not files or all(f.filename == '' for f in files):
             return jsonify({"error": "No files selected."}), 400
        
        patient_folder = clean_name(patient)
        if not patient_folder:
            # This case handles if the name consists only of invalid characters
            return jsonify({"error": "Invalid patient name provided."}), 400

        base_folder = f"unassign_hospital/patient_in_unassigned_hospital/{patient_folder}"
        current_index = get_next_index(base_folder)

        uploaded_count = 0
        errors = []

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                # Create a sequential public_id like 'patient-name_1', 'patient-name_2'
                public_id = f"{patient_folder}_{current_index}"
                
                cloudinary.uploader.upload(
                    f,
                    folder=base_folder,

                    public_id=public_id,
                    resource_type="auto",
                    access_mode="public"   # Ensure PDFs are publicly accessible
                )
                current_index += 1
                uploaded_count += 1
            elif f and f.filename:
                # Collect errors for files that are not allowed
                errors.append(f"File '{secure_filename(f.filename)}' has an unsupported type.")

        if uploaded_count > 0:
            success_message = f"{uploaded_count} file(s) uploaded for {patient}."
            return jsonify({"success": success_message})

    return render_template(
    "index.html",
    upload_title="📤 Uploading For 🌐"
)





@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    target = session.get("login_target")

    if request.method == "POST":
        password = request.form.get("password", "")

        # 1️⃣ Targeted login
        if target:
            
            if target.startswith("doctor:"):
                doctor_code = target.split(":")[1]
                if doctor_code in DOCTOR_PASSWORDS and check_password_hash(
                    DOCTOR_PASSWORDS[doctor_code], password
                ):
                    auth = load_auth()
                    session.clear()
                    session["doctor_auth"] = doctor_code
                    session["login_role"] = "doctor"
                    session["password_version"] = auth["doctors"][doctor_code]["password_updated_at"]
                    return redirect(url_for("reports_doctor", doctor_code=doctor_code))



                error = "Invalid doctor password"

            elif target.startswith("hospital:"):
                hospital_code = target.split(":")[1]
                if hospital_code in HOSPITAL_PASSWORDS and check_password_hash(
                    HOSPITAL_PASSWORDS[hospital_code], password
                ):
                    session.clear()
                    session["hospital_auth"] = hospital_code
                    session["login_role"] = "hospital"
                    return redirect(url_for("reports_hospital", hospital_code=hospital_code))

                error = "Invalid hospital password"

        # 2️⃣ Fallback (direct login page access)
        else:
            for doctor_code, hash_val in DOCTOR_PASSWORDS.items():
                if check_password_hash(hash_val, password):
                    auth = load_auth()
                    session.clear()
                    session["doctor_auth"] = doctor_code
                    session["login_role"] = "doctor"
                    session["password_version"] = auth["doctors"][doctor_code]["password_updated_at"]
                    return redirect(url_for("reports_doctor", doctor_code=doctor_code))



            for hospital_code, hash_val in HOSPITAL_PASSWORDS.items():
                if check_password_hash(hash_val, password):
                    auth = load_auth()
                    session.clear()
                    session["hospital_auth"] = hospital_code
                    session["login_role"] = "hospital"
                    session["password_version"] = auth["hospitals"][hospital_code]["password_updated_at"]
                    return redirect(url_for("reports_hospital", hospital_code=hospital_code))



            if PASSWORD_HASH and check_password_hash(PASSWORD_HASH, password):
                session.clear()
                session["doctor"] = True
                session["login_role"] = "admin"
                return redirect(url_for("reports"))

            error = "Invalid password"

    # ✅ ALWAYS RETURN ON GET OR FAILED POST
    return render_template(
        "login.html",
        error=error,
        role=session.get("login_role"),
        target=target,
    )






@app.route("/logout")
def logout():
    role = session.get("login_role")   # ✅ read BEFORE clearing
    session.clear()

    if role == "doctor":
        flash("Doctor logged out successfully 👨‍⚕️", "success")
    elif role == "hospital":
        flash("Hospital logged out successfully 🏥", "success")
    elif role == "admin":
        flash("Admin logged out successfully 🛡️", "success")
    else:
        flash("Logged out successfully 🐦‍🔥", "success")

    return redirect(url_for("login"))   # ✅ ALWAYS return






@app.route("/upload/d/<doctor_code>", methods=["GET", "POST"])
def upload_doctor(doctor_code):
    doctor_code = doctor_code.lower()

    # 1️⃣ Validate doctor
    if doctor_code not in DOCTOR_MAP:
        return "Invalid upload link", 404

    hospital = DOCTOR_MAP[doctor_code]

    # ✅ make doctor display name available to BOTH POST + GET
    display_name = doctor_code.replace("_", " ").title()

    # 2️⃣ Handle upload (same UX as /)
    if request.method == "POST":
        patient = request.form.get("patient", "").strip()
        if not patient:
            return jsonify({"error": "Patient name is required."}), 400

        files = request.files.getlist("report")
        if not files or all(f.filename == "" for f in files):
            return jsonify({"error": "No files selected."}), 400

        patient_folder = clean_name(patient)

        base_folder = f"{hospital}/{doctor_code}/{patient_folder}"
        current_index = get_next_index(base_folder)

        uploaded = 0

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                public_id = f"{patient_folder}_{current_index}"

                cloudinary.uploader.upload(
                    f,
                    folder=base_folder,
                    public_id=public_id,
                    resource_type="auto",
                    access_mode="public",
                )

                current_index += 1
                uploaded += 1

        return jsonify({
            "success": f"{uploaded} file(s) uploaded for {display_name}."
        })

    # 3️⃣ GET → reuse existing upload UI
    # display_name = f"Dr {doctor_code.replace('dr_', '').title()}"
    display_name = doctor_code.replace("_", " ").title()


    return render_template(
        "index.html",
        upload_title=f"📤 Uploading Files for {display_name}"
    )



@app.route("/reports/h/<hospital_code>")
def reports_hospital(hospital_code):
    hospital_code = hospital_code.lower()

    if hospital_code not in HOSPITAL_PASSWORDS:
        return "Invalid hospital", 404

    # 🔐 not logged in
    if not session.get("hospital_auth"):
        session["login_target"] = f"hospital:{hospital_code}"
        return redirect(url_for("login"))

    # 🔐 wrong hospital logged in
    if session["hospital_auth"] != hospital_code:
        session.clear()
        session["login_target"] = f"hospital:{hospital_code}"
        return redirect(url_for("login"))

    prefix = f"{hospital_code}/"
    data = build_reports_data(prefix=prefix)

    return render_template(
        "reports.html",
        data=data,
        search="",
        view="hospital"
    )





@app.route("/reports")
@login_required
def reports():
    data = build_reports_data(prefix=None)  # show all
    return render_template(
        "reports.html",
        data=data,
        search="",
        view="all"
    )


@app.route("/reports/data")
@login_required
def reports_data():
    if not session.get("doctor"):
        flash("Admin access only", "error")
        return redirect(url_for("reports"))

    auth = load_auth()   # ✅ READ FULL AUTH FILE

    return render_template(
        "reports_data.html",
        auth=auth
    )



@app.route("/api/add-entity", methods=["POST"])
@login_required
def api_add_entity():
    if not session.get("doctor"):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    entity_type = data.get("type")     # hospital | doctor
    entity_id = data.get("id")         # code
    hospital = data.get("hospital")    # only for doctor
    password = data.get("password")

    if not all([entity_type, entity_id, password]):
        return jsonify({"error": "Missing fields"}), 400

    auth = load_auth()
    now = int(time.time())

    if entity_type == "hospital":
        if entity_id in auth["hospitals"]:
            return jsonify({"error": "Hospital already exists"}), 400

        auth["hospitals"][entity_id] = {
            "password_hash": generate_password_hash(password),
            "password_updated_at": now
        }

    elif entity_type == "doctor":
        if not hospital or hospital not in auth["hospitals"]:
            return jsonify({"error": "Invalid hospital"}), 400

        if entity_id in auth["doctors"]:
            return jsonify({"error": "Doctor already exists"}), 400

        auth["doctors"][entity_id] = {
            "hospital": hospital,
            "password_hash": generate_password_hash(password),
            "password_updated_at": now
        }

    else:
        return jsonify({"error": "Invalid type"}), 400

    save_auth(auth)

    global DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS
    DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS = build_auth_maps()

    return jsonify({"success": True})


@app.route("/api/delete-entity", methods=["POST"])
@login_required
def api_delete_entity():
    if not session.get("doctor"):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    entity_type = data.get("type")
    entity_id = data.get("id")

    auth = load_auth()

    if entity_type == "doctor":
        if entity_id not in auth["doctors"]:
            return jsonify({"error": "Doctor not found"}), 404

        hospital = auth["doctors"][entity_id]["hospital"]

        # 🔥 DELETE ALL CLOUDINARY FILES
        cloudinary.api.delete_resources_by_prefix(
            f"{hospital}/{entity_id}/"
        )

        # 🔥 DELETE EMPTY FOLDERS (important)
        cloudinary.api.delete_folder(f"{hospital}/{entity_id}")

        # ❌ DELETE FROM AUTH
        del auth["doctors"][entity_id]


    elif entity_type == "hospital":
        if entity_id not in auth["hospitals"]:
            return jsonify({"error": "Hospital not found"}), 404

        # 🔥 DELETE ALL CLOUDINARY FILES
        cloudinary.api.delete_resources_by_prefix(f"{entity_id}/")
        cloudinary.api.delete_folder(entity_id)

        # ❌ REMOVE DOCTORS
        auth["doctors"] = {
            k: v for k, v in auth["doctors"].items()
            if v["hospital"] != entity_id
        }

        # ❌ REMOVE HOSPITAL
        del auth["hospitals"][entity_id]


    else:
        return jsonify({"error": "Invalid type"}), 400

    save_auth(auth)

    global DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS
    DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS = build_auth_maps()

    return jsonify({"success": True})




@app.route("/reports/d/<doctor_code>")
def reports_doctor(doctor_code):
    doctor_code = doctor_code.lower()

    if doctor_code not in DOCTOR_MAP:
        return "Invalid doctor", 404

    # 🔐 not logged in OR wrong doctor
    if session.get("doctor_auth") != doctor_code:
        session.pop("doctor_auth", None)
        session["login_target"] = f"doctor:{doctor_code}"
        return redirect(url_for("login"))

    hospital = DOCTOR_MAP[doctor_code]
    prefix = f"{hospital}/{doctor_code}/"
    data = build_reports_data(prefix=prefix)

    return render_template(
        "reports.html",
        data=data,
        search="",
        view="doctor"
    )







@app.route("/delete", methods=["POST"])
def delete_file():
    if not (session.get("doctor") or session.get("doctor_auth") or session.get("hospital_auth")):
        return redirect(url_for("login"))

    public_id = request.form.get("public_id")
    if public_id:
        resource_type = request.form.get("resource_type", "image")
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        flash("Report was deleted successfully.", "success")
    else:
        flash("Could not delete report: missing ID.", "error")

    return redirect(request.referrer or url_for("reports"))








@app.route("/download-patient/<hospital>/<doctor>/<patient>")
@login_required
def download_patient_zip(hospital, doctor, patient):
    prefix = f"{hospital}/{doctor}/{patient}/"

    resources = []
    for rt in ("image", "video", "raw"):
        res = cloudinary.api.resources(
            type="upload",
            resource_type=rt,
            prefix=prefix,
            max_results=500
        )
        resources += res.get("resources", [])

    if not resources:
        flash("No files found for this patient.", "error")
        return redirect(url_for("reports"))

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in resources:
            try:
                r = requests.get(f["secure_url"], timeout=20)
                r.raise_for_status()

                name = f["public_id"].split("/")[-1]

                if f["resource_type"] == "raw":
                    if "." not in name:
                        name += ".txt"
                elif "format" in f:
                    name += f".{f['format']}"

                zipf.writestr(name, r.content)

            except Exception:
                continue

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{patient}_RECORDS.zip",
        mimetype="application/zip"
    )




@app.route("/download-hospital/<hospital>")
@login_required
def download_hospital_zip(hospital):
    prefix = f"{hospital}/"

    resources = []
    for rt in ("image", "video", "raw"):
        res = cloudinary.api.resources(
            type="upload",
            resource_type=rt,
            prefix=prefix,
            max_results=500
        )
        resources += res.get("resources", [])

    if not resources:
        flash("No files found for this hospital.", "error")
        return redirect(url_for("reports"))

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in resources:
            try:
                r = requests.get(f["secure_url"], timeout=20)
                r.raise_for_status()

                rel_path = f["public_id"].replace(prefix, "")

                if f["resource_type"] == "raw":
                    if "." not in rel_path:
                        rel_path += ".txt"
                elif "format" in f:
                    rel_path += f".{f['format']}"

                zipf.writestr(rel_path, r.content)

            except Exception:
                continue

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{hospital}_ALL_RECORDS.zip",
        mimetype="application/zip"
    )





@app.route("/download-doctor/<hospital>/<doctor>")
@login_required
def download_doctor_zip(hospital, doctor):
    prefix = f"{hospital}/{doctor}/"

    resources = []
    for rt in ("image", "video", "raw"):
        res = cloudinary.api.resources(
            type="upload",
            resource_type=rt,
            prefix=prefix,
            max_results=500
        )
        resources += res.get("resources", [])

    if not resources:
        flash("No files found for this doctor.", "error")
        return redirect(url_for("reports"))

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in resources:
            try:
                r = requests.get(f["secure_url"], timeout=20)
                r.raise_for_status()

                rel_path = f["public_id"].replace(prefix, "")

                if f["resource_type"] == "raw":
                    if "." not in rel_path:
                        rel_path += ".txt"
                elif "format" in f:
                    rel_path += f".{f['format']}"

                zipf.writestr(rel_path, r.content)

            except Exception:
                continue

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{doctor}_ALL_PATIENTS.zip",
        mimetype="application/zip"
    )






@app.route("/api/change-password", methods=["POST"])
@login_required
def api_change_password():
    if not session.get("doctor"):
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json()
    entity_type = data.get("type")   # "doctor" or "hospital"
    entity_id = data.get("id")
    new_password = data.get("new_password")

    if not all([entity_type, entity_id, new_password]):
        return jsonify({"error": "Missing fields"}), 400

    auth = load_auth()
    now = int(time.time())

    if entity_type == "doctor":
        if entity_id not in auth["doctors"]:
            return jsonify({"error": "Doctor not found"}), 404

        auth["doctors"][entity_id]["password_hash"] = generate_password_hash(new_password)
        auth["doctors"][entity_id]["password_updated_at"] = now

    elif entity_type == "hospital":
        if entity_id not in auth["hospitals"]:
            return jsonify({"error": "Hospital not found"}), 404

        auth["hospitals"][entity_id]["password_hash"] = generate_password_hash(new_password)
        auth["hospitals"][entity_id]["password_updated_at"] = now

    else:
        return jsonify({"error": "Invalid type"}), 400

    save_auth(auth)

    # 🔁 refresh in-memory maps
    global DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS
    DOCTOR_MAP, DOCTOR_PASSWORDS, HOSPITAL_PASSWORDS = build_auth_maps()

    return jsonify({"success": True})





@app.route("/download-raw/<path:public_id>")
@login_required
def download_raw(public_id):
    # Fetch file info
    res = cloudinary.api.resource(public_id, resource_type="raw")

    file_url = res["secure_url"]
    filename = public_id.split("/")[-1]

    # force extension
    if not re.search(r"\.(txt|csv|log)$", filename, re.I):
        filename += ".txt"

    response = requests.get(file_url, timeout=20)
    response.raise_for_status()

    return send_file(
        io.BytesIO(response.content),
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain"
    )



# =========================
# PUBLIC SHARE VIEW ROUTE
# =========================
@app.route("/share/<token>")
def shared_view(token):
    shares = load_shares()

    if token not in shares["tokens"]:
        return "Invalid or expired link", 404

    data = shares["tokens"][token]

    # Expiry check
    if time.time() > data["expires"]:
        del shares["tokens"][token]
        save_shares(shares)
        return "Link expired", 410

    # Build view-only data same as reports()
    hospital = data["hospital"]

    if data["scope"] == "hospital":
        dataset = build_data(hospital=hospital)

    elif data["scope"] == "doctor":
        dataset = build_data(hospital=hospital, doctor=data["doctor"])

    else:
        dataset = build_data(
            hospital=hospital,
            doctor=data["doctor"],
            patient=data["patient"]
        )

    return render_template(
        "reports.html",
        data=dataset,
        view="share",
        readonly=True
    )




# =========================
# DELETE PATIENT
# =========================
@app.post("/api/patient/delete")
def api_delete_patient():
    data = request.get_json()

    hospital = data.get("hospital")
    doctor = data.get("doctor")
    patient = data.get("patient")

    if not (hospital and doctor and patient):
        return jsonify(ok=False, error="missing")

    prefix = f"{hospital}/{doctor}/{patient}"

    try:
        # ---- DELETE ALL FILES FROM CLOUDINARY ----
        cloudinary.api.delete_resources_by_prefix(prefix)

        # ---- DELETE FOLDER STRUCTURE ----
        try:
            cloudinary.api.delete_folder(prefix)
        except:
            pass

        return jsonify(ok=True)

    except Exception as e:
        print("DELETE FAILED:", e)
        return jsonify(ok=False)













# =========================
# MOVE PATIENT
# =========================
@app.post("/api/patient/move")
def api_move_patient():
    data = request.get_json()

    from_h = data.get("from_hospital")
    from_d = data.get("from_doctor")
    patient = data.get("patient")

    to_h = data.get("to_hospital")
    to_d = data.get("to_doctor")
    new_name = data.get("new_name")
    merge = data.get("merge", False)

    old_prefix = f"{from_h}/{from_d}/{patient}"
    new_prefix = f"{to_h}/{to_d}/{new_name}"

    try:
        # check conflict
        existing = cloudinary.api.resources(
            type="upload",
            prefix=new_prefix,
            max_results=1
        )

        if existing["resources"] and not merge:
            return jsonify(conflict=True)

        files = cloudinary.api.resources(
            type="upload",
            prefix=old_prefix,
            max_results=500
        )

        for f in files["resources"]:
            old_id = f["public_id"]
            new_id = old_id.replace(old_prefix, new_prefix, 1)

            cloudinary.uploader.rename(
                old_id,
                new_id,
                overwrite=True
            )

        try:
            cloudinary.api.delete_folder(old_prefix)
        except:
            pass

        return jsonify(ok=True)

    except Exception as e:
        print("MOVE FAILED:", e)
        return jsonify(ok=False)


# =========================
# RENAME PATIENT
# =========================
@app.post("/api/patient/rename")
def api_rename_patient():
    data = request.get_json()

    hospital = data.get("hospital")
    doctor = data.get("doctor")
    old_name = data.get("old_name")
    new_name = data.get("new_name")
    merge = data.get("merge", False)

    if not (hospital and doctor and old_name and new_name):
        return jsonify(ok=False, error="missing")

    old_prefix = f"{hospital}/{doctor}/{old_name}"
    new_prefix = f"{hospital}/{doctor}/{new_name}"

    try:
        # Check if new already exists
        existing = cloudinary.api.resources(
            type="upload",
            prefix=new_prefix,
            max_results=1
        )

        if existing["resources"] and not merge:
            return jsonify(conflict=True)

        # ===== RENAME (MOVE) ALL FILES =====
        files = cloudinary.api.resources(
            type="upload",
            prefix=old_prefix,
            max_results=500
        )

        for f in files["resources"]:
            old_id = f["public_id"]
            # Replace prefix
            new_id = old_id.replace(old_prefix, new_prefix, 1)

            cloudinary.uploader.rename(
                old_id,
                new_id,
                overwrite=True
            )

        try:
            cloudinary.api.delete_folder(old_prefix)
        except:
            pass

        return jsonify(ok=True)

    except Exception as e:
        print("RENAME FAILED:", e)
        return jsonify(ok=False)











# =========================
# GENERATE SHARE LINK
# =========================
@app.route("/api/share/create", methods=["POST"])
def api_share_create():
    req = request.json

    scope = req["scope"]
    hospital = req["hospital"]
    doctor = req.get("doctor")
    patient = req.get("patient")

    if not has_access(hospital, doctor):
        return jsonify({"error": "No access"}), 403

    expiry_hours = req.get("expiry_hours", 24)

    token = os.urandom(6).hex()

    shares = load_shares()

    shares["tokens"][token] = {
        "scope": scope,
        "hospital": hospital,
        "doctor": doctor,
        "patient": patient,
        "expires": time.time() + (expiry_hours * 3600)
    }

    save_shares(shares)

    return jsonify({
        "ok": True,
        "token": token,
        "url": f"{request.host_url}share/{token}"
    })




# ✅ TEMP DEV LOGIN (REMOVE BEFORE PRODUCTION)
@app.route("/dev-login")
def dev_login():
    session["doctor"] = True
    return redirect(url_for("reports"))





if __name__ == "__main__":
    # The development server is not for production. A WSGI server like Gunicorn will run the app.
    app.run(debug=True, host='0.0.0.0')
