import re
import base64
import math

class ComfyUIToNovelAIV4Converter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "comfyui_prompt": ("STRING", {"multiline": True, "default": "qw, a, (b c:1.05), d, e\\(f: g h\\), black bikini top, (negative example:-1.5), shorts under bikini bottom, (i j:1.2)"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, comfyui_prompt):
        # Preprocessing: Replace "artist:" with "__artist__"
        comfyui_prompt = comfyui_prompt.replace("artist:", "__artist__")
        
        processed_prompt = comfyui_prompt.replace(r"\\(", "(").replace(r"\\)", ")")
        novelai_parts = []

        elements = re.split(r'(?<!\\)([,()])', processed_prompt)
        processed_elements = [el.strip() for el in elements if el.strip()]

        i = 0
        while i < len(processed_elements):
            element = processed_elements[i]
            if element == '(':
                i += 1
                content = ""
                balance = 1
                while i < len(processed_elements):
                    sub_element = processed_elements[i]
                    if sub_element == '(':
                        balance += 1
                    elif sub_element == ')':
                        balance -= 1
                        if balance == 0:
                            i += 1
                            break
                    content += sub_element
                    i += 1

                if content:
                    match_weight = re.search(r':([\d.-]+)\s*$', content)
                    weight = 1.1
                    tags_str = content
                    if match_weight:
                        try:
                            weight = float(match_weight.group(1))
                            tags_str = content[:match_weight.start()].strip()
                            if not (-5 <= weight <= 5):
                                print(f"Warning: Weight '{weight}' is outside the -5 to 5 range. Using default value 1.1 for: {tags_str}")
                                weight = 1.1
                        except ValueError:
                            print(f"Warning: Invalid weight format '{match_weight.group(1)}'. Using default value 1.1 for: {tags_str}")

                    if tags_str:
                        novelai_parts.append(f"{weight}::{tags_str}::")

            elif element == ',':
                novelai_parts.append(',')
                i += 1
            else:
                if element:
                    novelai_parts.append(element)
                i += 1

        final_prompt = "".join(novelai_parts).replace("\\", "") # Remove backslashes after final conversion
        final_prompt_with_spaces = ""
        for part in final_prompt.split(','):
            final_prompt_with_spaces += part.strip() + ', '
        final_prompt_with_spaces = final_prompt_with_spaces.rstrip(', ') # Remove trailing comma and space
        
        # Postprocessing: Replace "__artist__" with "artist:"
        final_prompt_with_spaces = final_prompt_with_spaces.replace("__artist__", "artist:")

        return (final_prompt_with_spaces,)

class NovelAIV4ToComfyUIConverter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "novelai_prompt": ("STRING", {"multiline": True, "default": "qw, a, 1.05::b c::, d, e(f: g h), black bikini top, -1.5::negative example::, shorts under bikini bottom, 1.2::i j::"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("comfyui_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_prompt):
        # Preprocessing: Replace "artist:" with "__artist__"
        novelai_prompt = novelai_prompt.replace("artist:", "__artist__")
        
        processed_prompt = novelai_prompt.replace("(", r"\(").replace(")", r"\)")
        processed_prompt = processed_prompt.replace(r"\(", "__escopen__").replace(r"\)", "__escclose__")

        def encode_tags(tags_string):
            # Base64 인코딩 유지 - 패딩 제거하지 않음
            return base64.b64encode(tags_string.encode('utf-8')).decode('utf-8')

        def decode_tags(encoded_string):
            try:
                # Base64 디코딩
                return base64.b64decode(encoded_string).decode('utf-8')
            except:
                return encoded_string

        def replace_with_encoded(match):
            weight = match.group(1)
            tags_str = match.group(2)
            encoded_tags = encode_tags(tags_str)
            return f"{weight}::__TEMP_ENCODED__({encoded_tags})__TEMP_ENCODED_END__"

        processed_prompt = re.sub(r"([\d.-]+)::([^:]+?)::", replace_with_encoded, processed_prompt)

        comfyui_parts = []
        for part in processed_prompt.split(','):
            part = part.strip()
            if "__TEMP_ENCODED__" in part:
                match = re.match(r"([\d.-]+)::(__TEMP_ENCODED__\((.+?)\)__TEMP_ENCODED_END__)", part)
                if match:
                    weight = match.group(1)
                    encoded_tags = match.group(3)
                    comfyui_parts.append(f"(__TEMP_ENCODED__({encoded_tags}):{weight})")
                else:
                    comfyui_parts.append(part)
            else:
                comfyui_parts.append(part)

        comfyui_prompt = ", ".join(comfyui_parts)

        def replace_encoded_with_decoded(match):
            encoded_tags = match.group(1)
            weight = match.group(2)
            decoded_tags = decode_tags(encoded_tags).replace("__escopen__", "(").replace("__escclose__", ")")
            return f"({decoded_tags}:{weight})"

        comfyui_prompt = re.sub(r"__TEMP_ENCODED__\((.+?)\):([\d.-]+)", replace_encoded_with_decoded, comfyui_prompt)

        comfyui_prompt = comfyui_prompt.replace("__escopen__", r"\(").replace("__escclose__", r"\)")
        comfyui_prompt = comfyui_prompt.replace("((", "(").replace("))", ")")
        comfyui_prompt = re.sub(r",(?!\s)", ", ", comfyui_prompt)
        
        # Postprocessing: Replace "__artist__" with "artist:"
        comfyui_prompt = comfyui_prompt.replace("__artist__", "artist:")

        return (comfyui_prompt,)

class NovelAIV4ToOldNAIConverter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "novelai_v4_prompt": ("STRING", {"multiline": True, "default": "1.05::tag1::, 0.9::tag3::, 1.2::tag4::, 1.1::misty, golden hour::, -1.5::negative tag::, 0::zero weight tag::"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_old_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_v4_prompt):
        # Preprocessing: Replace "artist:" with "__artist__"
        novelai_v4_prompt = novelai_v4_prompt.replace("artist:", "__artist__")
        
        def find_closest_power(weight, base):
            """Find the closest exponent value to the weight using logarithm function"""
            if weight <= 0 or base <= 0 or base == 1:
                return 0
            exponent = math.log(weight) / math.log(base)
            return round(exponent)
            
        # Define regex pattern - find weight::tag:: format
        # This pattern treats any content between :: as a single tag unit, including commas
        pattern = r'([\d.-]+)::([^:]+?)::'
        
        # Find weight::tag:: format
        tags_with_weights = re.finditer(pattern, novelai_v4_prompt)
        
        # Record processed parts
        processed_spans = []
        old_nai_parts = []
        
        # Process tags with weights first
        for match in tags_with_weights:
            weight_str = match.group(1)
            tags = match.group(2).strip()
            start, end = match.span()
            processed_spans.append((start, end))
            
            try:
                weight = float(weight_str)
                
                if weight <= 0:
                    # Handle negative or zero weights
                    print(f"Warning: Old NAI format cannot represent negative or zero weights. Applying the default decrease weight of 0.95 > '[{tags}]' instead.")
                    old_nai_parts.append((start, f"[{tags}]"))
                elif weight < 1:
                    # Decreased weight - use square brackets
                    n_095 = find_closest_power(weight, 0.95)
                    if n_095 < 0:
                        old_nai_parts.append((start, "[" * abs(n_095) + tags + "]" * abs(n_095)))
                    else:
                        old_nai_parts.append((start, tags))
                elif weight == 1:
                    # Weight 1.0 - keep as is
                    old_nai_parts.append((start, tags))
                else:
                    # Increased weight - use curly braces
                    n_105 = find_closest_power(weight, 1.05)
                    if n_105 > 0:
                        old_nai_parts.append((start, "{" * n_105 + tags + "}" * n_105))
                    else:
                        old_nai_parts.append((start, tags))
            except ValueError:
                # Keep original if weight conversion fails
                old_nai_parts.append((start, match.group(0)))
        
        # Find unprocessed parts
        last_end = 0
        for start, end in sorted(processed_spans):
            if start > last_end:
                # Add unprocessed part
                remaining = novelai_v4_prompt[last_end:start].strip()
                if remaining:
                    # Split by commas and add
                    for part in remaining.split(','):
                        if part.strip():
                            old_nai_parts.append((last_end, part.strip()))
            last_end = end
        
        # Add the last unprocessed part
        if last_end < len(novelai_v4_prompt):
            remaining = novelai_v4_prompt[last_end:].strip()
            if remaining:
                # Split by commas and add
                for part in remaining.split(','):
                    if part.strip():
                        old_nai_parts.append((last_end, part.strip()))
        
        # Sort by position
        old_nai_parts.sort()
        
        # Combine final result (remove position info)
        final_prompt = ", ".join(part[1] for part in old_nai_parts)
        
        # Postprocessing: Replace "__artist__" with "artist:"
        final_prompt = final_prompt.replace("__artist__", "artist:")
        
        return (final_prompt,)

class OldNAIToNovelAIV4Converter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "novelai_old_prompt": ("STRING", {"multiline": True, "default": "{tag1}, [tag2], {{tag3}}, [[tag4]], tag5, {{{important tag}}}, {{misty, golden hour}}"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_v4_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_old_prompt):
        # Preprocessing: Replace "artist:" with "__artist__"
        novelai_old_prompt = novelai_old_prompt.replace("artist:", "__artist__")
        
        # Define regex pattern - patterns enclosed in curly braces or square brackets
        # Treat contents with commas inside brackets as a single tag
        pattern = r'([{\[]+)([^}\]]+?)([}\]]+)'
        
        # Store pattern matching results and positions
        matches = list(re.finditer(pattern, novelai_old_prompt))
        processed_spans = []
        
        # Store conversion results
        result_parts = []
        
        for match in matches:
            prefix = match.group(1)  # Opening brackets
            content = match.group(2).strip()  # Content inside brackets
            suffix = match.group(3)  # Closing brackets
            start, end = match.span()
            
            processed_spans.append((start, end))
            
            # Check bracket balance
            if prefix.count('{') == suffix.count('}') and prefix.count('[') == suffix.count(']'):
                # Calculate weight based on bracket type and count
                curly_count = prefix.count('{')
                square_count = prefix.count('[')
                
                weight = 1.0
                if curly_count > 0 and square_count == 0:
                    # Curly braces increase weight (1.05^n)
                    weight = 1.05 ** curly_count
                elif square_count > 0 and curly_count == 0:
                    # Square brackets decrease weight (0.95^n)
                    weight = 0.95 ** square_count
                
                if weight != 1.0:
                    # Display up to two decimal places (remove unnecessary zeros)
                    weight_str = f"{weight:.2f}".rstrip('0').rstrip('.')
                    result_parts.append((start, f"{weight_str}::{content}::"))
                else:
                    result_parts.append((start, content))
            else:
                # Keep original if brackets are unbalanced
                result_parts.append((start, match.group(0)))
        
        # Process unprocessed parts
        last_end = 0
        for start, end in sorted(processed_spans):
            if start > last_end:
                # Analyze unprocessed text
                unprocessed = novelai_old_prompt[last_end:start].strip()
                if unprocessed:
                    # Process each part separated by commas
                    for part in re.split(r',', unprocessed):
                        part = part.strip()
                        if part:
                            result_parts.append((last_end, part))
            last_end = end
        
        # Process the last unprocessed part
        if last_end < len(novelai_old_prompt):
            unprocessed = novelai_old_prompt[last_end:].strip()
            if unprocessed:
                # Process each part separated by commas
                for part in re.split(r',', unprocessed):
                    part = part.strip()
                    if part:
                        result_parts.append((last_end, part))
        
        # Sort by position
        result_parts.sort()
        
        # Combine final converted prompt
        if result_parts:
            # Combine all parts into a single string
            final_prompt = ", ".join(part[1] for part in result_parts)
        else:
            # Keep original if nothing to convert
            final_prompt = novelai_old_prompt.strip()
            
        # Postprocessing: Replace "__artist__" with "artist:"
        final_prompt = final_prompt.replace("__artist__", "artist:")
            
        return (final_prompt,)

class ComfyUIToOldNAIConverter:
    def __init__(self):
        self.comfyui_to_novelaiv4 = ComfyUIToNovelAIV4Converter()
        self.novelaiv4_to_oldnai = NovelAIV4ToOldNAIConverter()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "comfyui_prompt": ("STRING", {"multiline": True, "default": "qw, a, (b c:1.05), d, e\\(f: g h\\), black bikini top, denim shorts, shorts under bikini bottom, (i j:1.2)"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("novelai_old_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, comfyui_prompt):
        # First conversion: ComfyUI → NovelAI V4
        novelai_v4_prompt = self.comfyui_to_novelaiv4.convert_prompt(comfyui_prompt)[0]
        
        # Second conversion: NovelAI V4 → Old NAI
        novelai_old_prompt = self.novelaiv4_to_oldnai.convert_prompt(novelai_v4_prompt)[0]
        
        return (novelai_old_prompt,)


class OldNAIToComfyUIConverter:
    def __init__(self):
        self.oldnai_to_novelaiv4 = OldNAIToNovelAIV4Converter()
        self.novelaiv4_to_comfyui = NovelAIV4ToComfyUIConverter()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "novelai_old_prompt": ("STRING", {"multiline": True, "default": "{tag1}, [tag2], {{tag3}}, [[tag4]], tag5, {{{important tag}}}, {{misty, golden hour}}"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("comfyui_prompt",)
    FUNCTION = "convert_prompt"
    CATEGORY = "RS_NovelAI_API/Converters"

    def convert_prompt(self, novelai_old_prompt):
        # First conversion: Old NAI → NovelAI V4
        novelai_v4_prompt = self.oldnai_to_novelaiv4.convert_prompt(novelai_old_prompt)[0]
        
        # Second conversion: NovelAI V4 → ComfyUI
        comfyui_prompt = self.novelaiv4_to_comfyui.convert_prompt(novelai_v4_prompt)[0]
        
        return (comfyui_prompt,)



# Node class mappings
CONVERTER_NODE_CLASS_MAPPINGS = {
    "ComfyUIToNovelAIV4": ComfyUIToNovelAIV4Converter,
    "NovelAIV4ToComfyUI": NovelAIV4ToComfyUIConverter,
    "NovelAIV4ToOldNAI": NovelAIV4ToOldNAIConverter,
    "OldNAIToNovelAIV4": OldNAIToNovelAIV4Converter,
    "ComfyUIToOldNAI": ComfyUIToOldNAIConverter,
    "OldNAIToComfyUI": OldNAIToComfyUIConverter,
}

# Node display name mappings
CONVERTER_NODE_DISPLAY_NAME_MAPPINGS = {
    "ComfyUIToNovelAIV4": "Convert ComfyUI to Novel AI V4",
    "NovelAIV4ToComfyUI": "Convert Novel AI V4 to ComfyUI",
    "NovelAIV4ToOldNAI": "Convert Novel AI V4 to Old NAI",
    "OldNAIToNovelAIV4": "Convert Old NAI to Novel AI V4",
    "ComfyUIToOldNAI": "Convert ComfyUI to Old NAI",
    "OldNAIToComfyUI": "Convert Old NAI to ComfyUI",
}