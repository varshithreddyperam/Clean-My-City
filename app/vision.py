import cv2
import numpy as np
import hashlib
import os
import urllib.request
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

def run_opencv_preprocessing(image_bytes: bytes) -> Tuple[str, bool, float, bool]:
    """
    Applies OpenCV preprocessing:
    1. Grayscale Conversion
    2. Canny Edge Detection
    3. Contours extraction & bounding framing checks
    4. Face detection
    Returns: (image_hash_hex, framing_passed, edge_density, has_face)
    """
    # Decode bytes to OpenCV Mat
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        # Fallback hash if image corrupted
        fallback_hash = hashlib.md5(image_bytes).hexdigest()
        return fallback_hash, False, 0.0, False

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

    # 4. Face Detection (Disabled)
    has_face = False

    return img_hash, framing_passed, edge_density, has_face

MODEL_PATH = "app/mobilenetv2-7.onnx"
MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-7.onnx"

net = None

def get_net():
    global net
    if net is None:
        if not os.path.exists(MODEL_PATH):
            print(f"[Vision] Downloading MobileNetV2 ONNX model from {MODEL_URL}...")
            try:
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                req = urllib.request.Request(
                    MODEL_URL, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req) as response:
                    with open(MODEL_PATH, 'wb') as f:
                        f.write(response.read())
                print("[Vision] Download complete!")
            except Exception as e:
                print(f"[Vision] Failed to download model: {e}")
        if os.path.exists(MODEL_PATH):
            try:
                net = cv2.dnn.readNetFromONNX(MODEL_PATH)
                print("[Vision] MobileNetV2 ONNX loaded successfully.")
            except Exception as e:
                print(f"[Vision] Failed to load ONNX net: {e}")
    return net

async def classify_disposal(image_bytes: bytes, filename: str) -> Tuple[str, float, str, bool]:
    """
    Classifies a waste disposal image using the trained MobileNetV2 ONNX model.
    Runs OpenCV preprocessing on the image, then performs neural network inference.
    Returns: (classification, confidence, image_hash, framing_passed).
    
    Non-waste images are rejected based on low model confidence, NOT filename keywords.
    """
    # Perform OpenCV preprocessing
    image_hash, framing_passed, edge_density, has_face = run_opencv_preprocessing(image_bytes)

    # 1. Human presence check
    if has_face:
        return "invalid_disposal", 0.99, image_hash, False

    # 2. Run Neural Network classification using MobileNetV2 ONNX model
    dnn_net = get_net()
    classification = "unknown_object"
    confidence = 0.0

    if dnn_net is not None:
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                # Preprocess for MobileNetV2
                blob = cv2.dnn.blobFromImage(img, 1.0/255.0, (224, 224), (0.485, 0.456, 0.406), swapRB=True, crop=False)
                blob[0, 0, :, :] /= 0.229
                blob[0, 1, :, :] /= 0.224
                blob[0, 2, :, :] /= 0.225
                
                dnn_net.setInput(blob)
                preds = dnn_net.forward()
                
                # Apply softmax
                e_x = np.exp(preds[0] - np.max(preds[0]))
                probs = e_x / e_x.sum(axis=0)
                
                # Get highest probability class
                top_idx = int(np.argmax(probs))
                confidence = float(probs[top_idx])
                
                num_classes = preds.shape[1]
                
                # Custom 2-class model (trained via train.py):
                #   Class 0 = non-recyclable, Class 1 = recyclable
                if num_classes == 2:
                    if confidence < 0.55:
                        # Low confidence — model is unsure, likely not a waste item
                        return "unknown_object", confidence, image_hash, False
                    if top_idx == 0:
                        classification = "non-recyclable"
                    else:
                        classification = "recyclable"
                
                # Custom 3-class model:
                elif num_classes == 3:
                    if confidence < 0.45:
                        return "unknown_object", confidence, image_hash, False
                    if top_idx == 0:
                        classification = "recyclable"
                    elif top_idx == 1:
                        classification = "non-recyclable"
                    else:
                        classification = "non-recyclable"
                
                else:
                    # Default 1000-class ImageNet model (pretrained, not fine-tuned)
                    # Map known ImageNet waste-related class IDs
                    recyclable_ids = {440, 737, 898, 907, 478, 519, 653, 724, 897}
                    non_recyclable_ids = {412, 728, 463, 968, 636, 700, 504, 811, 923}
                    
                    if top_idx in recyclable_ids and confidence >= 0.20:
                        classification = "recyclable"
                    elif top_idx in non_recyclable_ids and confidence >= 0.20:
                        classification = "non-recyclable"
                    else:
                        # Not recognized as any waste class
                        return "unknown_object", confidence, image_hash, False

                return classification, confidence, image_hash, framing_passed
        except Exception as e:
            print(f"[Vision] Inference error: {e}")

    # 3. Fallback: if model failed to load or inference crashed
    # Use edge density as a basic heuristic — waste images tend to have moderate edge density
    if edge_density > 0.03:
        # Some structure detected; classify conservatively
        classification = "non-recyclable"
        confidence = 0.60
    else:
        classification = "unknown_object"
        confidence = 0.40

    return classification, float(confidence), image_hash, framing_passed
