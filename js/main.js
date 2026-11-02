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

// 첫 화면 디자인 단계이므로 아직 인트로로 이동하거나 방문 기록을 저장하지 않는다.
// 네이티브 button이 터치/클릭/Enter/Space를 처리하고, 연타 중 피드백은 한 번만 실행한다.
const startButton = document.getElementById('start-button');
let pressTimer;

startButton.addEventListener('click', () => {
  if (pressTimer) return;

  startButton.classList.add('is-pressed');
  pressTimer = window.setTimeout(() => {
    startButton.classList.remove('is-pressed');
    pressTimer = undefined;
  }, 160);
});
