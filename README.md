# Medical Patient Reports Web Application

This is a simple Flask web application for uploading and viewing medical patient reports. It uses Cloudinary for persistent cloud storage, ensuring that uploaded files are not lost on server restarts or redeploys.

## Features

- **Cloud-Based File Upload**: Upload patient reports (PDF, PNG, JPG, etc.) directly to Cloudinary.
- **Patient Organization**: Files are automatically organized into folders by patient name in the cloud.
- **Doctor Dashboard**: A secure, login-protected dashboard for doctors to manage reports.
- **Powerful Search**: Search for reports by patient name or filename.
- **In-Browser Previews**: Preview images and PDFs directly on the reports page.
- **Secure Deletion**: Doctors can permanently delete reports from cloud storage.

## Tech Stack

- **Backend**: Flask
- **File Storage**: Cloudinary
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Ready for services like Render, Heroku, etc.

## Setup and Installation

### 1. Prerequisites

- Python 3.x
- A free [Cloudinary](https://cloudinary.com/users/register/free) account.

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd medical_site
```

### 3. Install Dependencies

It's recommended to use a virtual environment.

```bash
# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install the required packages
pip install -r requirements.txt
```

### 4. Configuration (Crucial Step)

This application requires environment variables for configuration. The easiest way to manage these for local development is to create a `.env` file in the root of your project.

Create a file named `.env` and add the following, filling in your own values:

```
CLOUDINARY_CLOUD_NAME="your_cloud_name"
CLOUDINARY_API_KEY="your_api_key"
CLOUDINARY_API_SECRET="your_api_secret"

# Generate a strong secret key with: python -c "import secrets; print(secrets.token_hex(16))"
SECRET_KEY="your_generated_secret_key"

# Generate a password hash with: python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-chosen-password'))"
DOCTOR_PASSWORD_HASH="your_generated_password_hash"
```

**Note:** You will need to install a library to load the `.env` file. Add `python-dotenv` to your `requirements.txt` and `pip install python-dotenv`. Then, add `from dotenv import load_dotenv; load_dotenv()` to the top of `app.py`.

When deploying to a service like Render, you will set these same variables in the service's "Environment" or "Secrets" dashboard instead of using a `.env` file.

### 5. Run the Application

With your environment configured, you can run the development server:

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5000`.
