# Technology Stack

## Backend
- Django 5.1.4
- Python 3.13
- SQLite (Development)

## Frontend
- Tailwind CSS
- HTML/JavaScript

## Authentication
- Django's built-in authentication system

## Database Schema
### Task Model
- title (CharField)
- description (TextField)
- status (CharField: inbox/backlog/done/deleted)
- created_date (DateTimeField)
- modified_date (DateTimeField)
- estimated_time (IntegerField, optional)
- cost_benefit_ratio (IntegerField, optional)
- is_project (BooleanField)
- parent_project (ForeignKey to self)
- user (ForeignKey to User)