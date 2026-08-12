# Invoice Generator System

A simple professional invoice generator built with Flask, MongoDB, Bootstrap and ReportLab.

## Features
- Dashboard
- Customer CRUD
- Product CRUD
- Invoice creation
- Automatic subtotal, discount, tax and grand total
- MongoDB storage
- Invoice history
- Professional invoice preview
- PDF download
- Payment status

## Requirements
- Python 3.10+
- MongoDB Community Server running locally

## Installation

### Windows
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open: http://127.0.0.1:5000

## If Flask-PyMongo error occurs
Run:
```bash
pip install Flask-PyMongo pymongo
```

Make sure the same Python interpreter is used:
```bash
python -m pip install -r requirements.txt
python app.py
```
