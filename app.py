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

def get_next_index(patient_folder):
    """
    Counts existing files in a Cloudinary folder to determine the next file index.
    """
    result = cloudinary.api.resources(
        type="upload",
        prefix=f"{patient_folder}/",
        max_results=500  # Adjust if a patient might have more files
    )
    return len(result.get("resources", [])) + 1

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


@app.route("/reports")
@login_required
def reports():
    """
    Displays a list of all patients and their reports.
    Includes a search functionality to filter patients by name.
    This route requires the user to be logged in.
    """
    search = request.args.get("search", "").lower()
    data = {}

    # More efficient: Search directly and group results in Python.
    # This allows searching by patient name (folder) or filename.
    expression = None
    if search:
        # Search in folder (patient name) OR filename
        expression = f"folder:*{search}* OR filename:*{search}*"

    # Fetch images and PDFs (resource_type="image")
    resources_img = cloudinary.api.resources(
        type="upload",
        resource_type="image",
        max_results=500,
        expression=expression
    )

    # Fetch videos (resource_type="video")
    resources_vid = cloudinary.api.resources(
        type="upload",
        resource_type="video",
        max_results=500,
        expression=expression
    )

    # Merge the results from both queries
    all_resources = (
        resources_img.get("resources", []) + resources_vid.get("resources", [])
    )

    for res in all_resources:
        public_id = res["public_id"]

        # Skip root-level files by checking for a separator in the public_id
        if "/" not in public_id:
            continue  

        # The folder is the first part of the public_id
        patient_name = public_id.split("/")[0]

        # Initialize patient entry if not exists
        if patient_name not in data:
            data[patient_name] = {
        "files": [],    
        "pdf_count": 0,
        "image_count": 0,
        "video_count": 0,
    }

        upload_date = datetime.strptime(
            res["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).strftime('%b %d, %Y')

        file_obj = {
            "name": f"{public_id.split('/')[-1]}.{res['format']}",
            "date": upload_date,
            "url": res["secure_url"],
            "public_id": public_id,
            "is_pdf": res["format"] == "pdf",
            "is_video": res["resource_type"] == "video",
            "resource_type": res["resource_type"]
        }

        if file_obj["is_pdf"]:
            data[patient_name]["pdf_count"] += 1
        elif file_obj["is_video"]:
            data[patient_name]["video_count"] += 1
        else:
            data[patient_name]["image_count"] += 1

        # If it's a PDF, generate a thumbnail URL for the first page
        if file_obj.get("is_pdf"):
            file_obj["thumbnail_url"] = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="image", # PDFs are treated as images for transformations
                format="jpg",          # Convert to JPG for the thumbnail
                page=1,                # Get the first page
                secure=True
            )[0]
        # If it's a video, generate a thumbnail image
        elif file_obj.get("is_video"):
            file_obj["thumbnail_url"] = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="video",
                transformation=[{'width': 400, 'crop': 'limit'}],
                format="jpg",
                secure=True
            )[0]

        # Use setdefault for cleaner grouping
        data[patient_name]["files"].append(file_obj)

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
