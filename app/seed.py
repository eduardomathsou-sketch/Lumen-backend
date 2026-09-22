"""Optional demo catalog, explicitly invoked after migrations."""
from app.main import seed_database

if __name__ == "__main__":
    seed_database()
    print("Catálogo de demonstração preparado; catálogo existente preservado.")
