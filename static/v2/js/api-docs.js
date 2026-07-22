document.querySelectorAll('[data-copy-code]').forEach((button) => {
  button.addEventListener('click', async () => {
    const code = button.closest('.code-block')?.querySelector('code')?.textContent || '';
    try {
      await navigator.clipboard.writeText(code);
      button.textContent = '已複製';
      setTimeout(() => { button.textContent = '複製'; }, 1600);
    } catch (_) {
      button.textContent = '無法複製';
    }
  });
});
