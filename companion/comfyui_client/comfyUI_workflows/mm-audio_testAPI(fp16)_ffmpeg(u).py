import os
import random
import sys
from typing import Sequence, Mapping, Any, Union
import torch


def get_value_at_index(obj: Union[Sequence, Mapping], index: int) -> Any:
    """Returns the value at the given index of a sequence or mapping.

    If the object is a sequence (like list or string), returns the value at the given index.
    If the object is a mapping (like a dictionary), returns the value at the index-th key.

    Some return a dictionary, in these cases, we look for the "results" key

    Args:
        obj (Union[Sequence, Mapping]): The object to retrieve the value from.
        index (int): The index of the value to retrieve.

    Returns:
        Any: The value at the given index.

    Raises:
        IndexError: If the index is out of bounds for the object and the object is not a mapping.
    """
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def find_path(name: str, path: str = None) -> str:
    """
    Recursively looks at parent folders starting from the given path until it finds the given name.
    Returns the path as a Path object if found, or None otherwise.
    """
    # If no path is given, use the current working directory
    if path is None:
        path = os.getcwd()

    # Check if the current directory contains the name
    if name in os.listdir(path):
        path_name = os.path.join(path, name)
        print(f"{name} found: {path_name}")
        return path_name

    # Get the parent directory
    parent_directory = os.path.dirname(path)

    # If the parent directory is the same as the current directory, we've reached the root and stop the search
    if parent_directory == path:
        return None

    # Recursively call the function with the parent directory
    return find_path(name, parent_directory)


def add_comfyui_directory_to_sys_path() -> None:
    """
    Add 'ComfyUI' to the sys.path
    """
    comfyui_path = find_path("ComfyUI")
    if comfyui_path is not None and os.path.isdir(comfyui_path):
        sys.path.append(comfyui_path)
        print(f"'{comfyui_path}' added to sys.path")


def add_extra_model_paths() -> None:
    """
    Parse the optional extra_model_paths.yaml file and add the parsed paths to the sys.path.
    """
    try:
        from main import load_extra_path_config
    except ImportError:
        print(
            "Could not import load_extra_path_config from main.py. Looking in utils.extra_config instead."
        )
        from utils.extra_config import load_extra_path_config

    extra_model_paths = find_path("extra_model_paths.yaml")

    if extra_model_paths is not None:
        load_extra_path_config(extra_model_paths)
    else:
        print("Could not find the extra_model_paths config file.")


add_comfyui_directory_to_sys_path()
add_extra_model_paths()


def import_custom_nodes() -> None:
    """Find all custom nodes in the custom_nodes folder and add those node objects to NODE_CLASS_MAPPINGS

    This function sets up a new asyncio event loop, initializes the PromptServer,
    creates a PromptQueue, and initializes the custom nodes.
    """
    import asyncio
    import execution
    from nodes import init_extra_nodes

    sys.path.insert(0, find_path("ComfyUI"))
    import server

    # Creating a new event loop and setting it as the default loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Creating an instance of PromptServer with the loop
    server_instance = server.PromptServer(loop)
    execution.PromptQueue(server_instance)

    # Initializing custom nodes
    asyncio.run(init_extra_nodes())


from nodes import NODE_CLASS_MAPPINGS


def main():
    import_custom_nodes()
    with torch.inference_mode():
        mmaudiomodelloader = NODE_CLASS_MAPPINGS["MMAudioModelLoader"]()
        mmaudiomodelloader_85 = mmaudiomodelloader.loadmodel(
            mmaudio_model="mmaudio_large_44k_v2_fp16.safetensors", base_precision="fp16"
        )

        mmaudiofeatureutilsloader = NODE_CLASS_MAPPINGS["MMAudioFeatureUtilsLoader"]()
        mmaudiofeatureutilsloader_102 = mmaudiofeatureutilsloader.loadmodel(
            vae_model="mmaudio_vae_44k_fp16.safetensors",
            synchformer_model="mmaudio_synchformer_fp16.safetensors",
            clip_model="apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors",
            mode="44k",
            precision="fp16",
        )

        vhs_loadvideoffmpegpath = NODE_CLASS_MAPPINGS["VHS_LoadVideoFFmpegPath"]()
        vhs_loadvideoffmpegpath_109 = vhs_loadvideoffmpegpath.load_video(
            video="ComfyUI/input/",
            force_rate=25,
            custom_width=0,
            custom_height=0,
            frame_load_cap=0,
            start_time=0,
            format="None",
            unique_id=13555644699082977465,
        )

        vhs_loadvideoffmpeg = NODE_CLASS_MAPPINGS["VHS_LoadVideoFFmpeg"]()
        vhs_loadvideoffmpeg_110 = vhs_loadvideoffmpeg.load_video(
            video="hunyuan_spring.mp4",
            force_rate=25,
            custom_width=0,
            custom_height=0,
            frame_load_cap=0,
            start_time=0,
            format="None",
            unique_id=10252929831676075958,
        )

        vhs_videoinfo = NODE_CLASS_MAPPINGS["VHS_VideoInfo"]()
        mmaudiosampler = NODE_CLASS_MAPPINGS["MMAudioSampler"]()
        saveaudio = NODE_CLASS_MAPPINGS["SaveAudio"]()

        for q in range(1):
            vhs_videoinfo_105 = vhs_videoinfo.get_video_info(
                video_info=get_value_at_index(vhs_loadvideoffmpeg_110, 3)
            )

            mmaudiosampler_92 = mmaudiosampler.sample(
                duration=get_value_at_index(vhs_videoinfo_105, 7),
                steps=25,
                cfg=4.5,
                seed=random.randint(1, 2**64),
                prompt="",
                negative_prompt="music, voices",
                mask_away_clip=False,
                force_offload=True,
                mmaudio_model=get_value_at_index(mmaudiomodelloader_85, 0),
                feature_utils=get_value_at_index(mmaudiofeatureutilsloader_102, 0),
                images=get_value_at_index(vhs_loadvideoffmpeg_110, 0),
            )

            saveaudio_107 = saveaudio.save_flac(
                filename_prefix="audio/mmaudio",
                audio=get_value_at_index(mmaudiosampler_92, 0),
            )


if __name__ == "__main__":
    main()
