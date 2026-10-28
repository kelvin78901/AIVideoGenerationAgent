# DramaStudio nodes for ComfyUI

AI Drama Studio's input and output nodes. A workflow built with them runs in the studio without
bindings: the studio fills each input node by its class and reads the output nodes by theirs.
Every input has a default, so the workflow also runs by hand in ComfyUI.

The studio's setup page installs this folder into `ComfyUI/custom_nodes/comfyui-dramastudio`
(after a ComfyUI-Manager snapshot). Restart ComfyUI to load it. Checked on ComfyUI 0.41.2.

| Node | Studio slot | Input the studio fills | Outputs |
| --- | --- | --- | --- |
| DramaStudio ▸ First frame | `first_frame` | `image` | IMAGE |
| DramaStudio ▸ Reference picture | `ref_image` (by `index`) | `image` | IMAGE |
| DramaStudio ▸ Video in | `video_in` | `video` | VIDEO |
| DramaStudio ▸ Dialogue audio | `dialogue_audio` | `audio` | AUDIO |
| DramaStudio ▸ Voice sample | `ref_audio` (by `index`) | `audio` | AUDIO |
| DramaStudio ▸ Prompt | `prompt` | `text` | STRING |
| DramaStudio ▸ Negative prompt | `negative` | `text` | STRING |
| DramaStudio ▸ Size | `width`, `height` | `width`, `height` | INT, INT |
| DramaStudio ▸ Frame rate and length | `fps`, `seconds` | `fps`, `seconds` | fps (FLOAT), fps_int, seconds, frames |
| DramaStudio ▸ Seed | `seed` | `seed` | INT |
| DramaStudio ▸ Video out | `video_out` | — | saves MP4 |
| DramaStudio ▸ Image out | `image_out` | — | saves PNG |
| DramaStudio ▸ Audio out | `audio_out` | — | saves FLAC |

File inputs list the files under ComfyUI's `input` folder (the studio uploads into
`input/dramastudio/`); outputs save into `output/dramastudio/`.

Reference pictures and voice samples are optional in the studio: a shot with fewer files than the
workflow has nodes leaves the extra nodes out, together with the inputs that read them, so wire
them into inputs that are optional on their nodes.

`frames` is `fps × seconds`, rounded. A model that wants a frame count like 4n + 1 needs its own
math node after it.

The studio's table of these nodes is `src/drama_series_agent/wflib/dramastudio.py`; the tests in
`tests/unit/test_dramastudio_nodes.py` keep the two in step.
