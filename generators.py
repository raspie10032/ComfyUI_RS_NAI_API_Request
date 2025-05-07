import os
import zipfile
import aiohttp
import asyncio
import json
import base64
import torch
import numpy as np
from PIL import Image
from io import BytesIO
from typing import Optional, List, Union, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

ucPreset_list = [
    "blurry, lowres, error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, logo, dated, signature, multiple views, gigantic breasts",
    "blurry, lowres, error, worst quality, bad quality, jpeg artifacts, very displeasing, logo, dated, signature",
    ""
]


async def post_novelai(url, data, header):
    """
    Send a POST request to the NovelAI API
    
    Args:
        url: API endpoint URL
        data: Request data (JSON)
        header: Request headers with auth token
        
    Returns:
        Response data or raises an exception
    """
    async with aiohttp.ClientSession(headers=header) as session:
        try:
            async with session.post(url, json=data) as response:
                if response.status == 429:
                    resp = await response.json()
                    message = resp.get("message", "Too many requests, retrying...")
                    print(f"Rate limit hit: {message}")
                    await asyncio.sleep(5)
                    return await post_novelai(url, data, header)
                elif response.status == 401:
                    raise ValueError("Invalid NovelAI token. Check your NAI_ACCESS_TOKEN in .env file.")
                elif response.status == 200:
                    return await response.read()
                else:
                    raise Exception(f"Request failed with status {response.status}: {await response.text()}")
        except Exception as e:
            print(f"Error during request: {e}")
            raise e


class CharacterPrompt:
    def __init__(self, prompt: str, uc: str, x: float, y: float):
        self.prompt = prompt
        self.uc = uc
        self.x = x
        self.y = y
        self.center = {"x": self.x, "y": self.y}


class BaseRequest:
    def __init__(
            self,
            prompt: Optional[str] = "",
            negative_prompt: Optional[str] = "",
            seed: int = -1,
            sampler_name: str = "Euler a",
            batch_size: int = 1,
            n_iter: int = 1,
            steps: int = 23,
            cfg_scale: float = 5,
            width: int = 832,
            height: int = 1216,
            denoising_strength: float = 1,
            scheduler: str = "Automatic",
            send_images: bool = True,
            save_images: bool = True,
            override_settings: Dict[str, Any] = {},
            override_settings_restore_afterwards: bool = False
    ):
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.seed = seed
        self.sampler_name = sampler_name
        self.batch_size = batch_size
        self.n_iter = n_iter
        self.steps = steps
        self.cfg_scale = cfg_scale
        self.width = width
        self.height = height
        self.denoising_strength = denoising_strength
        self.scheduler = scheduler
        self.send_images = send_images
        self.save_images = save_images
        self.override_settings = override_settings
        self.override_settings_restore_afterwards = override_settings_restore_afterwards


class NovelAITXT2IMGPayload(BaseRequest):
    def __init__(
            self, ucPreset: int, cfg_rescale: int, 
            characterPrompts: list[CharacterPrompt]|list,
            prefer_brownian: bool, base_request: BaseRequest, model,
            use_coords: bool = True, use_order: bool = True
    ):
        super().__init__(**vars(base_request))

        self.scale = base_request.cfg_scale
        self.sampler = base_request.sampler_name
        self.n_samples = base_request.n_iter
        self.ucPreset = ucPreset
        self.cfg_rescale = cfg_rescale
        self.noise_schedule = base_request.scheduler
        self.characterPrompts = characterPrompts
        self.model = model
        self.use_coords = use_coords
        self.use_order = use_order
        
        characterPrompts_list = []

        for cp in self.characterPrompts:
            cp = dict(vars(cp))
            del cp['x']
            del cp['y']
            characterPrompts_list.append(cp)

        self.characterPrompts = characterPrompts_list
        char_captions = []
        for cp in self.characterPrompts:
            char_captions.append({"char_caption": cp["prompt"], "centers": [cp["center"]]})
        self.v4_prompt = {
            "caption": {
                "base_caption": self.prompt,
                "char_captions": char_captions
            },
            "use_coords": self.use_coords,
            "use_order": self.use_order
        }
        char_captions = []
        for cp in self.characterPrompts:
            char_captions.append({"char_caption": cp["uc"], "centers": [cp["center"]]})
        self.v4_negative_prompt = {
            "caption": {
                "base_caption": self.negative_prompt,
                "char_captions": char_captions
            },
            "use_coords": False,
            "use_order": False
        }
        self.prefer_brownian = prefer_brownian


def tensor_to_pil(img_tensor, batch_index=0):
    # Takes an image in a batch in the form of a tensor of shape [batch_size, channels, height, width]
    # and returns an PIL Image with the corresponding mode deduced by the number of channels

    # Take the image in the batch given by batch_index
    img_tensor = img_tensor[batch_index].unsqueeze(0)
    i = 255. * img_tensor.cpu().numpy()
    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8).squeeze())
    return img


def pil_to_tensor(image):
    # Takes a PIL image and returns a tensor of shape [1, height, width, channels]
    image = np.array(image).astype(np.float32) / 255.0
    image = torch.from_numpy(image).unsqueeze(0)
    if len(image.shape) == 3:  # If the image is grayscale, add a channel dimension
        image = image.unsqueeze(-1)
    return image


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
    OUTPUT_NODE = False
    CATEGORY = "RS_NovelAI_API/Characters"

    def build_character_prompt(
        self, character1, character1_uc, character1_x, character1_y,
        character2_enable, character2, character2_uc, character2_x, character2_y, 
        character3_enable, character3, character3_uc, character3_x, character3_y, 
        character4_enable, character4, character4_uc, character4_x, character4_y, 
        character5_enable, character5, character5_uc, character5_x, character5_y
    ):
        # Convert integer coordinates to float (0-10 -> 0.0-1.0)
        character1_pos = {"x": int(character1_x * 0.099 * 10) / 10, "y": int(character1_y * 0.099 * 10) / 10}
        character2_pos = {"x": int(character2_x * 0.099 * 10) / 10, "y": int(character2_y * 0.099 * 10) / 10}
        character3_pos = {"x": int(character3_x * 0.099 * 10) / 10, "y": int(character3_y * 0.099 * 10) / 10}
        character4_pos = {"x": int(character4_x * 0.099 * 10) / 10, "y": int(character4_y * 0.099 * 10) / 10}
        character5_pos = {"x": int(character5_x * 0.099 * 10) / 10, "y": int(character5_y * 0.099 * 10) / 10}

        character_prompts = []

        character_prompts.append(CharacterPrompt(character1, character1_uc, character1_pos["x"], character1_pos["y"]))

        if character2_enable:
            character_prompts.append(CharacterPrompt(character2, character2_uc, character2_pos["x"], character2_pos["y"]))
        if character3_enable:
            character_prompts.append(CharacterPrompt(character3, character3_uc, character3_pos["x"], character3_pos["y"]))
        if character4_enable:
            character_prompts.append(CharacterPrompt(character4, character4_uc, character4_pos["x"], character4_pos["y"]))
        if character5_enable:
            character_prompts.append(CharacterPrompt(character5, character5_uc, character5_pos["x"], character5_pos["y"]))

        return (character_prompts,)


class NovelAIGenerator:
    """
    Node that creates and processes NovelAI requests for image generation.
    Gets the API token from environment variables.
    """

    @classmethod
    def INPUT_TYPES(cls):
        sampler_list = [
            "k_dpmpp_2m", "k_dpmpp_sde", "k_dpmpp_2m_sde", "k_dpmpp_2s_ancestral",
            "k_euler_ancestral", "k_euler", "ddim_v3"
        ]
        scheduler_list = ["karras"]

        # Display model names list
        model_display_list = [
            "NAI Diffusion V4.5 Curated",
            "NAI Diffusion V4 Full",
            "NAI Diffusion V4 Curated Preview",
            "NAI Diffusion V3",
            "NAI Diffusion Furry V3",
            "NAI Diffusion V2"
        ]

        return {
            "required": {
                "prompt": ("STRING", {"default": "prompt here"})
            },
            "optional": {
                "negative_prompt": ("STRING", {"default": "negative prompt here"}),
                "seed": ("INT", {"default": -1}),
                "sampler": (sampler_list,),
                "n_iter": ("INT", {"default": 1}),
                "steps": ("INT", {"default": 28}),
                "cfg_scale": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.5, "display": "%.1f"}),
                "width": ("INT", {"default": 832}),
                "height": ("INT", {"default": 1216}),
                "scheduler": (scheduler_list,),
                "ucPreset": (ucPreset_list,),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "display": "%.2f"}),
                "characterPrompts": ("LIST",),
                "prefer_brownian": ("BOOLEAN", {"default": False}),
                "use_coords": ("BOOLEAN", {"default": True}),
                "use_order": ("BOOLEAN", {"default": True}),
                "model": (model_display_list, {"default": model_display_list[0]})
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "generate_image"
    OUTPUT_NODE = True
    CATEGORY = "RS_NovelAI_API/Generation"

    def generate_image(
            self,
            prompt,
            negative_prompt="",
            seed=-1,
            sampler="k_euler",
            n_iter=1,
            steps=28,
            cfg_scale=6.0,
            width=832,
            height=1216,
            scheduler="karras",
            ucPreset=ucPreset_list[0],
            cfg_rescale=0,
            characterPrompts=[],
            prefer_brownian=False,
            use_coords=True,
            use_order=True,
            model="NAI Diffusion V4.5 Curated"
    ):
        # Convert model display name to API model ID
        model_ids = {
            "NAI Diffusion V4.5 Curated": "nai-diffusion-4-5-curated",
            "NAI Diffusion V4 Full": "nai-diffusion-4-full",
            "NAI Diffusion V4 Curated Preview": "nai-diffusion-4-curated-preview",
            "NAI Diffusion V3": "nai-diffusion-3",
            "NAI Diffusion Furry V3": "nai-diffusion-furry-3",
            "NAI Diffusion V2": "nai-diffusion-2"
        }
        model_id = model_ids.get(model, "nai-diffusion-4-5-curated")

        # Create base request
        negative_prompt = negative_prompt + "," + ucPreset
        base_request = BaseRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            sampler_name=sampler,
            n_iter=n_iter,
            steps=steps,
            cfg_scale=cfg_scale,
            width=width,
            height=height,
            scheduler=scheduler,
        )

        # Get ucPreset index
        ucPreset_index = ucPreset_list.index(ucPreset)

        # Create payload
        payload = NovelAITXT2IMGPayload(
            ucPreset_index,
            cfg_rescale,
            characterPrompts,
            prefer_brownian,
            base_request,
            model_id,
            use_coords,
            use_order
        )

        # Prepare for API request
        save_path = "./temp/api_request"
        if not os.path.exists(save_path):
            os.makedirs(save_path)

        # Get token from environment variable
        token = os.getenv("NAI_ACCESS_TOKEN", "")
        if not token:
            print("WARNING: NAI_ACCESS_TOKEN environment variable is not set or empty.")
            print("Please set your NovelAI token in your .env file with the key NAI_ACCESS_TOKEN")
            raise ValueError("NovelAI token not found. Set NAI_ACCESS_TOKEN in your .env file.")
            
        header = {
            "authorization": "Bearer " + token,
            ":authority": "https://api.novelai.net",
            ":path": "/ai/generate-image",
            "content-type": "application/json",
            "referer": "https://novelai.net",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
        }

        api_payload = {
            "input": payload.prompt,
            "model": payload.model,
            "parameters": dict(vars(payload))
        }

        # Make the API request
        response_data = asyncio.run(post_novelai("https://image.novelai.net/ai/generate-image", api_payload, header))

        # Process the response
        with zipfile.ZipFile(BytesIO(response_data)) as z:
            z.extractall(save_path)

        image_bytes = []
        for filename in os.listdir(save_path):
            if filename.endswith('.png'):
                file_path = os.path.join(save_path, filename)
                with open(file_path, "rb") as image_file:
                    image_data = image_file.read()
                    image_bytes.append(image_data)

        # Convert images to tensors
        tensor_images = []
        for img_data in image_bytes:
            img = Image.open(BytesIO(img_data))
            tensor_img = pil_to_tensor(img)
            tensor_images.append(tensor_img)

        tensor = torch.cat(tensor_images, dim=0)
        return (tensor,)


# Node class mappings
GENERATOR_NODE_CLASS_MAPPINGS = {
    "CharacterPromptSelect": CharacterPromptSelect,
    "NovelAIGenerator": NovelAIGenerator
}

# Node display name mappings
GENERATOR_NODE_DISPLAY_NAME_MAPPINGS = {
    "CharacterPromptSelect": "NAI Character Prompt Select",
    "NovelAIGenerator": "NAI Image Generator"
}

# Model ID and display name mapping for external use
MODEL_DISPLAY_NAMES = {
    "nai-diffusion-4-5-curated": "NAI Diffusion V4.5 Curated",
    "nai-diffusion-4-full": "NAI Diffusion V4 Full",
    "nai-diffusion-4-curated-preview": "NAI Diffusion V4 Curated Preview",
    "nai-diffusion-3": "NAI Diffusion V3",
    "nai-diffusion-furry-3": "NAI Diffusion Furry V3",
    "nai-diffusion-2": "NAI Diffusion V2"
}