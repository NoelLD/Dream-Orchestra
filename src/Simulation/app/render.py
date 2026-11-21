"""The cheap renderer used at run time and for policy datasets, so training and execution see the same images.

320x240 render cropped to 320x180 (the station's 640x480 -> 640x360 crop at half size). Dream-1 is sent 320x176
anyway. Shadows/reflections cost ~3x under software rendering (642 vs 207 ms for three views on 2 CPUs).
"""

import mujoco

RENDER_W, RENDER_H = 320, 240
RENDER_CROP = slice(30, 210)
CAMERAS = ("top", "left", "right")


class SmallRenderer:
    def __init__(self, model, shadows: bool = False):
        self.renderer = mujoco.Renderer(model, height=RENDER_H, width=RENDER_W)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = shadows
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = shadows

    def views(self, data) -> dict:
        """By camera name (`top`, `left`, `right`), a 180x320x3 uint8 RGB image."""
        images = {}
        for name in CAMERAS:
            self.renderer.update_scene(data, camera=name)
            images[name] = self.renderer.render()[RENDER_CROP].copy()
        return images

    def close(self) -> None:
        self.renderer.close()
