import os
import cv2
import torch
import numpy as np
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from PIL import Image
from transformers import pipeline
from diffusers import StableDiffusionInpaintPipeline
from torchvision import models, transforms

app = Flask(__name__)

# Configure upload and output folders
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['OUTPUT_FOLDER'] = 'static/outputs/'

# Load classification model (Places365 for scene detection)
classifier = pipeline("image-classification", model="openai/clip-vit-base-patch32")

# Load inpainting model
device = "cuda" if torch.cuda.is_available() else "cpu"
pipe_inpaint = StableDiffusionInpaintPipeline.from_pretrained("stabilityai/stable-diffusion-2-inpainting")
pipe_inpaint = pipe_inpaint.to(device)

# Load the DeepLabV3 segmentation model
segmentation_model = models.segmentation.deeplabv3_resnet101(pretrained=True)
segmentation_model.eval().to(device)

# Define image transformations for segmentation
preprocess = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((512, 512)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# Route for uploading an image


# Check if the file is an allowed image type
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

# Scene classification function to detect room type
def classify_room(image_path):
    result = classifier(image_path)[0]
    return result['label']

# Segment the image and create a prompt based on the room type
# Segment the image and create a prompt based on the room type
def segment_and_generate_prompt(image, room_type):
    # Transform the image for segmentation
    input_tensor = preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        output = segmentation_model(input_tensor)['out'][0]
    
    output_predictions = output.argmax(0).cpu().numpy()

    # Create a mask where furniture or objects are detected (based on class indices)
    mask = np.zeros_like(output_predictions)
    
    # Valid class indices for DeepLabV3 (based on COCO dataset)
    valid_class_indices = [15, 24, 1, 28]  # chair, sofa, person, dining table
    class_indices = [15, 24, 1, 28]  # customize as needed

    # Ensure we're using only valid indices
    for idx in class_indices:
        if idx < output_predictions.max():  # Check that the class index is valid
            mask[output_predictions == idx] = 1

    # Create a mask image
    mask_image = Image.fromarray((mask * 255).astype(np.uint8))

    # Prompt based on room type
    if "bedroom" in room_type:
        prompt = "enhance bedroom with modern furniture, soft lighting, and minimalistic decor"
    elif "living room" in room_type:
        prompt = "enhance living room with modern furniture, warm lighting, and minimalistic design"
    else:
        prompt = "enhance room with modern furniture and soft lighting"

    return mask_image, prompt


# Function to apply inpainting to the room for enhancements
def inpaint_room(image, mask, prompt, filename):
    # Convert OpenCV image to PIL format
    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    # Generate redesigned room with inpainting
    result = pipe_inpaint(prompt=prompt, image=image_pil, mask_image=mask, num_inference_steps=50).images[0]

    # Save the redesigned image
    output_filename = f"redesigned_{filename}"
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    result.save(output_path)

    return output_filename

if __name__ == '__main__':
    app.run(debug=True)
