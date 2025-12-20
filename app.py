from flask import Flask, render_template, request, redirect, send_from_directory, session, url_for, flash, jsonify
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import re

import io
import zipfile
import requests
from flask import send_file

import cloudinary
import cloudinary.uploader
import cloudinary.api


DOCTOR_MAP = {
    "dr_rutu": "apollo_mumbai",
    "dr_omkar": "apollo_mumbai",
}



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
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webm'}

def login_required(f):
    """
    Decorator to ensure a user is logged in before accessing a route.
    Redirects to the login page if the user is not in the session.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("doctor"):
            return redirect(url_for('index'))
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



@app.route("/upload/h/<hospital_code>", methods=["GET", "POST"])
def upload_hospital(hospital_code):
    # 1️⃣ Validate hospital
    if hospital_code not in set(DOCTOR_MAP.values()):
        return "Invalid hospital upload link", 404

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
            "success": f"{uploaded} file(s) uploaded for {patient}."
        })

    # GET → same upload UI
    return render_template("index.html")




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

        current_index = get_next_index(patient_folder)
        uploaded_count = 0
        errors = []

        for f in files:
            if f and f.filename and allowed_file(f.filename):
                # Create a sequential public_id like 'patient-name_1', 'patient-name_2'
                public_id = f"{patient_folder}_{current_index}"
                
                cloudinary.uploader.upload(
                    f,
                    folder=patient_folder,
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

    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Handles the doctor's login. On successful login, the user is added
    to the session and redirected to the reports page.
    """
    error = None
    if request.method == "POST":
        # Ensure the hash is set in the environment
        if not PASSWORD_HASH:
            error = "Application is not configured for login."
        # Check the submitted password against the stored hash
        elif check_password_hash(PASSWORD_HASH, request.form.get("password", "")):
            session["doctor"] = True
            return redirect(url_for('reports'))
        else:
            error = "Invalid password."
    
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    """Clears the session to log the user out."""
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('index'))

@app.route("/upload/d/<doctor_code>", methods=["GET", "POST"])
def upload_doctor(doctor_code):
    doctor_code = doctor_code.lower()

    # 1️⃣ Validate doctor
    if doctor_code not in DOCTOR_MAP:
        return "Invalid upload link", 404

    hospital = DOCTOR_MAP[doctor_code]

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
            "success": f"{uploaded} file(s) uploaded for {patient}."
        })

    # 3️⃣ GET → reuse existing upload UI
    return render_template("index.html")


@app.route("/reports")
@login_required
def reports():
    search = request.args.get("search", "").lower()
    data = {}

    # ❌ REMOVE expression usage for now
    resources_img = cloudinary.api.resources(
    type="upload",
    resource_type="image",
    prefix="apollo_mumbai/",
    max_results=500
    )

    resources_vid = cloudinary.api.resources(
        type="upload",
        resource_type="video",
        prefix="apollo_mumbai/",
        max_results=500
    )


    all_resources = (
        resources_img.get("resources", []) +
        resources_vid.get("resources", [])
    )

    for res in all_resources:
        public_id = res["public_id"]
        parts = public_id.split("/")

        # Expect: hospital/doctor_or__unassigned/patient/file
        if len(parts) < 4:
            continue

        hospital = parts[0]
        doctor = parts[1]      # dr_rutu OR _unassigned
        patient = parts[2]

        # ---- INIT STRUCTURE ----
        data.setdefault(hospital, {})
        data[hospital].setdefault(doctor, {})
        data[hospital][doctor].setdefault(patient, {
            "files": [],
            "pdf_count": 0,
            "image_count": 0,
            "video_count": 0,
        })

        upload_date = datetime.strptime(
            res["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).strftime("%b %d, %Y")

        file_obj = {
            "name": f"{parts[-1]}.{res['format']}",
            "date": upload_date,
            "url": res["secure_url"],
            "public_id": public_id,
            "is_pdf": res["format"] == "pdf",
            "is_video": res["resource_type"] == "video",
            "resource_type": res["resource_type"],
        }

        if file_obj["is_pdf"]:
            data[hospital][doctor][patient]["pdf_count"] += 1
        elif file_obj["is_video"]:
            data[hospital][doctor][patient]["video_count"] += 1
        else:
            data[hospital][doctor][patient]["image_count"] += 1

        # ---- THUMBNAILS ----
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

    return render_template("reports.html", data=data, search=search)




@app.route("/delete", methods=["POST"])
@login_required
def delete_file():
    """
    Deletes a specific report file from Cloudinary.
    Requires the user to be logged in.
    """
    public_id = request.form.get("public_id")
    if public_id:
        # Deleting requires the public_id
        # We must also specify the resource_type for videos
        resource_type = request.form.get("resource_type", "image")
        cloudinary.uploader.destroy(
            public_id, resource_type=resource_type
        )
        flash(f"Report was deleted successfully.", "success")
    else:
        flash("Could not delete report: missing ID.", "error")
        
    return redirect(url_for('reports'))







@app.route("/download-patient/<patient>")
@login_required
def download_patient_zip(patient):
    """
    Download ALL files of a patient as a ZIP
    """
    patient = clean_name(patient)

    # Get all files for this patient from Cloudinary
    result_img = cloudinary.api.resources(
        type="upload",
        resource_type="image",
        prefix=f"{patient}/",
        max_results=500
    )

    result_vid = cloudinary.api.resources(
        type="upload",
        resource_type="video",
        prefix=f"{patient}/",
        max_results=500
    )

    all_files = result_img.get("resources", []) + result_vid.get("resources", [])

    if not all_files:
        flash("No files found for this patient.", "error")
        return redirect(url_for("reports"))

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in all_files:
            file_url = file["secure_url"]
            filename = f"{file['public_id'].split('/')[-1]}.{file['format']}"

            try:
                response = requests.get(file_url, timeout=20)
                response.raise_for_status()
                zipf.writestr(filename, response.content)
            except Exception:
                continue

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{patient}_reports.zip"
    )






if __name__ == "__main__":
    # The development server is not for production. A WSGI server like Gunicorn will run the app.
    app.run(debug=True, host='0.0.0.0')
