<div align="center">

<img title="" src="doc/images/miku_splash.png" alt="메인 화면" width="400">

[![기반](https://img.shields.io/badge/%EA%B8%B0%EB%B0%98-manga--translator--ui-green)](https://github.com/hgmzhn/manga-translator-ui)
[![모델](https://img.shields.io/badge/%EB%AA%A8%EB%8D%B8-Real--CUGAN-orange)](https://github.com/bilibili/ailab)
[![모델](https://img.shields.io/badge/%EB%AA%A8%EB%8D%B8-MangaJaNai-orange)](https://github.com/the-database/MangaJaNai)
[![모델](https://img.shields.io/badge/%EB%AA%A8%EB%8D%B8-YSG-orange)](https://github.com/lhj5426/YSG)
[![모델](https://img.shields.io/badge/Model-MangaLens%20Bubble%20Segmentation-orange?logo=huggingface)](https://huggingface.co/huyvux3005/manga109-segmentation-bubble)
[![OCR](https://img.shields.io/badge/OCR-HayaiOCR-blue)](https://github.com/NopeNopeGuy/hayai-ocr)
[![OCR](https://img.shields.io/badge/OCR-PaddleOCR-blue)](https://github.com/PaddlePaddle/PaddleOCR)
[![OCR](https://img.shields.io/badge/OCR-MangaOCR-blue)](https://github.com/kha-white/manga-ocr)
[![OCR](https://img.shields.io/badge/OCR-PaddleOCR--VL--1.5-blue)](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5)
[![라이선스](https://img.shields.io/badge/%EB%9D%BC%EC%9D%B4%EC%84%A0%EC%8A%A4-GPL--3.0-red)](LICENSE.txt)

</div>


속도와, 편의성, 접근성을 모두 극대화하고자 조정된 만화 번역기입니다. 가장 큰 장벽인 API 없이도 번역을 진행할 수 있는 TXT 모드가 마련되어 있고, 한글 배치에 최적화된 알고리즘을 제공하며, 클릭 몇 번으로 출판급 퀄리티에 가까운 결과물을 낼 수 있도록 UI가 마련되어 있습니다. 또한 여러 가지 편의기능이 마련되어 있습니다. <div align="center">

 <H3>StoneCandy</H3>

<img title="" src="doc/images/PPL100.png" height=35> 
<br><br>
소스코드가 아직 정리되지 않았습니다. 반드시 Release 버전을 이용해 주세요

**[StoneCandy-Translator 0.8 Release](https://github.com/Stone-Candy/StoneCandy-Translator/releases)**
<br>
<br>

</div>

---

## 🖼️ Showcase

<img title="" src="doc/images/tr_01.png"> 
<img title="" src="doc/images/tr_02.png"> 
<div align="center">
<strong>▲ 위의 그림은 TXT모드 사용 예시이며, 번역 API 사용시 편집 전까지 모든 과정이 자동으로 진행됩니다.</strong>
</div>
<br>
<img title="" src="doc/images/tr_03.png"> 

<br><br>

## 📝 번역기 사용팁
1. 메인에서 상단 제목을 눌러 작업 모드를 고르고, 파일이나 폴더를 드래그 앤 드랍하고, 시작 버튼을 누르면 진행됩니다.
2. 압축 파일도 지원되지만, 여러 파일을 지속적으로 작업할 때는 폴더 상태로 불러오는 것을 권장합니다.
3. 처음 시작 시에는 모델을 자동으로 다운로드하므로, 진행 속도가 느릴 수 있습니다.
4. 편집 화면에서 z키를 누르면, 빠르게 원본과 비교하며 작업할 수 있습니다.
5. 클리닝(대패질) 작업은 인페인트로 이루어지기 때문에, 대체로 퀄리티가 괜찮지만, 인페인트는 기본적으로 주변의 색상과 무늬를 닮으려는 경향이 있어서, 가끔 말풍선 내부로 원치 않는 색상이나 무늬가 침범해 들어올 때가 있습니다. 그럴 때는 덧칠 브러시 상태로, ctrl + 클릭하게 되면, 단색의 덧칠 레이어로 전환되어 깔끔하게 정리할 수 있습니다. <div align="center"><img title="" src="doc/images/tip_01.png"> </div>
6. 글꼴과 스타일은 ctrl + [숫자키] 로 저장되며, 같은 숫자키를 누르면 글자 레이어에 저장된 스타일을 적용시킬 수 있습니다. 앱을 껐다 켜게 되면 단축키 설정이 사라지지만, 스타일을 저장할 때 앞에 숫자를 붙이면 앱을 열 때 해당 숫자에 자동으로 단축키가 할당됩니다.
7. 배포 가능한 폰트를 몇 개를 포함하였습니다. 설정 - 조판 에서 시스템 폰트 사용 여부를 결정할 수 있습니다.




<br><br>
## ⚖️ 라이선스

이 프로젝트는 GPL-3.0 라이선스로 오픈소스입니다.


### 모델 라이선스 안내

이 프로젝트의 소스 코드는 **GPL-3.0** 라이선스를 사용합니다.

이 프로젝트는 이미지 초해상도에 MangaJaNai / IllustrationJaNai 모델 가중치를 사용할 수 있습니다. 해당 모델 가중치는 **CC BY-NC 4.0**(저작자표시-비영리 4.0 국제) 라이선스이며, 비상업적 용도로만 사용할 수 있습니다.

- **모델 출처**: [MangaJaNai](https://github.com/the-database/MangaJaNai)
- **모델 라이선스**: CC BY-NC 4.0
- **사용 제한**: 비상업적 용도만 허용

<br><br>
## ⚠️ 특별 고지

이 프로젝트는 기술 시연, 개인 학습, 교류 목적으로만 제공되며 법률, 상업, 컴플라이언스 자문을 구성하지 않습니다.

이 프로젝트와 관련 기능을 설치, 구성, 호출, 배포할 때는 현지 법령, 플랫폼 규칙, 콘텐츠 출처 라이선스, 제3자 서비스 약관을 직접 확인하고 지속적으로 준수해야 합니다.

### 면책 및 책임 제한

- 이 프로젝트 사용으로 발생하는 모든 행위와 결과(콘텐츠 처리, 게시, 전파, 재배포, 상업적 이용을 포함하되 이에 한정되지 않음)는 사용자가 단독으로 책임집니다.
- 입력 콘텐츠, 출력 콘텐츠, 데이터 출처가 적법하게 허가되었는지 직접 확인해야 하며, 저작권, 상표권, 프라이버시, 초상권 등 정당한 권익을 침해하는 용도로 사용해서는 안 됩니다.
- 이 프로젝트를 불법·규정 위반 용도로 사용해서는 안 됩니다. 여기에는 불법 복제 배포, 무단 대량 수집·전재, 플랫폼 제한 우회, 사기, 명예훼손, 타인의 정당한 권익 침해 등이 포함됩니다.
- 이 프로젝트는 OCR, 번역, 초해상도 관련 서비스를 포함한 제3자 모델, API, 데이터, 라이브러리에 의존합니다. 가용성, 정확성, 안정성, 요금, 리스크 관리, 컴플라이언스 요구 사항은 해당 제공자가 책임지며, 관련 위험과 비용은 사용자가 부담합니다.
- 적용 법령이 허용하는 최대 범위에서, 프로젝트 제작자와 기여자는 이 프로젝트의 사용 또는 사용 불능으로 인한 직접·간접 손실(데이터 손실, 업무 중단, 수익 손실, 계정 위험, 제3자 청구를 포함하되 이에 한정되지 않음)에 대해 책임지지 않습니다.
- 팀이나 조직 환경에서 이 프로젝트를 사용할 경우, 권한 관리, 로그 감사, 콘텐츠 심사, 컴플라이언스 평가를 직접 수행하고 필요한 사람 검토 절차를 마련해야 합니다.

사용 전에 위험을 신중히 평가하세요. 계속 사용하는 것은 위 고지를 읽고 이해했으며 이에 동의하는 것으로 간주됩니다.

<br><br>
<div align="center">
 
## StoneCandy

<img title="" src="doc/images/PPL100.png" height=35> 
</div>
