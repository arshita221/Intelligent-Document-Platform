import re
import uuid
from datetime import datetime

def generate_document_name(original_filename: str) -> str:
    """Generates a clean, unique document identifier."""
    base = re.sub(r'[^a-zA-Z0-9_\-]', '_', os_filename_clean(original_filename))
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    return f"{base}_{timestamp}_{short_id}"

def os_filename_clean(filename: str) -> str:
    """Removes extension and illegal characters from filename."""
    clean = filename.rsplit('.', 1)[0]
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', clean)[:50]
