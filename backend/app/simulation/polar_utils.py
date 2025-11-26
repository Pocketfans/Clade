"""球面坐标与像素网格之间的折返工具函数。"""

from __future__ import annotations

import numpy as np

_TWO_PI = 2.0 * np.pi


def wrap_polar_coordinates(
    x: np.ndarray,
    y: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    将像素坐标映射到球面并执行极点折返，再投影回像素平面。

    Args:
        x: 水平像素坐标，可以是标量或数组。
        y: 垂直像素坐标，可以是标量或数组。
        width: 像素网格宽度（对应 360° 经度）。
        height: 像素网格高度（对应 180° 纬度）。

    Returns:
        (x_new, y_new): 折返后的像素坐标，范围分别为
        [0, width) 与 [0, height)。
    """

    width_f = float(width)
    height_f = float(height)

    lon = (np.asarray(x, dtype=np.float64) / width_f) * _TWO_PI - np.pi
    lat = (np.asarray(y, dtype=np.float64) / height_f) * np.pi - 0.5 * np.pi

    over_north = lat > 0.5 * np.pi
    over_south = lat < -0.5 * np.pi

    if np.any(over_north):
        lat = np.where(over_north, np.pi - lat, lat)
        lon = np.where(over_north, lon + np.pi, lon)

    if np.any(over_south):
        lat = np.where(over_south, -np.pi - lat, lat)
        lon = np.where(over_south, lon + np.pi, lon)

    lon = (lon + np.pi) % _TWO_PI - np.pi

    x_new = (lon + np.pi) / _TWO_PI * width_f
    y_new = (lat + 0.5 * np.pi) / np.pi * height_f
    y_new = np.clip(y_new, 0.0, height_f - 1.0001)

    return x_new.astype(np.float32, copy=False), y_new.astype(np.float32, copy=False)


__all__ = ["wrap_polar_coordinates"]

