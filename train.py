import os
import sys
import numpy as np
import cv2

# Step 1: Check and import dependencies
try:
    import torch
    import torchvision
    import onnx
except ModuleNotFoundError:
    print("=" * 80)
    print("CRITICAL ERROR: Missing machine learning dependencies!")
    print("To train your custom model, you must install torch, torchvision, and onnx.")
    print("Please execute the following command in your terminal:")
    print("    pip install torch torchvision onnx")
    print("=" * 80)
    sys.exit(1)

from torchvision import datasets, transforms, models

def generate_mock_dataset():
    """
    Generates a synthetic mock dataset (recyclable, non-recyclable, littered) 
    so the script can run and export immediately without requiring manual image downloads.
    """
    for folder in ['train', 'val']:
        for cls in ['recyclable', 'non-recyclable']:
            os.makedirs(f'dataset/{folder}/{cls}', exist_ok=True)

    from PIL import Image
    import random
    
    print("[Trainer] Checking dataset folders...")
    needs_generation = False
    for folder in ['train', 'val']:
        for cls in ['recyclable', 'non-recyclable']:
            if len(os.listdir(f'dataset/{folder}/{cls}')) < 3:
                needs_generation = True

    if not needs_generation:
        print("[Trainer] Existing dataset found. Skipping synthetic data generation.")
        return

    print("[Trainer] Generating synthetic mock dataset to make script runnable...")
    for folder in ['train', 'val']:
        for cls in ['recyclable', 'non-recyclable']:
            num_imgs = 10 if folder == 'train' else 3
            for idx in range(num_imgs):
                # Create a black background canvas
                img_arr = np.zeros((224, 224, 3), dtype=np.uint8)
                
                # Add distinct geometric features/colors based on categories
                if cls == 'recyclable':
                    # Recyclable has blue circles/ellipses (representing bottles/cans)
                    cv2.circle(img_arr, (112, 112), random.randint(30, 80), (255, 100, 50), -1)
                elif cls == 'non-recyclable':
                    # Non-recyclable has green filled rectangles (representing waste bins)
                    cv2.rectangle(img_arr, (40, 40), (180, 180), (100, 255, 50), -1)
                
                # Add random noise to simulate real-world variance
                noise = np.random.normal(0, 15, img_arr.shape).astype(np.int16)
                img_arr = np.clip(img_arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                
                # Save image
                img = Image.fromarray(img_arr)
                img.save(f'dataset/{folder}/{cls}/synthetic_{idx}.jpg')
                
    print("[Trainer] Mock dataset generation complete.")

def train_custom_model():
    # 1. Prepare data directories
    generate_mock_dataset()

    # 2. Data transformations and loaders
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    print("[Trainer] Loading image dataset loaders...")
    train_dataset = datasets.ImageFolder('dataset/train', transform=transform)
    val_dataset = datasets.ImageFolder('dataset/val', transform=transform)

    # Take a small subset for extremely fast CPU compilation/export
    train_subset = torch.utils.data.Subset(train_dataset, range(min(8, len(train_dataset))))
    val_subset = torch.utils.data.Subset(val_dataset, range(min(4, len(val_dataset))))
    
    train_loader = torch.utils.data.DataLoader(train_subset, batch_size=4, shuffle=True)
    val_loader = torch.utils.data.DataLoader(val_subset, batch_size=4, shuffle=False)

    print(f"[Trainer] Classes found: {train_dataset.classes} (Mapped to indices: {train_dataset.class_to_idx})")

    # 3. Initialize model (MobileNetV2 fine-tuned for 3 output classes)
    print("[Trainer] Loading pretrained MobileNetV2 architecture...")
    try:
        # Newer torchvision versions (0.13+)
        weights = models.MobileNet_V2_Weights.DEFAULT
        model = models.mobilenet_v2(weights=weights)
    except AttributeError:
        # Older torchvision versions
        model = models.mobilenet_v2(pretrained=True)

    # Freeze base model parameters to make CPU training extremely fast
    for param in model.parameters():
        param.requires_grad = False

    # Replace classifier head for 2 classes
    model.classifier[1] = torch.nn.Linear(model.last_channel, 2)
    
    # Ensure classifier weights are trainable
    for param in model.classifier.parameters():
        param.requires_grad = True

    # 4. Device and Optimizer selection (strictly CPU)
    device = torch.device("cpu")
    model.to(device)

    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=0.001)

    # 5. Training loop
    epochs = 1
    print(f"[Trainer] Starting CPU training loop for {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        correct_preds = 0
        total_preds = 0
        
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item() * inputs.size(0)
            _, predicted = torch.max(outputs, 1)
            total_preds += labels.size(0)
            correct_preds += (predicted == labels).sum().item()
            
        epoch_loss = running_loss / len(train_dataset)
        epoch_acc = (correct_preds / total_preds) * 100
        print(f"Epoch {epoch+1}/{epochs} | Loss: {epoch_loss:.4f} | Training Accuracy: {epoch_acc:.2f}%")

    # 6. Export to ONNX format
    print("[Trainer] Training complete! Exporting PyTorch weights to ONNX model...")
    model.eval()
    dummy_input = torch.randn(1, 3, 224, 224, device=device)
    onnx_path = "app/mobilenetv2-7.onnx"
    
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    
    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        verbose=False,
        opset_version=11,
        input_names=["input"],
        output_names=["output"]
    )
    print(f"[Trainer] SUCCESS: Model exported and saved to {onnx_path}")
    print("=" * 80)
    print("You can now restart your FastAPI backend server. The app will automatically")
    print("detect the new 2-class model layout and use it to classify uploads!")
    print("=" * 80)

if __name__ == "__main__":
    train_custom_model()
