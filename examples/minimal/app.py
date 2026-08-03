"""svkit 단독 실행 예제 — 프론트 없이 백엔드만 기동한다.

실행:
    pip install -r requirements.txt
    python app.py
확인:
    curl http://localhost:5000/api/health
    curl http://localhost:5000/api/hello/items
"""
from svkit import create_app

app = create_app(__file__)

if __name__ == "__main__":
    from svkit import run
    run(app)
