"""인프라 계층 예외 — 무거운 의존(PIL·cv2) 없이 import 되는 자리.

이미지 디코딩처럼 실패를 웹 계층이 상태코드로 바꿔야 하는데, 그 예외를 위해
이미지 라이브러리를 함께 끌고 들어오면 그것을 안 싣는 배포가 깨진다.
"""


class ImageDecodeError(ValueError):
    """입력 이미지가 base64/이미지가 아니다 — 호출자 잘못이라 400 으로 매핑된다."""


__all__ = ["ImageDecodeError"]
