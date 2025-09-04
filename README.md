# ParkEasy
🚗 ParkEasy App 
A full-stack web application built using Flask (Python) and Vue.js for managing vehicle parking lots, user bookings, and automated background tasks like email reminders and reports.

**📂 Project Structure**
```bash
project/
│
├── app.py                      # Main Flask application
├── routes/                     # Flask route handlers
│   ├── routes.py
│   
├── templates/                  # HTML templates (Jinja2)
│   ├── user_dashboard.html
│   └── admin_dashboard.html
├── static/                     # CSS, JS, images
├── models.py                   # SQLAlchemy models
├── celery_worker.py            # Celery configuration
├── requirements.txt            # Python dependencies
├── api_definition.yaml         # API endpoints defined in YAML
├── README.md                   # This file
└── ...
```

**🚀 How to Run the App**

✅ For Flask Web App

The web app runs without any virtual environment if all packages are installed globally.

```bash
python app.py
```
Open the browser and go to: http://localhost:5000

Admin and user functionalities will be available.

**⏱️ How to Run Celery Worker (For Background Tasks)**

❗ Celery tasks like email reminders and monthly reports require a virtual environment and Redis server.

1. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
```
2. (Optional but recommended) Upgrade setuptools
```bash
pip install --upgrade setuptools
```
3. Install required packages
```bash
pip install -r requirements.txt
```
4. Make sure Redis server is running
   
   Start Redis on your machine or use a hosted Redis server.

6. Run Celery worker
```bash
celery -A celery_worker.celery worker --loglevel=info
```
📦 API Definition (YAML)

The file api_definition.yaml contains the full list of API routes used in the project. It includes:

/login

/logout

/register

/admin/dashboard

/user/bookings

/api/lots

/api/bookings

And others...

This YAML file can be used for documentation or importing into tools like Swagger UI or Postman.

**📝 Features**

*Core Features:*

🧍 User and Admin Roles

📍 Add and Edit Parking Lots (Admin)

🚗 Book, View, and Cancel Parking (User)

📊 Dashboard for Admin with Spot Status

🔐 Login/Logout System (Session-based)

📨 Email Reminders using Celery

📈 Monthly Parking Report via Email

*Tech Stack:*

Frontend: Vue.js, Bootstrap 5

Backend: Flask (Python), SQLite

Background Tasks: Celery + Redis

Others: Chart.js, Flask-Login, SQLAlchemy


