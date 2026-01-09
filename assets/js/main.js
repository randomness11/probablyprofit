// Copy install command
function copyInstall() {
    const command = 'pip install probablyprofit';
    const hint = document.getElementById('copyHint');

    navigator.clipboard.writeText(command).then(() => {
        hint.textContent = 'copied!';
        hint.classList.add('copied');

        setTimeout(() => {
            hint.textContent = 'click to copy';
            hint.classList.remove('copied');
        }, 2000);
    });
}
