import os
import requests
import zipfile
import io
import torch
import numpy as np
import time
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

_session = requests.Session()

def post_nai(token, payload, url="https://image.novelai.net/ai/generate-image"):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        response = _session.post(url, headers=headers, json=payload)
        
        if response.status_code == 429:
            print("NAI API: 429 Too Many Requests. Sleeping for 60 seconds...")
            time.sleep(60)
            response = _session.post(url, headers=headers, json=payload)
            
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"NAI API Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        raise e

def zip_to_pil(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        image_bytes = zipped.read(zipped.infolist()[0])
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")

def pil_to_tensor(img):
    img_np = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(img_np).unsqueeze(0)

def tensor_to_pil(tensor, batch_index=0):
    # tensor shape: [B, H, W, C]
    img_np = tensor[batch_index].cpu().numpy()
    img_np = (img_np * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img_np)

def get_nai_token():
    token = os.getenv('NAI_ACCESS_TOKEN')
    if not token:
        print("Warning: NAI_ACCESS_TOKEN not found in environment variables.")
    return token
