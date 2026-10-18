from app.database import create_tables
from app.models import OrderDB

create_tables()  # Create the tables in the database if they don't exist

print("Database tables created successfully.")