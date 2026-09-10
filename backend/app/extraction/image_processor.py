import io
from PIL import Image
from typing import Tuple, Dict, Any

def process_image_document(file_path: str) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Validates and converts image file for multimodal Gemini processing.
    Returns:
    - image_bytes: PNG/JPEG image binary data
    - mime_type: image/png or image/jpeg
    - image_info: dimensions metadata
    """
    with Image.open(file_path) as img:
        mime = "image/png" if img.format == "PNG" else "image/jpeg"
        width, height = img.size
        
        buffer = io.BytesIO()
        # Convert RGBA/P mode to RGB if JPEG
        if img.mode in ("RGBA", "P") and mime == "image/jpeg":
            img_conv = img.convert("RGB")
            img_conv.save(buffer, format="JPEG")
        else:
            img.save(buffer, format=img.format or "PNG")
            
        return buffer.getvalue(), mime, {"width": width, "height": height, "mode": img.mode}
