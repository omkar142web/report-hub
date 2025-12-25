# 🩺 Report Hub

Report Hub is a Flask-based medical report management system designed to streamline the process of uploading, organizing, and accessing patient records. It connects patients, doctors, and hospitals through a secure, cloud-based interface powered by Cloudinary.

## ✨ Key Features

### 📂 File Management

- **Multi-Format Support:** Upload PDFs, Images (PNG, JPG, GIF), Videos (MP4, MOV, WEBM), and Raw Data (TXT, CSV, LOG).
- **Cloud Storage:** All files are securely stored and managed via **Cloudinary**.
- **Smart Organization:** Files are automatically sorted by Hospital > Doctor > Patient.
- **Public & Private Uploads:**
  - General public upload portal.
  - Dedicated upload links for specific Hospitals (`/upload/h/<code>`) and Doctors (`/upload/d/<code>`).

### 🔐 Role-Based Access

- **Admin:** Full access to all hospitals, doctors, and patient records.
- **Hospital:** Access to all doctors and patients associated with the specific hospital.
- **Doctor:** Access only to their specific patient list.
- **Security:** Secure password hashing (Werkzeug) and session management with version control to invalidate sessions on password changes.

### 💻 User Interface

- **Modern Design:** Dark mode UI with glassmorphism effects and responsive layout.
- **Live Search:** Real-time filtering of patients and files.
- **File Previews:** Built-in modal previews for images and PDFs; video player for media files.
- **Bulk Actions:** Download all records for a Patient, Doctor, or Hospital as a ZIP file.

## 🛠️ Tech Stack

- **Backend:** Python, Flask
- **Storage:** Cloudinary API
- **Frontend:** HTML5, CSS3 (Custom variables, Flexbox/Grid), JavaScript (Vanilla)
- **Utilities:** `requests`, `zipfile`, `io`

## 🚀 Installation & Setup

### 1. Prerequisites

- Python 3.8+
- A Cloudinary account

### 2. Environment Variables

Create a `.env` file or set the following system environment variables:

```bash
export CLOUDINARY_CLOUD_NAME="your_cloud_name"
export CLOUDINARY_API_KEY="your_api_key"
export CLOUDINARY_API_SECRET="your_api_secret"
export SECRET_KEY="your_flask_secret_key"
export DOCTOR_PASSWORD_HASH="hash_for_admin_login"
```

### 3. Data Configuration

Ensure the `data/` directory exists and contains an `auth.json` file for managing credentials.

**Structure of `data/auth.json`:**

```json
{
  "hospitals": {
    "city_hospital": {
      "password_hash": "scrypt:32768:8:1$...",
      "password_updated_at": 1715000000
    }
  },
  "doctors": {
    "dr_smith": {
      "hospital": "city_hospital",
      "password_hash": "scrypt:32768:8:1$...",
      "password_updated_at": 1715000000
    }
  }
}
```

### 4. Running the Application

```bash
# Install dependencies (ensure you have a requirements.txt or install manually)
pip install flask cloudinary requests werkzeug

# Run the app
python app.py
```

The application will start at `http://0.0.0.0:5000`.

## 📖 Usage Guide

### Uploading Reports

- **General Upload:** Visit the homepage `/`. Enter the patient's name and drag & drop files.
- **Targeted Upload:** Use specific URLs like `/upload/h/city_hospital` to upload directly to a hospital's unassigned folder, or `/upload/d/dr_smith` for a specific doctor.

### Viewing Reports (Dashboard)

1.  Navigate to `/login`.
2.  Enter your password. The system automatically detects if you are an Admin, Hospital, or Doctor based on the password hash.
3.  **Dashboard Features:**
    - **Expand/Collapse:** Click on Hospital or Doctor names to toggle views.
    - **Search:** Type in the search bar to filter patients or filenames instantly.
    - **Download:** Click the "Download" button on any card (Patient/Doctor/Hospital) to generate a ZIP archive.
    - **Delete:** Use the delete button on specific files to remove them from Cloudinary.

### API Endpoints

The application exposes internal APIs for managing entities (requires authentication):

- `POST /api/add-entity`: Create new Hospital or Doctor credentials.
- `POST /api/delete-entity`: Remove an entity and **delete all associated files** from Cloudinary.
- `POST /api/change-password`: Update credentials.

## 📂 Project Structure

```
report_hub/
├── app.py                 # Main application logic & routes
├── data/
│   └── auth.json          # JSON database for users (Hospitals/Doctors)
├── static/
│   ├── style.css          # Main stylesheet (Dark theme)
│   ├── upload.js          # Drag & drop upload logic
│   └── toast.js           # Notification logic
├── templates/
│   ├── index.html         # Upload page
│   ├── login.html         # Login page
│   ├── reports.html       # Main dashboard (Admin/Hospital/Doctor views)
│   └── reports_data.html  # Data management view
└── README.md              # Project documentation
```

---

_Inspired by Rutu • Built with Flask & Cloudinary_
