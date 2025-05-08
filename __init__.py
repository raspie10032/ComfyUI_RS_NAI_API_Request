from .converters import CONVERTER_NODE_CLASS_MAPPINGS, CONVERTER_NODE_DISPLAY_NAME_MAPPINGS
from .generators import GENERATOR_NODE_CLASS_MAPPINGS, GENERATOR_NODE_DISPLAY_NAME_MAPPINGS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Integrate nodes defined in each file into a single dictionary
NODE_CLASS_MAPPINGS = {
    **CONVERTER_NODE_CLASS_MAPPINGS,
    **GENERATOR_NODE_CLASS_MAPPINGS
}

# Integrate node display names defined in each file into a single dictionary
NODE_DISPLAY_NAME_MAPPINGS = {
    **CONVERTER_NODE_DISPLAY_NAME_MAPPINGS,
    **GENERATOR_NODE_DISPLAY_NAME_MAPPINGS
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]