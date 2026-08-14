# -*- coding: utf-8 -*-
"""中/英文文本叠加工具（基于 Pillow，支持中文）。

OpenCV 的 cv2.putText 不支持中文（多字节 UTF-8 会乱码），本模块用 Pillow +
系统字体（微软雅黑）渲染文字，转回 BGR ndarray 后叠加到 OpenCV 画布。
"""
from __future__ import annotations

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf", # 黑体
    "/System/Library/Fonts/PingFang.ttc",  # mac
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # linux
]


def _get_font(size_px: int) -> ImageFont.FreeTypeFont:
    """按尺寸获取可用中文字体。"""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def text_overlay(canvas_bgr: np.ndarray, text: str,
                 pos_xy: tuple = (10, 10), size_px: int = 36,
                 color=(255, 255, 255), bg_color=None, bg_pad=(6, 3),
                 anchor="left-top"):
    """把文字叠加到 BGR 画布（支持中文）。

    canvas_bgr: (H, W, 3) uint8 BGR 画布（原地修改）。
    pos_xy: 参考锚点 (x, y)（左上角像素坐标）。
    color: 文字 BGR 颜色。
    bg_color: 若给定，在文字后画半透明底色条。
    bg_pad: 底色相对文字包围盒的内边距 (pad_x, pad_y)。
    anchor: 定位方式：
      "left-top"    pos_xy 是文字左上角
      "right-bottom" pos_xy 是文字右下角（用于角标）
    """
    h, w = canvas_bgr.shape[:2]
    font = _get_font(size_px)
    # 临时用 RGB 渲染以便测量
    tmp = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    # 先测量文字包围盒
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    if anchor == "right-bottom":
        tx = pos_xy[0] - tw
        ty = pos_xy[1] - th
    elif anchor == "left-bottom":
        tx = pos_xy[0]
        ty = pos_xy[1] - th
    else:
        tx, ty = pos_xy

    # 底色
    if bg_color is not None:
        pad_x, pad_y = bg_pad
        x0 = max(0, tx - pad_x)
        y0 = max(0, ty - pad_y)
        x1 = min(w, tx + tw + pad_x)
        y1 = min(h, ty + th + pad_y)
        sub = canvas_bgr[y0:y1, x0:x1]
        overlay = np.full_like(sub, bg_color)
        canvas_bgr[y0:y1, x0:x1] = cv2.addWeighted(overlay, 0.55, sub, 0.45, 0)

    # 渲染文字（PIL 用 RGB，canvas 是 BGR）
    pil_img = Image.fromarray(cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    draw.text((tx, ty), text, font=font, fill=(color[2], color[1], color[0]))
    canvas_bgr[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return canvas_bgr
