// 화면 전환: data-go가 달린 버튼을 누르면 그 id의 화면만 보인다
function showScreen(id) {
  document.querySelectorAll('.screen').forEach((screen) => {
    screen.hidden = screen.id !== id;
  });

  // 키보드 사용자를 위해 새 화면의 버튼으로 초점 이동
  const next = document.getElementById(id);
  const button = next && next.querySelector('.btn');
  if (button) button.focus({ preventScroll: true });
}

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-go]');
  if (target) showScreen(target.dataset.go);
});
