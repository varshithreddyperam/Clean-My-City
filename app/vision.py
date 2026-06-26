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

    # 4. Face Detection using OpenCV Haar Cascade (Disabled due to high false positives on waste objects)
    has_face = False

    return img_hash, framing_passed, edge_density, has_face

MODEL_PATH = "app/mobilenetv2-7.onnx"
IMAGENET_MODEL_PATH = "app/mobilenetv2-imagenet.onnx"
MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-7.onnx"

net = None
net_imagenet = None

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

def get_imagenet_net():
    global net_imagenet
    if net_imagenet is None:
        if not os.path.exists(IMAGENET_MODEL_PATH):
            print(f"[Vision] Downloading ImageNet MobileNetV2 ONNX model from {MODEL_URL}...")
            try:
                os.makedirs(os.path.dirname(IMAGENET_MODEL_PATH), exist_ok=True)
                req = urllib.request.Request(
                    MODEL_URL, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req) as response:
                    with open(IMAGENET_MODEL_PATH, 'wb') as f:
                        f.write(response.read())
                print("[Vision] ImageNet model download complete!")
            except Exception as e:
                print(f"[Vision] Failed to download ImageNet model: {e}")
        if os.path.exists(IMAGENET_MODEL_PATH):
            try:
                net_imagenet = cv2.dnn.readNetFromONNX(IMAGENET_MODEL_PATH)
                print("[Vision] ImageNet MobileNetV2 ONNX loaded successfully.")
            except Exception as e:
                print(f"[Vision] Failed to load ImageNet ONNX net: {e}")
    return net_imagenet

def is_non_waste_imagenet(top_idx: int) -> bool:
    """
    Checks if an ImageNet-1K class ID represents an obvious non-waste category
    such as humans, clothes, pets, vehicles, office equipment, or furniture.
    """
    # 1. Animals: 0 to 397 (all vertebrates, insects, spiders, birds, mammals, cats, dogs, etc.)
    if 0 <= top_idx <= 397:
        return True
    
    # 2. Clothing & Accessories
    clothing_accessories = {
        401, 411, 445, 612, 651, 655, 834, 608, 474, 869, 617, 738, 793, 841, # clothing
        837, 813, 904, 592, 668, 669, 715 # accessories, including mosquito net & helmet
    }
    if top_idx in clothing_accessories:
        return True
        
    # 3. Electronics & Computers
    electronics = {
        527, 508, 620, 673, 706, 782, 851, 687, 487, 844, 690, 752, 721
    }
    if top_idx in electronics:
        return True
        
    # 4. Vehicles & Transportation
    vehicles = {
        404, 444, 511, 609, 627, 654, 661, 670, 705, 751, 779, 817, 864, 867, 889, 847, 895, 812,
        472, 482, 554, 625, 814, 871, 914
    }
    if top_idx in vehicles:
        return True
        
    # 5. Furniture & Large Household Fixtures
    furniture_fixtures = {
        805, 526, 532, 900, 431, 503, 423, 765, 827, # furniture
        861, 883, 899, 425, 757 # fixtures
    }
    if top_idx in furniture_fixtures:
        return True
        
    # 6. Musical Instruments
    musical_instruments = {
        402, 486, 543, 558, 593, 697, 702, 704, 719, 726, 881, 886, 818, 514, 776
    }
    if top_idx in musical_instruments:
        return True
        
    # 7. Buildings & Large Structures
    structures = {
        449, 498, 744, 689, 911, 428, 535, 701, 727, 830, 836, 887, 913
    }
    if top_idx in structures:
        return True
        
    # 8. Miscellaneous obvious non-waste (books, toys, balls, digital screens/websites)
    misc = {
        453, 917, 549, 916, # book, comic, envelope, website
        852, 722, 640, 865, 848, 723, 749 # toys, balls, etc.
    }
    if top_idx in misc:
        return True

    return False

async def classify_disposal(image_bytes: bytes, filename: str) -> Tuple[str, float, str, bool]:
    """
    Classifies a waste disposal image using a two-stage pipeline:
    1. Runs the fine-tuned custom model to get the primary classification.
    2. If the custom model is highly confident (>= 70%), it bypasses the ImageNet filter.
    3. Otherwise, it runs a 1000-class ImageNet filter to block obvious non-waste items.
    """
    # Perform OpenCV preprocessing
    image_hash, framing_passed, edge_density, has_face = run_opencv_preprocessing(image_bytes)

    # 1. Human presence check (Face cascade fallback)
    if has_face:
        return "invalid_disposal", 0.99, image_hash, False

    # 2. Clean digital graphics / low-texture filter
    # If the edge density is very low, we check if it is confidently classified as a whitelisted waste class by ImageNet.
    # If it is not, we block it immediately. This allows clean photos of single waste items on plain backgrounds
    # while rejecting clean digital diagrams, flowcharts, game logos, etc.
    if edge_density < 0.035:
        is_whitelisted_waste = False
        dnn_imagenet = get_imagenet_net()
        if dnn_imagenet is not None:
            try:
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    blob = cv2.dnn.blobFromImage(img, 1.0/255.0, (224, 224), (0.485, 0.456, 0.406), swapRB=True, crop=False)
                    blob[0, 0, :, :] /= 0.229
                    blob[0, 1, :, :] /= 0.224
                    blob[0, 2, :, :] /= 0.225
                    dnn_imagenet.setInput(blob)
                    preds_imagenet = dnn_imagenet.forward()
                    e_x = np.exp(preds_imagenet[0] - np.max(preds_imagenet[0]))
                    probs_imagenet = e_x / e_x.sum(axis=0)
                    top_idx_imagenet = int(np.argmax(probs_imagenet))
                    confidence_imagenet = float(probs_imagenet[top_idx_imagenet])
                    
                    whitelist = {
                        440, 737, 898, 907, 724, 457, # bottles
                        478, 519, 728, 639, 791, # packaging/containers/bags
                        653, 412, 463, # cans/bins/buckets
                        968, 636, 504, 811, 923, 647, # cups/mugs/plates
                        948, 949, 950, 951, 952, 953, 954, 957, 958, 988, # organic/food
                        936, 937, 938, 939, 940, 941, 962, 963, 964, 965, # organic/food
                        700, 686, # paper/packets
                        783, 862 # screw, toilet paper
                    }
                    if top_idx_imagenet in whitelist and confidence_imagenet >= 0.15:
                        is_whitelisted_waste = True
            except Exception as e:
                print(f"[Vision] Graphics filter error: {e}")
                
        if not is_whitelisted_waste:
            print(f"[Vision] Blocked clean graphic / low-texture image: edge_density={edge_density:.4f}")
            return "unknown_object", 0.0, image_hash, False

    # Preprocess image for DNN models (224x224, BGR->RGB, normalized)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return "unknown_object", 0.0, image_hash, False

    blob = cv2.dnn.blobFromImage(img, 1.0/255.0, (224, 224), (0.485, 0.456, 0.406), swapRB=True, crop=False)
    blob[0, 0, :, :] /= 0.229
    blob[0, 1, :, :] /= 0.224
    blob[0, 2, :, :] /= 0.225

    # 2. Stage 1: Run Custom Waste Classifier first to evaluate confidence
    dnn_net = get_net()
    classification = "unknown_object"
    confidence = 0.0
    num_classes = 1000
    top_idx = 0
    probs = None

    if dnn_net is not None:
        try:
            dnn_net.setInput(blob)
            preds = dnn_net.forward()
            
            # Apply softmax
            e_x = np.exp(preds[0] - np.max(preds[0]))
            probs = e_x / e_x.sum(axis=0)
            
            # Get highest probability class
            top_idx = int(np.argmax(probs))
            confidence = float(probs[top_idx])
            num_classes = preds.shape[1]
        except Exception as e:
            print(f"[Vision] Custom model error: {e}")

    # 3. Stage 2: General Object Filter (ImageNet model)
    # Bypass this filter if the custom model is highly confident (>= 70%) that it is waste
    # AND the image has high edge density (>= 0.10) indicating a complex, textured waste scene.
    # This prevents pareidolia false positives (like complex trash bags looking like a pug dog),
    # but ensures OOD clean photos (like swimsuit selfies, flowcharts) do not bypass the filter.
    bypass_filter = (num_classes == 2 and confidence >= 0.70 and edge_density >= 0.10)
    
    if not bypass_filter:
        dnn_imagenet = get_imagenet_net()
        if dnn_imagenet is not None:
            try:
                dnn_imagenet.setInput(blob)
                preds_imagenet = dnn_imagenet.forward()
                
                # Apply Softmax to get probabilities
                e_x = np.exp(preds_imagenet[0] - np.max(preds_imagenet[0]))
                probs_imagenet = e_x / e_x.sum(axis=0)
                
                top_idx_imagenet = int(np.argmax(probs_imagenet))
                confidence_imagenet = float(probs_imagenet[top_idx_imagenet])
                
                # If the ImageNet model detects an obvious non-waste item with reasonable confidence, block it
                if is_non_waste_imagenet(top_idx_imagenet) and confidence_imagenet >= 0.15:
                    print(f"[Vision] Blocked non-waste item via ImageNet blocklist: class={top_idx_imagenet}, conf={confidence_imagenet:.4f}")
                    return "unknown_object", confidence_imagenet, image_hash, False

                # If the ImageNet model predicts a class that is NOT in the whitelist of waste items,
                # and is highly confident (>= 15%), block it as well (catches homes, general outdoor objects, logos, etc.)
                whitelist = {
                    440, 737, 898, 907, 724, 457, # bottles
                    478, 519, 728, 639, 791, # packaging/containers/bags
                    653, 412, 463, # cans/bins/buckets
                    968, 636, 504, 811, 923, 647, # cups/mugs/plates
                    948, 949, 950, 951, 952, 953, 954, 957, 958, 988, # organic/food
                    936, 937, 938, 939, 940, 941, 962, 963, 964, 965, # organic/food
                    700, 686, # paper/packets
                    783, 862 # screw (metal recycle_box), toilet paper (waste paper/packaging)
                }
                if top_idx_imagenet not in whitelist and confidence_imagenet >= 0.15:
                    print(f"[Vision] Blocked non-waste item via ImageNet whitelist filter: class={top_idx_imagenet}, conf={confidence_imagenet:.4f}")
                    return "unknown_object", confidence_imagenet, image_hash, False
            except Exception as e:
                print(f"[Vision] ImageNet filtering error: {e}")
    else:
        print(f"[Vision] Bypassing ImageNet filter due to high custom confidence: {confidence:.4f}")

    # 4. Process final classification result
    if dnn_net is not None and probs is not None:
        try:
            # Custom 2-class model (trained via train.py):
            #   Class 0 = non-recyclable, Class 1 = recyclable
            if num_classes == 2:
                # Entropy-based rejection: if both classes have similar probability,
                # the model is confused — likely not a waste item
                min_prob = float(min(probs[0], probs[1]))
                max_prob = float(max(probs[0], probs[1]))
                # If the difference between classes is small, model doesn't recognize the item
                if max_prob - min_prob < 0.10:
                    return "unknown_object", confidence, image_hash, False
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

    # 4. Fallback: if model failed to load or inference crashed
    # Use edge density as a basic heuristic — waste images tend to have moderate edge density
    if edge_density > 0.03:
        # Some structure detected; classify conservatively
        classification = "non-recyclable"
        confidence = 0.60
    else:
        classification = "unknown_object"
        confidence = 0.40

    return classification, float(confidence), image_hash, framing_passed
