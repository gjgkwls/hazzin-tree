# hazzin-tree 🎄

파이썬 표준 라이브러리만으로 렌더링하는, 회전하는 ASCII 크리스마스 트리.
글자 11,650개가 모여 트리가 되고 — 전구, 오너먼트, 금색 가랜드, 하늘에서 떨어지는 선물,
루돌프 썰매를 탄 산타, 눈, 필기체 인사말까지 전부 문자로 그려진다.

**Live: https://hazzin-tree.vercel.app**

## 실행

```bash
python3 tree.py            # 로컬 서버 → http://localhost:8000 (시작 시 프레임 생성 ~30초)
python3 tree.py --dump 230 # 특정 프레임을 터미널에서 미리보기
python3 tree.py --build    # 배포용 정적 파일 생성 → hazzin-tree/index.html
```

의존성 없음. 240프레임(16초 루프)을 서버 시작 시 전부 미리 계산한다 —
3D 포인트 클라우드 회전, 원근 투영, z-버퍼, 성장 애니메이션 모두 파이썬.

## 배포

```bash
python3 tree.py --build
cd hazzin-tree && npx vercel@58.9.0 deploy --prod --yes --archive=tgz
```

## 크레딧

- BGM: "Jingle Bells" — Kevin MacLeod ([incompetech.com](https://incompetech.com)), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- 필기체 레터링: FIGlet Cursive 폰트
