(function () {
    const clicksBeforeSurprise = 5;

    document.querySelectorAll('[data-empty-list-easter-egg]').forEach(function (emptyState) {
        const message = emptyState.querySelector('[data-empty-list-message]');
        const surprise = emptyState.querySelector('[data-empty-list-surprise]');
        let clickCount = 0;

        if (!message || !surprise) return;

        emptyState.addEventListener('click', function (event) {
            if (event.target.closest('a, button, input, select, textarea, label')) return;
            if (clickCount >= clicksBeforeSurprise) return;

            clickCount += 1;
            if (clickCount === clicksBeforeSurprise) {
                message.textContent = surprise.textContent.trim();
                message.classList.add('nc-empty-list-surprise');
            }
        });
    });
})();
