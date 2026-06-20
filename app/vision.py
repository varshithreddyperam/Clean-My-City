import cv2
import numpy as np
import hashlib
from typing import Tuple

def calculate_dhash(img_gray: np.ndarray) -> str:
    """
    Calculates a 64-bit difference hash (dhash) for perceptual image hashing.
    """
    # Resize to 9x8 (9 columns, 8 rows)
    resized = cv2.resize(img_gray, (9, 8), interpolation=cv2.INTER_AREA)
    # Compute difference between adjacent pixels in rows
    diff = resized[:, 1:] > resized[:, :-1]
    # Build hex string from bits
    decimal_val = 0
    hex_string = []
    for i, bit in enumerate(diff.flatten()):
        if bit:
            decimal_val += 2**(i % 8)
        if (i % 8) == 7:
            hex_string.append(hex(decimal_val)[2:].zfill(2))
            decimal_val = 0
    return "".join(hex_string)

def run_opencv_preprocessing(image_bytes: bytes) -> Tuple[str, bool, float]:
    """
    Applies OpenCV preprocessing:
    1. Grayscale Conversion
    2. Canny Edge Detection
    3. Contours extraction & bounding framing checks
    Returns: (image_hash_hex, framing_passed, edge_density)
    """
    # Decode bytes to OpenCV Mat
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        # Fallback hash if image corrupted
        fallback_hash = hashlib.md5(image_bytes).hexdigest()
        return fallback_hash, False, 0.0

    # 1. Grayscale Conversion
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Calculate difference hash
    img_hash = calculate_dhash(gray)

    # 2. Canny Edges
    edges = cv2.Canny(gray, 50, 150)
    
    # Calculate edge density (percentage of white pixels)
    total_pixels = edges.shape[0] * edges.shape[1]
    edge_pixels = np.sum(edges > 0)
    edge_density = float(edge_pixels / total_pixels)

    # 3. Find Contours and check framing alignment
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    framing_passed = False
    
    if contours:
        # Find largest contour by area
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        # Calculate bounding rect
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        frame_area = img.shape[0] * img.shape[1]
        area_ratio = (w * h) / frame_area

        # Object is framed if it is centered and occupies a significant part of the frame
        # e.g., bounding box takes up >4% of total canvas area
        if area_ratio > 0.04:
            framing_passed = True

    return img_hash, framing_passed, edge_density

async def classify_disposal(image_bytes: bytes, filename: str) -> Tuple[str, float, str, bool]:
    """
    Simulates a TensorFlow image classification model.
    Runs OpenCV preprocessing on the image, calculates perceptual dhash,
    and returns: (classification, confidence, image_hash, framing_passed).
    """
    # Perform OpenCV preprocessing
    image_hash, framing_passed, edge_density = run_opencv_preprocessing(image_bytes)
    
    # Classify based on file context tags (Mock AI classification)
    filename_lower = filename.lower()
    
    if "recycle" in filename_lower:
        classification = "recyclable"
        confidence = 0.94 + np.random.uniform(-0.02, 0.02)
    elif "bin" in filename_lower or "trash" in filename_lower:
        classification = "non-recyclable"
        confidence = 0.88 + np.random.uniform(-0.03, 0.03)
    elif "litter" in filename_lower or "road" in filename_lower or "street" in filename_lower:
        classification = "littered"
        confidence = 0.91 + np.random.uniform(-0.02, 0.02)
    else:
        # Default fallback based on edge features: high edge details -> recyclable, otherwise standard trash
        if edge_density > 0.08:
            classification = "recyclable"
            confidence = 0.76
        else:
            classification = "non-recyclable"
            confidence = 0.82
            
    return classification, float(confidence), image_hash, framing_passed
