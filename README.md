<div align="center">

<img src="static/logo.png" alt="Content मंच" width="180"/>

# Content मंच

### *Content को दें नई पहचान*

A modern, cloud-powered Image & GIF Gallery — built with Flask, AWS S3, Neon PostgreSQL, and Tailwind CSS.


### 🌐 [Live Demo → content-manch.onrender.com](https://content-manch.onrender.com)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![AWS S3](https://img.shields.io/badge/AWS-S3-FF9900?style=flat&logo=amazonaws&logoColor=white)](https://aws.amazon.com/s3/)
[![Neon](https://img.shields.io/badge/Neon-PostgreSQL-00E599?style=flat&logo=postgresql&logoColor=white)](https://neon.tech/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3-06B6D4?style=flat&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Render](https://img.shields.io/badge/Deployed_on-Render-46E3B7?style=flat&logo=render&logoColor=white)](https://content-manch.onrender.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](#license)
[![Tests](https://img.shields.io/badge/Tests-59%20passed-success?style=flat)](#testing)

</div>

---

## ✨ Features

- 🔐 **Secure Authentication** — Sign up, log in, and log out with hashed passwords (Werkzeug + Flask-Login)
- ☁️ **Cloud Storage** — Images uploaded directly to AWS S3 with public-read URLs
- 🏷️ **Tag System** — Add up to 20 tags per image for easy discovery
- 🔍 **Live Search** — Dynamic, case-insensitive partial tag search without page reloads
- 👍 **Like / Dislike** — One reaction per user per image with smart toggle logic
- 🗑️ **Owner-Only Deletion** — Only the uploader can delete an image, with a confirmation modal
- 👑 **Admin Role** — Admin can delete any user's image for moderation
- 🌓 **Dark / Light Mode** — Persistent theme toggle via `localStorage`
- 📱 **Fully Responsive** — Pinterest-style masonry grid that adapts from mobile to desktop
- ⚡ **Fast** — Search returns results in under 2 seconds for up to 10,000 records

---

## 🖼️ Screenshots

<div align="center">

<img width="1600" height="850" alt="IMG-20260519-WA0024" src="https://github.com/user-attachments/assets/cf185f06-873a-424b-90ea-e73a5eae46d6" />
<img width="1600" height="843" alt="IMG-20260519-WA0025" src="https://github.com/user-attachments/assets/5efea754-1b73-4dad-bdec-9dee69246382" />
<img width="1897" height="866" alt="Screenshot 2026-05-20 201632" src="https://github.com/user-attachments/assets/956fdc7a-7eb5-4566-bf77-4d73aa826fd9" />
<img width="1901" height="871" alt="Screenshot 2026-05-20 201602" src="https://github.com/user-attachments/assets/f4dc6134-3366-4e43-83a9-1fa0a555ef23" />

</div>

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, Flask 3.0, SQLAlchemy 2.0 |
| **Database** | Neon PostgreSQL (production) / SQLite (local dev) |
| **Storage** | Amazon AWS S3 (Boto3) |
| **Auth** | Flask-Login + Werkzeug password hashing |
| **Frontend** | HTML5, Tailwind CSS (CDN), Vanilla JavaScript |
| **Hosting** | Render (Web Service) |
| **Testing** | pytest, Hypothesis (property-based tests) |
| **Production Server** | Gunicorn |

---

## 📋 Prerequisites

- Python **3.10** or higher
- An **AWS account** with an S3 bucket (configured for public read access)
- An **IAM user** with `s3:PutObject`, `s3:DeleteObject`, `s3:GetObject` permissions
- `pip3` (Python package manager)

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/cms-image-gallery.git
cd cms-image-gallery
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root with the following keys:

```bash
# Flask secret key — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-secret-key

# AWS S3 credentials
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_S3_BUCKET_NAME=your-bucket-name
AWS_S3_REGION=us-east-1
```

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing key — generate one with the command below |
| `AWS_ACCESS_KEY_ID` | Your AWS IAM access key ID |
| `AWS_SECRET_ACCESS_KEY` | Your AWS IAM secret access key |
| `AWS_S3_BUCKET_NAME` | Name of your S3 bucket |
| `AWS_S3_REGION` | AWS region (e.g. `us-east-1`) |

**Generate a secret key:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run the application

```bash
python3 app.py
```


To enable debug mode:
```bash
FLASK_DEBUG=1 python3 app.py
```

---

## ☁️ AWS S3 Setup

### Bucket configuration

| Setting | Value |
|---|---|
| **Object Ownership** | ACLs enabled |
| **Block Public Access** | Disabled (all 4 unchecked) |
| **Versioning** | Disabled |
| **Encryption** | SSE-S3 (default) |

### Bucket policy

Allow public read for uploaded images:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
  }]
}
```

### CORS configuration

```json
[{
  "AllowedHeaders": ["*"],
  "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
  "AllowedOrigins": ["*"],
  "ExposeHeaders": ["ETag"]
}]
```

### IAM policy (for the app's access key)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:PutObjectAcl", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    }
  ]
}
```

---

## 🧪 Testing

Run the full test suite (59 tests covering services, routes, and edge cases):

```bash
python3 -m pytest tests/ -v
```

Run with coverage:
```bash
python3 -m pytest tests/ --cov=. --cov-report=html
```

---

## 🌐 Deployment (Render + Neon)

This app is deployed on **Render** (hosting) + **Neon** (PostgreSQL database) + **AWS S3** (image storage).

### Production setup:

1. Push this repo to GitHub
2. Create a free **Neon** project at [neon.tech](https://neon.tech) → copy the pooled connection string
3. Create a **Render Web Service** at [render.com](https://render.com) → connect this repo
4. Configure Render:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:application --workers 1 --timeout 120`
   - **Instance Type**: Free
5. Add Environment Variables in Render:
   - `DATABASE_URL` = your Neon connection string
   - `SECRET_KEY` = a random 64-char hex string
   - `AWS_ACCESS_KEY_ID` = your AWS key
   - `AWS_SECRET_ACCESS_KEY` = your AWS secret
   - `AWS_S3_BUCKET_NAME` = your bucket name
   - `AWS_S3_REGION` = your bucket region
   - `RENDER` = `1`
6. Deploy — your app goes live in ~3 minutes


Other supported platforms: **Railway**, **Fly.io**, **PythonAnywhere**, **AWS Elastic Beanstalk**

---

## 📁 Project Structure

```
cms-image-gallery/
├── app.py                 # Flask app factory + entry point
├── models.py              # SQLAlchemy models (User, Image, Tag, Likes)
├── routes.py              # All HTTP routes
├── auth_service.py        # Registration + login
├── upload_service.py      # File validation + S3 upload + tag parsing
├── s3_service.py          # Boto3 S3 integration
├── search_service.py      # Tag-based search
├── like_service.py        # Like/dislike toggle logic
├── delete_service.py      # Authorized deletion with cascade
├── templates/             # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html         # Gallery homepage
│   ├── login.html
│   ├── register.html
│   ├── upload.html
│   └── error.html
├── static/                # Static assets
│   ├── js/gallery.js      # Frontend JS (search, reactions, delete)
│   └── logo.png
├── tests/                 # pytest test suite
│   ├── test_like.py       # 11 tests
│   ├── test_search.py     # 17 tests
│   └── test_upload.py     # 31 tests
├── requirements.txt       # Python dependencies (pinned)
├── Procfile               # Production start command
└── README.md
```

---

## 🔒 Security Notes

- ✅ Passwords are hashed using Werkzeug's `generate_password_hash` (PBKDF2-SHA256)
- ✅ AWS credentials are loaded from environment variables only — **never hardcoded**
- ✅ `.env` is excluded from version control via `.gitignore`
- ✅ Owner-only authorization on all destructive operations
- ✅ Generic error messages on login to prevent user enumeration
- ✅ Unique S3 keys (UUID-based) prevent overwrite attacks

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 👥 Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/ishant025">
        <img src="https://github.com/ishant025.png" width="80" style="border-radius:50%;" alt="Ishant Sahu"/><br/>
        <sub><b>Ishant Sahu</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/rootmelody">
        <img src="https://github.com/rootmelody.png" width="80" style="border-radius:50%;" alt="Nitin Nirmalkar"/><br/>
        <sub><b>Nitin Nirmalkar</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/RAKESH-PARATE">
        <img src="https://github.com/RAKESH-PARATE.png" width="80" style="border-radius:50%;" alt="Rakesh Parate"/><br/>
        <sub><b>Rakesh Parate</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/sageverse-tech">
        <img src="https://github.com/sageverse-tech.png" width="80" style="border-radius:50%;" alt="Khushraj Varghat"/><br/>
        <sub><b>Khushraj Varghat</b></sub>
      </a>
    </td>
  </tr>
</table>

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- Built as a Cloud Computing college project
- Logo represents a **lotus** (creativity) opening into a **book** (content)
- Color palette inspired by traditional Indian aesthetics

---

<div align="center">

### Made with ❤️ for the love of content 

⭐ **Star this repo if you found it useful!**

</div>
