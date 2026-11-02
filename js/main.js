// 배경 한 장을 중앙 기준으로 자른다. PC 양옆과 모바일 중앙의 배율은 공유한다.
// 1152×384 원본의 정수배만 사용하고, 짧은 화면은 1배부터 시작한다.
function fitTitleWorld() {
  const root = document.documentElement;
  const baseScale = root.clientHeight <= 560 ? 1 : 2;
  const scale = Math.max(baseScale, Math.ceil(root.clientWidth / 1152));
  root.style.setProperty('--scene-width', `${1152 * scale}px`);
  root.style.setProperty('--scene-height', `${384 * scale}px`);
}

fitTitleWorld();
window.addEventListener('resize', fitTitleWorld);

const INTRO_SEEN_KEY = 'guessty_intro_seen';

const screens = {
  title: document.getElementById('screen-title'),
  intro: document.getElementById('screen-intro'),
  map: document.getElementById('screen-map'),
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

function showScreen(name, isIndoor = false) {
  Object.entries(screens).forEach(([key, section]) => {
    if (!section) return;
    section.hidden = key !== name;
  });
  document.body.classList.toggle('world-indoor', isIndoor);
  document.body.classList.toggle('world-outdoor', !isIndoor);
}

// PRESS START → 첫 방문이면 인트로, 재방문이면 맵으로 이동한다.
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

    if (hasSeenIntro()) {
      showScreen('map', false);
    } else {
      showScreen('intro', false);
      screens.intro?.focus();
    }
  }, 160);
});

// 인트로 화면을 터치·클릭하거나 Enter/Space를 누르면 방문 기록을 남기고 맵으로 이동한다.
let introLocked = false;

function finishIntro() {
  if (introLocked || screens.intro?.hidden) return;
  introLocked = true;
  markIntroSeen();
  showScreen('map', false);
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



