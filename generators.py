import os
import torch
import numpy as np
import base64
import io
from PIL import Image, ImageFilter, ImageDraw
from .nai_api import post_nai, zip_to_pil, pil_to_tensor, tensor_to_pil, get_nai_token
from pathlib import Path
from datetime import datetime

# Constants
BOX_SIZE = 32
GRID_STEP = 8

SAMPLER_LIST = [
    "k_dpmpp_2m", "k_dpmpp_sde", "k_dpmpp_2m_sde", "k_dpmpp_2s_ancestral",
    "k_euler_ancestral", "k_euler", "ddim_v3"
]

SCHEDULER_LIST = ["karras"]

MODEL_DISPLAY_LIST = [
    "NAI Diffusion V4.5 Curated",
    "NAI Diffusion V4.5 Full",
    "NAI Diffusion V4 Full",
    "NAI Diffusion V4 Curated Preview",
    "NAI Diffusion V3",
    "NAI Diffusion Furry V3",
    "NAI Diffusion V2"
]

MODEL_ID_MAP = {
    "NAI Diffusion V4.5 Curated": "nai-diffusion-4-5-curated",
    "NAI Diffusion V4.5 Full": "nai-diffusion-4-5-full",
    "NAI Diffusion V4 Full": "nai-diffusion-4-full",
    "NAI Diffusion V4 Curated Preview": "nai-diffusion-4-curated-preview",
    "NAI Diffusion V3": "nai-diffusion-3",
    "NAI Diffusion Furry V3": "nai-diffusion-furry-3",
    "NAI Diffusion V2": "nai-diffusion-2"
}

# Helper Functions
def mask_to_grid_boxes(sam_mask_np, img_w, img_h, threshold=0.3):
    """
    SAM mask to BOX_SIZE(32px) grid boxes.
    Sliding with GRID_STEP(8px).
    """
    result = np.zeros((img_h, img_w), dtype=np.uint8)
    # Ensure sam_mask_np is 2D and 0-255
    if len(sam_mask_np.shape) == 3:
        sam_mask_np = sam_mask_np.squeeze()
    
    for y in range(0, img_h - BOX_SIZE + 1, GRID_STEP):
        for x in range(0, img_w - BOX_SIZE + 1, GRID_STEP):
            region = sam_mask_np[y:y + BOX_SIZE, x:x + BOX_SIZE]
            if region.mean() / 255.0 >= threshold:
                result[y:y + BOX_SIZE, x:x + BOX_SIZE] = 255
    return Image.fromarray(result, mode="L")

def pil_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

class CharacterPrompt:
    def __init__(self, prompt, uc, x, y):
        self.prompt = prompt
        self.uc = uc
        self.center = {"x": x, "y": y}

class CharacterPromptSelect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character1": ("STRING", {"default": "Input Character 1"}),
                "character1_uc": ("STRING", {"default": "negative_prompt"}),
                "character1_x": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character1_y": ("INT", {"default": 3, "min": 0, "max": 10}),
            },
            "optional": {
                "character2_enable": ("BOOLEAN", {"default": True}),
                "character2": ("STRING", {"default": "Input Character 2"}),
                "character2_uc": ("STRING", {"default": "negative_prompt"}),
                "character2_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character2_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character3_enable": ("BOOLEAN", {"default": False}),
                "character3": ("STRING", {"default": ""}),
                "character3_uc": ("STRING", {"default": "negative_prompt"}),
                "character3_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character3_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character4_enable": ("BOOLEAN", {"default": False}),
                "character4": ("STRING", {"default": ""}),
                "character4_uc": ("STRING", {"default": "negative_prompt"}),
                "character4_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character4_y": ("INT", {"default": 3, "min": 0, "max": 10}),
                "character5_enable": ("BOOLEAN", {"default": False}),
                "character5": ("STRING", {"default": ""}),
                "character5_uc": ("STRING", {"default": "negative_prompt"}),
                "character5_x": ("INT", {"default": 1, "min": 0, "max": 10}),
                "character5_y": ("INT", {"default": 3, "min": 0, "max": 10}),
            },
        }

    RETURN_TYPES = ("LIST",)
    RETURN_NAMES = ("CharacterPrompt",)
    FUNCTION = "build_character_prompt"
    CATEGORY = "RS_NovelAI_API/Characters"

    def build_character_prompt(self, **kwargs):
        character_prompts = []
        for i in range(1, 6):
            enable = kwargs.get(f"character{i}_enable", True) if i == 1 else kwargs.get(f"character{i}_enable", False)
            if enable:
                prompt = kwargs.get(f"character{i}", "")
                uc = kwargs.get(f"character{i}_uc", "")
                x_val = kwargs.get(f"character{i}_x", 0)
                y_val = kwargs.get(f"character{i}_y", 0)
                x = int(x_val * 0.099 * 10) / 10
                y = int(y_val * 0.099 * 10) / 10
                character_prompts.append(CharacterPrompt(prompt, uc, x, y))
        return (character_prompts,)

class NovelAIGenerator:
    def __init__(self):
        self.output_dir = self._get_output_directory()

    @classmethod
    def _get_output_directory(cls):
        try:
            import folder_paths
            return folder_paths.get_output_directory()
        except ImportError:
            output_dir = Path('./output')
            output_dir.mkdir(exist_ok=True)
            return str(output_dir)

    @classmethod
    def _get_save_path(cls, prefix, output_dir):
        current_date = datetime.now().strftime('%Y-%m-%d')
        autosave_folder = Path(output_dir) / current_date / 'NAI_autosave'
        autosave_folder.mkdir(parents=True, exist_ok=True)
        filename = f'{prefix}_{datetime.now().strftime("%y%m%d_%H%M%S")}'
        return autosave_folder, filename

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
                "characterPrompts": ("LIST",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, seed, 
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False, characterPrompts=None):
        token = get_nai_token()
        model_id = MODEL_ID_MAP.get(model, "nai-diffusion-4-5-curated")
        
        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        parameters = {
            "width": width,
            "height": height,
            "n_samples": 1,
            "seed": seed,
            "sampler": sampler,
            "steps": steps,
            "scale": cfg_scale,
            "negative_prompt": negative_prompt,
            "cfg_rescale": cfg_rescale,
            "prefer_brownian": prefer_brownian,
            "noise_schedule": scheduler,
            "params_version": 3,
            "legacy": False
        }

        if "4-5" in model_id:
            parameters["skip_cfg_above_sigma"] = 58
        elif "4" in model_id:
            parameters["skip_cfg_above_sigma"] = 19

        if "nai-diffusion-4" in model_id:
            char_captions = []
            neg_char_captions = []
            if characterPrompts:
                for cp in characterPrompts:
                    char_captions.append({"char_caption": cp.prompt, "centers": [cp.center]})
                    neg_char_captions.append({"char_caption": cp.uc, "centers": [cp.center]})
            
            parameters["v4_prompt"] = {
                "caption": {"base_caption": prompt, "char_captions": char_captions},
                "use_coords": bool(char_captions),
                "use_order": True
            }
            parameters["v4_negative_prompt"] = {
                "caption": {"base_caption": negative_prompt, "char_captions": neg_char_captions},
                "use_coords": False,
                "use_order": False
            }

        payload = {
            "input": prompt,
            "model": model_id,
            "action": "generate",
            "parameters": parameters
        }

        result_bytes = post_nai(token, payload)
        pil_img = zip_to_pil(result_bytes)
        
        # Autosave
        save_folder, filename = self._get_save_path('NAI', self.output_dir)
        save_path = save_folder / f'{filename}.png'
        pil_img.save(save_path)
        print(f'Image saved: {save_path}')
        
        return (pil_to_tensor(pil_img),)

class NAIImg2ImgNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False):
        token = get_nai_token()
        model_id = MODEL_ID_MAP.get(model, "nai-diffusion-4-5-curated")
        
        pil_img = tensor_to_pil(image).resize((width, height), Image.LANCZOS)
        
        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        parameters = {
            "width": width,
            "height": height,
            "n_samples": 1,
            "seed": seed,
            "sampler": sampler,
            "steps": steps,
            "scale": cfg_scale,
            "strength": strength,
            "negative_prompt": negative_prompt,
            "cfg_rescale": cfg_rescale,
            "prefer_brownian": prefer_brownian,
            "noise_schedule": scheduler,
            "image": pil_to_base64(pil_img),
            "params_version": 3,
            "legacy": False
        }

        if "4-5" in model_id:
            parameters["skip_cfg_above_sigma"] = 58
        elif "4" in model_id:
            parameters["skip_cfg_above_sigma"] = 19

        if "nai-diffusion-4" in model_id:
            parameters["v4_prompt"] = {"caption": {"base_caption": prompt, "char_captions": []}, "use_coords": False, "use_order": True}
            parameters["v4_negative_prompt"] = {"caption": {"base_caption": negative_prompt, "char_captions": []}, "use_coords": False, "use_order": False}

        payload = {
            "input": prompt,
            "model": model_id,
            "action": "img2img",
            "parameters": parameters
        }

        result_bytes = post_nai(token, payload)
        result_pil = zip_to_pil(result_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_i2i', NovelAIGenerator._get_output_directory())
        save_path = save_folder / f'{filename}.png'
        result_pil.save(save_path)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(result_pil),)

class NAIInpaintNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"default": "prompt here"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "width": ("INT", {"default": 832, "min": 64, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 4096, "step": 64}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate(self, image, mask, prompt, negative_prompt, model, width, height, sampler, steps, cfg_scale, strength, seed,
                 scheduler="karras", cfg_rescale=0.0, prefer_brownian=False):
        token = get_nai_token()
        model_id = MODEL_ID_MAP.get(model, "nai-diffusion-4-5-curated")
        
        # Snap width/height to 64
        width = (width // 64) * 64
        height = (height // 64) * 64
        
        pil_img = tensor_to_pil(image).resize((width, height), Image.LANCZOS)
        
        # Mask preprocessing
        if len(mask.shape) == 3:
            mask_np = (mask[0].cpu().numpy() * 255).astype(np.uint8)
        else:
            mask_np = (mask.cpu().numpy() * 255).astype(np.uint8)
        pil_mask = Image.fromarray(mask_np, mode="L").resize((width, height), Image.NEAREST)
        
        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)

        parameters = {
            "width": width,
            "height": height,
            "n_samples": 1,
            "seed": seed,
            "sampler": sampler,
            "steps": steps,
            "scale": cfg_scale,
            "negative_prompt": negative_prompt,
            "cfg_rescale": cfg_rescale,
            "prefer_brownian": prefer_brownian,
            "noise_schedule": scheduler,
            "image": pil_to_base64(pil_img),
            "mask": pil_to_base64(pil_mask),
            "add_original_image": True,
            "inpaintImg2ImgStrength": strength,
            "noise": 0,
            "params_version": 3,
            "legacy": False
        }

        if "4-5" in model_id:
            parameters["skip_cfg_above_sigma"] = 58
        elif "4" in model_id:
            parameters["skip_cfg_above_sigma"] = 19

        if "nai-diffusion-4" in model_id:
            parameters["v4_prompt"] = {"caption": {"base_caption": prompt, "char_captions": []}, "use_coords": False, "use_order": True}
            parameters["v4_negative_prompt"] = {"caption": {"base_caption": negative_prompt, "char_captions": []}, "use_coords": False, "use_order": False}

        payload = {
            "input": prompt,
            "model": model_id + "-inpainting",
            "action": "infill",
            "parameters": parameters
        }

        result_bytes = post_nai(token, payload)
        result_pil = zip_to_pil(result_bytes)

        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_inpaint', NovelAIGenerator._get_output_directory())
        save_path = save_folder / f'{filename}.png'
        result_pil.save(save_path)
        print(f'Image saved: {save_path}')

        return (pil_to_tensor(result_pil),)

class NAIFaceDetailerNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "bbox_detector": ("BBOX_DETECTOR",),
                "sam_model": ("SAM_MODEL",),
                "prompt": ("STRING", {"default": "smiling face, highly detailed"}),
                "negative_prompt": ("STRING", {"default": "lowres, bad anatomy"}),
                "model": (MODEL_DISPLAY_LIST, {"default": MODEL_DISPLAY_LIST[0]}),
                "strength": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
                "threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
                "feather_radius": ("INT", {"default": 10, "min": 0, "max": 100}),
                "sampler": (SAMPLER_LIST, {"default": "k_euler"}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 50}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "bbox_threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "dilation": ("INT", {"default": 4, "min": 0, "max": 64}),
                "crop_factor": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "scheduler": (SCHEDULER_LIST, {"default": "karras"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffff}),
            },
            "optional": {
                "eye_bbox_detector": ("BBOX_DETECTOR",),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("image", "mask_visualization")
    FUNCTION = "detail"
    CATEGORY = "RS_NovelAI_API/FaceDetailer"

    def detail(self, image, bbox_detector, sam_model, prompt, negative_prompt, model, strength, threshold, feather_radius,
               sampler, steps, cfg_scale, bbox_threshold, dilation, crop_factor, scheduler, seed, eye_bbox_detector=None):
        token = get_nai_token()
        model_id = MODEL_ID_MAP.get(model, "nai-diffusion-4-5-curated")
        
        pil_img = tensor_to_pil(image)
        w, h = pil_img.size

        # 1. Bbox detection
        segs = bbox_detector.detect(image, bbox_threshold, dilation, crop_factor, drop_size=10, detailer_hook=None)
        if not segs or len(segs[1]) == 0:
            return (image, image)
        
        seg = segs[1][0]
        bbox = seg.bbox  # (x1, y1, x2, y2)
        bx0, by0, bx1, by1 = bbox
        crx0, cry0, crx1, cry1 = [int(v) for v in seg.crop_region]
        
        # 2. Crop to crop_region
        crop_img = pil_img.crop((crx0, cry0, crx1, cry1))
        cw, ch = crop_img.size
        
        # 3. Upscale calculation
        scale = 1024 / max(cw, ch)
        nw = max(64, (round(cw * scale) // 64) * 64)
        nh = max(64, (round(ch * scale) // 64) * 64)
        
        # 4. Resize crop
        scaled_img = crop_img.resize((nw, nh), Image.LANCZOS)
        
        # 5. SAM Predictor
        from segment_anything import SamPredictor
        predictor = SamPredictor(sam_model)
        predictor.set_image(np.array(scaled_img.convert('RGB')))
        
        # 6. Face segmentation on scaled relative coordinates
        sx, sy = nw / cw, nh / ch
        face_x0 = (bx0 - crx0) * sx
        face_y0 = (by0 - cry0) * sy
        face_x1 = (bx1 - crx0) * sx
        face_y1 = (by1 - cry0) * sy
        input_box = np.array([[face_x0, face_y0, face_x1, face_y1]], dtype=float)
        
        # 7. Predict
        masks, scores, _ = predictor.predict(box=input_box, multimask_output=False)
        
        # 8. Mask processing
        mask_np = (masks[0] * 255).astype(np.uint8)

        # Eye region augmentation (optional)
        if eye_bbox_detector is not None:
            eye_tensor = pil_to_tensor(scaled_img)
            eye_segs = eye_bbox_detector.detect(eye_tensor, bbox_threshold, dilation, 1.0, drop_size=4, detailer_hook=None)
            if eye_segs and len(eye_segs[1]) > 0:
                for eye_seg in eye_segs[1]:
                    ex0 = max(0, int(eye_seg.crop_region[0]))
                    ey0 = max(0, int(eye_seg.crop_region[1]))
                    ex1 = min(nw, int(eye_seg.crop_region[2]))
                    ey1 = min(nh, int(eye_seg.crop_region[3]))
                    mask_np[ey0:ey1, ex0:ex1] = 255
        
        # 9. mask_to_grid_boxes
        scaled_mask = mask_to_grid_boxes(mask_np, nw, nh, threshold=threshold)
        
        # 10. NAI Inpaint
        if seed == -1:
            seed = np.random.randint(0, 0x7fffffff)
            
        parameters = {
            "width": nw,
            "height": nh,
            "n_samples": 1,
            "seed": seed,
            "sampler": sampler,
            "steps": steps,
            "scale": cfg_scale,
            "negative_prompt": negative_prompt,
            "cfg_rescale": 0.0,
            "prefer_brownian": False,
            "noise_schedule": scheduler,
            "image": pil_to_base64(scaled_img),
            "mask": pil_to_base64(scaled_mask),
            "add_original_image": True,
            "inpaintImg2ImgStrength": strength,
            "noise": 0,
            "params_version": 3,
            "legacy": False
        }
        
        if "4-5" in model_id:
            parameters["skip_cfg_above_sigma"] = 58
        elif "4" in model_id:
            parameters["skip_cfg_above_sigma"] = 19

        if "nai-diffusion-4" in model_id:
            parameters["v4_prompt"] = {"caption": {"base_caption": prompt, "char_captions": []}, "use_coords": False, "use_order": True}
            parameters["v4_negative_prompt"] = {"caption": {"base_caption": negative_prompt, "char_captions": []}, "use_coords": False, "use_order": False}

        payload = {
            "input": prompt,
            "model": model_id + "-inpainting",
            "action": "infill",
            "parameters": parameters
        }
        
        result_bytes = post_nai(token, payload)
        
        # 11. Convert result to PIL
        result_pil = zip_to_pil(result_bytes)
        
        # 12. Downscale result
        result_downscaled = result_pil.resize((cw, ch), Image.LANCZOS)
        
        # 13. Paste result directly (NAI infill preserves non-masked area internally)
        # feather_radius is kept in signature but not used here.
        out_img = pil_img.copy()
        out_img.paste(result_downscaled, (crx0, cry0))
        
        # Autosave
        save_folder, filename = NovelAIGenerator._get_save_path('NAI_face', NovelAIGenerator._get_output_directory())
        save_path = save_folder / f'{filename}.png'
        out_img.save(save_path)
        print(f'Image saved: {save_path}')

        # Visualization mask
        vis_mask = Image.new("L", (w, h), 0)
        vis_mask.paste(scaled_mask.resize((cw, ch), Image.NEAREST), (crx0, cry0))
        vis_mask_rgb = Image.merge("RGB", (vis_mask, vis_mask, vis_mask))

        return (pil_to_tensor(out_img), pil_to_tensor(vis_mask_rgb))

class NAIUpscalerNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "scale": ([2, 4], {"default": 2}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"
    CATEGORY = "RS_NovelAI_API/Upscale"

    def upscale(self, image, scale):
        token = get_nai_token()
        pil_img = tensor_to_pil(image)
        
        payload = {
            "image": pil_to_base64(pil_img),
            "width": pil_img.width,
            "height": pil_img.height,
            "scale": scale
        }
        
        result_bytes = post_nai(token, payload, url="https://api.novelai.net/ai/upscale")
        img = zip_to_pil(result_bytes)
        return (pil_to_tensor(img),)

NODE_CLASS_MAPPINGS = {
    "NovelAIGenerator": NovelAIGenerator,
    "CharacterPromptSelect": CharacterPromptSelect,
    "NAIImg2ImgNode": NAIImg2ImgNode,
    "NAIInpaintNode": NAIInpaintNode,
    "NAIFaceDetailerNode": NAIFaceDetailerNode,
    "NAIUpscalerNode": NAIUpscalerNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NovelAIGenerator": "NAI Image Generator",
    "CharacterPromptSelect": "NAI Character Prompt Select",
    "NAIImg2ImgNode": "NAI Img2Img",
    "NAIInpaintNode": "NAI Inpaint",
    "NAIFaceDetailerNode": "NAI Face Detailer",
    "NAIUpscalerNode": "NAI Upscaler"
}
