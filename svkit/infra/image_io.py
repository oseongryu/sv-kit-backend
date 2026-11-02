"""이미지 인코딩/디코딩 공용 유틸 — 도메인 무관 부분만.

피사체를 아는 보정(가정한 방향으로 회전·재검출 후 회전)은 그 도메인이 갖는다.
"""

import base64
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from svkit.infra.errors import ImageDecodeError


def decode_image(data: str) -> np.ndarray:
    """base64/데이터URI → OpenCV BGR (EXIF 회전 보정).

    입력이 깨졌으면 ImageDecodeError — 서버 오류(500)와 구분하기 위해서다.
    """
    if ',' in data:
        data = data.split(',', 1)[1]
    try:
        img_bytes = base64.b64decode(data, validate=False)
        img_pil = Image.open(io.BytesIO(img_bytes))
        img_pil = ImageOps.exif_transpose(img_pil)
        img_pil = img_pil.convert('RGB')
    except Exception as e:
        raise ImageDecodeError('이미지를 해석할 수 없습니다') from e
    img_np = np.array(img_pil)
    return cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)


def encode_image(img_bgr: np.ndarray, quality: int = 85) -> str:
    """OpenCV BGR → base64 JPEG 문자열"""
    _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode('utf-8')


def data_uri_jpeg(img_bgr: np.ndarray, quality: int = 85) -> str:
    """OpenCV BGR → data:image/jpeg;base64,... 형식"""
    return 'data:image/jpeg;base64,' + encode_image(img_bgr, quality)
