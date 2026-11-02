// 배경 한 장을 중앙 기준으로 자른다. PC 양옆과 모바일 중앙의 배율은 공유한다.
// 1152×384 원본의 정수배만 사용하고, 짧은 화면은 1배부터 시작한다.
function fitTitleWorld() {
  const root = document.documentElement;
  const baseScale = root.clientHeight <= 560 ? 1 : 2;
  const scale = Math.max(baseScale, Math.ceil(root.clientWidth / 1152));
  root.style.setProperty('--scene-width', `${1152 * scale}px`);
  root.style.setProperty('--scene-height', `${384 * scale}px`);

  // 맵은中央 216×324 원본과 바깥 1152×324 확장 파노라마가 똑같은 정수배(2배: 432×648 / 2304×648)를 공유해
  // 도로·연석·잔디가 경계에서 1픽셀도 어긋나지 않고 이어진다.
  const mapScale = root.clientWidth < 380 ? 1 : 2;
  root.style.setProperty('--map-scale', String(mapScale));
}

fitTitleWorld();
window.addEventListener('resize', fitTitleWorld);

const INTRO_SEEN_KEY = 'guessty_intro_seen';
const PROGRESS_KEY = 'guessty_progress';

const screens = {
  title: document.getElementById('screen-title'),
  intro: document.getElementById('screen-intro'),
  map: document.getElementById('screen-map'),
  interview: document.getElementById('screen-interview'),
  result: document.getElementById('screen-result'),
};

const mapScroll = document.getElementById('map-scroll');
const mapStreet = document.getElementById('map-street');
const mapError = document.getElementById('map-error');
const mapModal = document.getElementById('map-modal');
const mapModalBar = document.getElementById('map-modal-bar');
const mapModalTitle = document.getElementById('map-modal-title');
const mapModalDesc = document.getElementById('map-modal-desc');
const mapModalModeRow = document.getElementById('map-modal-mode-row');
const mapModeGuideBtn = document.getElementById('map-mode-guide');
const mapModePracticeBtn = document.getElementById('map-mode-practice');
const mapModalActions = document.getElementById('map-modal-actions');
const mapModalRound1 = document.getElementById('map-modal-round1');
const mapModalRound2 = document.getElementById('map-modal-round2');
const mapModalClose = document.getElementById('map-modal-close');
const mapStagePill = document.getElementById('map-stage-pill');
const mapGaugeFill = document.getElementById('map-gauge-fill');
const mapStampPill = document.getElementById('map-stamp-pill');
const mapHelpBtn = document.getElementById('map-help-btn');

// 면접 화면 요소
const interviewWinTitle = document.getElementById('interview-win-title');
const interviewExitBtn = document.getElementById('interview-exit-btn');
const interviewStageLabel = document.getElementById('interview-stage-label');
const interviewStepDot1 = document.getElementById('interview-step-dot-1');
const interviewStepDot2 = document.getElementById('interview-step-dot-2');
const interviewStepDot3 = document.getElementById('interview-step-dot-3');
const slotGwajang = document.getElementById('slot-gwajang');
const slotBujang = document.getElementById('slot-bujang');
const imgGwajang = document.getElementById('img-gwajang');
const imgBujang = document.getElementById('img-bujang');
const interviewQuestionText = document.getElementById('interview-question-text');
const interviewChoices = document.getElementById('interview-choices');
const interviewPracticeBox = document.getElementById('interview-practice-box');
const practiceHint = document.getElementById('practice-hint');
const practiceInput = document.getElementById('practice-input');
const practiceUnit = document.getElementById('practice-unit');
const practiceError = document.getElementById('practice-error');
const practiceSubmitBtn = document.getElementById('practice-submit-btn');
const interviewDialogueArea = document.getElementById('interview-dialogue-area');
const imgHeroFace = document.getElementById('img-hero-face');
const dialogueSpeakerTab = document.getElementById('dialogue-speaker-tab');
const dialogueText = document.getElementById('dialogue-text');
const dialogueNextArrow = document.getElementById('dialogue-next-arrow');

// 결과 화면 요소
const resultWinBar = document.getElementById('result-win-bar');
const resultBadge = document.getElementById('result-badge');
const resultVerdictTitle = document.getElementById('result-verdict-title');
const resultClosingLine = document.getElementById('result-closing-line');
const resultStampSeal = document.getElementById('result-stamp-seal');
const resultUserVal = document.getElementById('result-user-val');
const resultActualVal = document.getElementById('result-actual-val');
const resultSourceText = document.getElementById('result-source-text');
const resultSummaryReview = document.getElementById('result-summary-review');
const resultReviewList = document.getElementById('result-review-list');
const resultPrimaryBtn = document.getElementById('result-primary-btn');
const resultPrimaryLabel = document.getElementById('result-primary-label');
const resultMapBtn = document.getElementById('result-map-btn');

let companiesData = null;
let selectedCompany = null;
let selectedMode = 'guide';
let currentHeroSlot = 0; // 0: 취업센터, 1: 쟤당치킨, 2: 대충통운, 3: 촤지피티
let heroWalkTimer = null;
let isHeroWalking = false;

// 216×324 원본 맵의 S자 도로를 따라 이어지는 경유지 좌표
const MAP_STOP_COORDS = {
  0: { x: 64, y: 296 },  // 취업센터 앞 도로
  1: { x: 74, y: 214 },  // 1번 회사(쟤당치킨) 앞 도로
  2: { x: 126, y: 136 }, // 2번 회사(대충통운) 앞 도로
  3: { x: 100, y: 58 },  // 3번 회사(촤지피티) 앞 도로
};

// 구간별 S자 도로 중간 코너 경유지 (작은 값 -> 큰 값 순서)
const MAP_SEGMENT_WAYPOINTS = {
  '0-1': [
    { x: 74, y: 256 },
    { x: 74, y: 214 },
  ],
  '1-2': [
    { x: 76, y: 172 },
    { x: 112, y: 158 },
    { x: 126, y: 136 },
  ],
  '2-3': [
    { x: 134, y: 108 },
    { x: 90, y: 80 },
    { x: 100, y: 58 },
  ],
};

function hasSeenIntro() {
  try {
    return window.localStorage.getItem(INTRO_SEEN_KEY) === '1';
  } catch {
    return false;
  }
}

function markIntroSeen() {
  try {
    window.localStorage.setItem(INTRO_SEEN_KEY, '1');
  } catch {
    // 저장소 접근이 제한된 환경에서는 무시하고 진행한다.
  }
}

function loadProgress() {
  try {
    const raw = window.localStorage.getItem(PROGRESS_KEY);
    if (!raw) return { cleared: {}, round1Cleared: {} };
    const parsed = JSON.parse(raw);
    return {
      cleared: parsed?.cleared || {},
      round1Cleared: parsed?.round1Cleared || {},
    };
  } catch {
    return { cleared: {}, round1Cleared: {} };
  }
}

function saveProgress(progress) {
  try {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  } catch {
    // 저장소 접근이 제한된 환경에서는 무시하고 진행한다.
  }
}

function getCompanyState(company, sortedAsc, progress) {
  if (progress.cleared[company.id]) {
    return 'cleared';
  }
  // 아직 클리어하지 않은 가장 낮은 order 회사가 현재 진행 중 회사다.
  const currentCompany = sortedAsc.find((item) => !progress.cleared[item.id]) || sortedAsc[0];
  if (currentCompany && currentCompany.id === company.id) {
    return 'current';
  }
  return 'locked';
}

function updateStampHud(sortedAsc, progress) {
  const clearedCount = sortedAsc.filter((c) => progress.cleared[c.id]).length;
  const currentCompany = sortedAsc.find((item) => !progress.cleared[item.id]) || sortedAsc[sortedAsc.length - 1];
  const stageNum = currentCompany ? String(currentCompany.order).padStart(2, '0') : '03';

  if (mapStagePill) mapStagePill.textContent = `STAGE ${stageNum}`;
  if (mapStampPill) mapStampPill.textContent = `STAMP ${clearedCount}/${sortedAsc.length}`;
  if (mapGaugeFill) {
    const pct = Math.max(12, Math.round((clearedCount / sortedAsc.length) * 100));
    mapGaugeFill.style.width = `${pct}%`;
  }
}

function renderMapStreet(companies) {
  if (!mapStreet) return;
  mapStreet.innerHTML = '';

  const canvas = document.createElement('div');
  canvas.className = 'map-canvas';

  const bgImg = document.createElement('img');
  bgImg.className = 'map-bg-image';
  bgImg.src = './assets/map-bg.png?v=4';
  bgImg.width = 216;
  bgImg.height = 324;
  bgImg.alt = '';
  canvas.appendChild(bgImg);

  const progress = loadProgress();
  const sortedAsc = [...companies].sort((a, b) => a.order - b.order);
  const sortedDesc = [...sortedAsc].reverse();

  updateStampHud(sortedAsc, progress);

  sortedDesc.forEach((company) => {
    const state = getCompanyState(company, sortedAsc, progress);

    const node = document.createElement('div');
    node.className = `map-node is-${state}`;
    node.dataset.companyId = company.id;
    node.dataset.slot = String(company.order);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'map-building-btn';
    btn.dataset.companyId = company.id;
    btn.setAttribute('aria-label', company.name);

    const plate = document.createElement('div');
    plate.className = 'map-nameplate';

    const nameSpan = document.createElement('span');
    nameSpan.textContent = company.name;

    const statusTag = document.createElement('span');
    statusTag.className = `map-status-tag is-${state}`;
    if (state === 'cleared') {
      statusTag.textContent = '완료';
    } else if (state === 'current') {
      statusTag.textContent = progress.round1Cleared[company.id] ? '2차' : '지원';
    } else {
      statusTag.textContent = '잠김';
    }

    plate.append(nameSpan, statusTag);
    btn.appendChild(plate);
    node.appendChild(btn);
    canvas.appendChild(node);
  });

  // 맨 아래 길 옆 취업센터 핫스팟
  const careerNode = document.createElement('div');
  careerNode.className = 'map-node is-career';
  careerNode.dataset.slot = '0';

  const careerBtn = document.createElement('button');
  careerBtn.type = 'button';
  careerBtn.className = 'map-building-btn';
  careerBtn.dataset.action = 'career-center';
  careerBtn.setAttribute('aria-label', '취업센터 안내');

  const careerPlate = document.createElement('div');
  careerPlate.className = 'map-nameplate';
  careerPlate.innerHTML = `
    <span>취업센터</span>
  `;

  careerBtn.appendChild(careerPlate);
  careerNode.appendChild(careerBtn);
  canvas.appendChild(careerNode);

  // 아직 아무 면접도 통과하지 않은 첫 방문 상태면 취업센터(0번) 앞, 아니면 현재 진행 중 회사 앞에 배치
  const hasAnyProgress =
    Object.keys(progress.cleared).length > 0 ||
    Object.keys(progress.round1Cleared).length > 0;
  const currentCompany = sortedAsc.find((item) => !progress.cleared[item.id]);
  currentHeroSlot = hasAnyProgress && currentCompany ? currentCompany.order : 0;
  const startCoord = MAP_STOP_COORDS[currentHeroSlot] || MAP_STOP_COORDS[0];

  const hero = document.createElement('div');
  hero.id = 'map-hero';
  hero.className = 'map-hero';
  hero.setAttribute('aria-hidden', 'true');
  hero.style.setProperty('--hero-x', `${startCoord.x}px`);
  hero.style.setProperty('--hero-y', `${startCoord.y}px`);
  hero.innerHTML = `
    <span class="title-hero-shadow"></span>
    <img id="map-hero-img" src="./assets/hero-back.png" width="32" height="64" alt="">
  `;
  canvas.appendChild(hero);

  mapStreet.appendChild(canvas);

  // 처음 열면 진행 중 회사(없으면 취업센터)가 보이게 스크롤한다.
  window.requestAnimationFrame(() => {
    const target =
      canvas.querySelector('.map-node.is-current') ||
      canvas.querySelector('.map-node.is-career');
    if (target) {
      target.scrollIntoView({ block: 'center', behavior: 'instant' });
    }
  });
}

function buildRoadPath(fromSlot, toSlot) {
  if (fromSlot === toSlot) return [];
  const points = [];
  const dir = toSlot > fromSlot ? 1 : -1;
  let cur = fromSlot;
  while (cur !== toSlot) {
    const next = cur + dir;
    const key = dir > 0 ? `${cur}-${next}` : `${next}-${cur}`;
    const seg = MAP_SEGMENT_WAYPOINTS[key] || [];
    if (dir > 0) {
      points.push(...seg);
    } else {
      const reversed = [...seg].slice(0, -1).reverse();
      reversed.push(MAP_STOP_COORDS[next]);
      points.push(...reversed);
    }
    cur = next;
  }
  return points;
}

function walkHeroToSlot(targetSlot, onArrive) {
  const hero = document.getElementById('map-hero');
  const heroImg = document.getElementById('map-hero-img');
  if (!hero) {
    onArrive?.();
    return;
  }

  if (heroWalkTimer) {
    window.clearTimeout(heroWalkTimer);
    heroWalkTimer = null;
  }

  const waypoints = buildRoadPath(currentHeroSlot, targetSlot);
  if (waypoints.length === 0) {
    isHeroWalking = false;
    hero.classList.remove('is-walking');
    if (heroImg) heroImg.src = './assets/hero-back.png';
    onArrive?.();
    return;
  }

  const goingDown = targetSlot < currentHeroSlot;
  if (heroImg) {
    heroImg.src = goingDown ? './assets/hero-front.png' : './assets/hero-back.png';
  }

  isHeroWalking = true;
  hero.classList.add('is-walking');
  currentHeroSlot = targetSlot;

  let idx = 0;
  function stepNext() {
    if (idx >= waypoints.length) {
      isHeroWalking = false;
      hero.classList.remove('is-walking');
      if (heroImg) heroImg.src = './assets/hero-back.png';
      onArrive?.();
      return;
    }
    const pt = waypoints[idx];
    hero.style.setProperty('--hero-x', `${pt.x}px`);
    hero.style.setProperty('--hero-y', `${pt.y}px`);
    idx += 1;
    heroWalkTimer = window.setTimeout(stepNext, 260);
  }

  stepNext();
}

async function enterMapScreen() {
  showScreen('map', false);

  if (companiesData) {
    renderMapStreet(companiesData);
    return;
  }

  try {
    const response = await window.fetch('./data/companies.json');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!Array.isArray(data) || data.length === 0) {
      throw new Error('Empty companies data');
    }
    companiesData = data;
    if (mapError) mapError.hidden = true;
    renderMapStreet(companiesData);
  } catch {
    if (mapError) mapError.hidden = false;
  }
}

function updateModalModeUI() {
  if (mapModeGuideBtn) {
    mapModeGuideBtn.classList.toggle('is-active', selectedMode === 'guide');
  }
  if (mapModePracticeBtn) {
    mapModePracticeBtn.classList.toggle('is-active', selectedMode === 'practice');
  }
}

function openCompanyModal(company) {
  if (!mapModal || !companiesData) return;
  selectedCompany = company;

  const progress = loadProgress();
  const sortedAsc = [...companiesData].sort((a, b) => a.order - b.order);
  const state = getCompanyState(company, sortedAsc, progress);

  if (mapModalBar) mapModalBar.textContent = `${company.id.toUpperCase()}.EXE`;
  if (mapModalTitle) mapModalTitle.textContent = company.name;

  if (state === 'locked') {
    if (mapModalDesc) {
      mapModalDesc.textContent = '이전 회사 도장을 먼저 받아야 지원할 수 있어요.';
    }
    if (mapModalModeRow) mapModalModeRow.hidden = true;
    if (mapModalActions) mapModalActions.hidden = true;
  } else {
    const canEnterRound2 = Boolean(
      progress.round1Cleared[company.id] || progress.cleared[company.id]
    );
    selectedMode = 'guide';

    if (mapModalDesc) {
      if (state === 'cleared') {
        mapModalDesc.textContent = '도장을 획득한 회사예요. 원하는 차수를 골라 복습해 보세요!';
      } else if (canEnterRound2) {
        mapModalDesc.textContent = '1차 면접 통과! 2차 면접을 보거나 1차를 다시 연습할 수 있어요.';
      } else {
        mapModalDesc.textContent = `${company.greeting}`;
      }
    }

    if (mapModalModeRow) mapModalModeRow.hidden = false;
    if (mapModalActions) mapModalActions.hidden = false;
    if (mapModalRound1) mapModalRound1.disabled = false;
    if (mapModalRound2) mapModalRound2.disabled = !canEnterRound2;
    updateModalModeUI();
  }

  mapModal.hidden = false;
}

function closeMapModal() {
  if (!mapModal) return;
  mapModal.hidden = true;
  selectedCompany = null;
}

mapModeGuideBtn?.addEventListener('click', () => {
  selectedMode = 'guide';
  updateModalModeUI();
});

mapModePracticeBtn?.addEventListener('click', () => {
  selectedMode = 'practice';
  updateModalModeUI();
});

const introCtaText = document.getElementById('intro-cta-text');

function openIntroScreen(fromCareerCenter = false) {
  introLocked = false;
  if (introCtaText) {
    introCtaText.textContent = fromCareerCenter
      ? '▶ 튜토리얼 진행하기'
      : '▶ 화면을 터치하세요';
  }
  showScreen('intro', false);
  screens.intro?.focus();
}

if (mapStreet) {
  mapStreet.addEventListener('click', (event) => {
    if (isHeroWalking) return;

    const careerBtn = event.target.closest('button[data-action="career-center"]');
    if (careerBtn) {
      walkHeroToSlot(0, () => {
        // 취업센터에 도착하면 튜토리얼 진행하기 CTA로 인트로 설명 화면을 띄운다.
        openIntroScreen(true);
      });
      return;
    }

    const companyBtn = event.target.closest('button[data-company-id]');
    if (!companyBtn || !companiesData) return;

    const company = companiesData.find((item) => item.id === companyBtn.dataset.companyId);
    if (!company) return;
    walkHeroToSlot(company.order, () => {
      openCompanyModal(company);
    });
  });
}

// 맵 화면에서 방향키(↑/↓/←/→ 또는 W/A/S/D)로도 주인공이 도로를 따라 이동하고 Enter/Space로 진입 가능
window.addEventListener('keydown', (event) => {
  if (screens.map?.hidden || !mapModal?.hidden || isHeroWalking) return;

  if (event.key === 'ArrowUp' || event.key === 'w' || event.key === 'W') {
    event.preventDefault();
    const nextSlot = Math.min(3, currentHeroSlot + 1);
    if (nextSlot !== currentHeroSlot) {
      walkHeroToSlot(nextSlot);
    }
  } else if (event.key === 'ArrowDown' || event.key === 's' || event.key === 'S') {
    event.preventDefault();
    const nextSlot = Math.max(0, currentHeroSlot - 1);
    if (nextSlot !== currentHeroSlot) {
      walkHeroToSlot(nextSlot);
    }
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (currentHeroSlot === 0) {
      openIntroScreen(true);
    } else if (companiesData) {
      const company = companiesData.find((item) => item.order === currentHeroSlot);
      if (company) openCompanyModal(company);
    }
  }
});

mapHelpBtn?.addEventListener('click', () => {
  openIntroScreen(true);
});

mapModalClose?.addEventListener('click', closeMapModal);
mapModal?.addEventListener('click', (event) => {
  if (event.target === mapModal) closeMapModal();
});

const problemsCache = {};

async function enterInterviewFromMap(company, round, mode) {
  closeMapModal();

  try {
    let problemDoc = problemsCache[company.id];
    if (!problemDoc) {
      const res = await window.fetch(`./data/problems/${company.id}.json`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      problemDoc = await res.json();
      problemsCache[company.id] = problemDoc;
    }

    const interviewData =
      problemDoc.interviews?.find((item) => item.round === round) ||
      problemDoc.interviews?.[0];
    if (!interviewData) throw new Error('Missing interview round');

    const outfit = company.outfit || 'default';
    if (imgGwajang) {
      imgGwajang.src = `./assets/interviewers/gwajang-${outfit}-neutral.png`;
    }
    if (imgBujang) {
      imgBujang.src = `./assets/interviewers/bujang-${outfit}-neutral.png`;
    }
    if (imgHeroFace) {
      imgHeroFace.src = './assets/hero-face/neutral.png';
    }
    if (interviewWinTitle) {
      interviewWinTitle.textContent = `STAGE ${company.order}`;
    }
    if (interviewStageLabel) {
      interviewStageLabel.textContent = `${round}차 면접 · ${mode === 'practice' ? '실전' : '공식'}`;
    }
    if (interviewQuestionText) {
      interviewQuestionText.textContent = interviewData.question;
    }
    if (dialogueSpeakerTab) {
      dialogueSpeakerTab.textContent = round === 2 ? '부장' : '과장';
      dialogueSpeakerTab.classList.add('is-interviewer');
    }
    if (dialogueText) {
      dialogueText.textContent = company.greeting;
    }
    if (dialogueNextArrow) {
      dialogueNextArrow.hidden = false;
    }
    if (slotGwajang) {
      slotGwajang.classList.toggle('is-speaking', round !== 2);
    }
    if (slotBujang) {
      slotBujang.classList.toggle('is-speaking', round === 2);
    }
    if (interviewChoices) {
      interviewChoices.innerHTML = '';
      interviewChoices.hidden = mode === 'practice';
    }
    if (interviewPracticeBox) {
      interviewPracticeBox.hidden = mode !== 'practice';
    }

    showScreen('interview', true);
  } catch {
    showScreen('map', false);
    if (mapError) mapError.hidden = false;
  }
}

mapModalRound1?.addEventListener('click', () => {
  if (!selectedCompany) return;
  enterInterviewFromMap(selectedCompany, 1, selectedMode);
});

mapModalRound2?.addEventListener('click', () => {
  if (!selectedCompany || mapModalRound2.disabled) return;
  enterInterviewFromMap(selectedCompany, 2, selectedMode);
});

interviewExitBtn?.addEventListener('click', () => {
  enterMapScreen();
});

function showScreen(name, isIndoor = false) {
  Object.entries(screens).forEach(([key, section]) => {
    if (!section) return;
    section.hidden = key !== name;
  });
  document.body.classList.toggle('world-indoor', isIndoor);
  document.body.classList.toggle('world-outdoor', !isIndoor);
  if (isIndoor) {
    document.body.dataset.world = 'indoor';
  } else if (name === 'map') {
    document.body.dataset.world = 'map';
  } else {
    document.body.dataset.world = 'title';
  }
}

// PRESS START → 항상 인트로 화면('화면을 터치하세요')을 거쳐 맵으로 이동한다.
const startButton = document.getElementById('start-button');
let pressTimer;
let isTransitioning = false;

startButton.addEventListener('click', () => {
  if (pressTimer || isTransitioning) return;

  isTransitioning = true;
  startButton.classList.add('is-pressed');
  pressTimer = window.setTimeout(() => {
    startButton.classList.remove('is-pressed');
    pressTimer = undefined;
    isTransitioning = false;

    openIntroScreen(false);
  }, 160);
});

// 인트로 화면을 터치·클릭하거나 Enter/Space를 누르면 방문 기록을 남기고 맵으로 이동한다.
let introLocked = false;

function finishIntro() {
  if (introLocked || screens.intro?.hidden) return;
  introLocked = true;
  markIntroSeen();
  enterMapScreen();
}

if (screens.intro) {
  screens.intro.addEventListener('click', finishIntro);
  screens.intro.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      finishIntro();
    }
  });
}




