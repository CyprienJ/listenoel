(function () {
    "use strict";

    const form = document.querySelector(".nc-bug-form");
    if (!form) return;

    const unknown = form.dataset.unknown;

    function detectBrowser() {
        const ua = navigator.userAgent;
        const browsers = [
            ["Firefox", /Firefox\/([\d.]+)/],
            ["Edge", /Edg\/([\d.]+)/],
            ["Opera", /OPR\/([\d.]+)/],
            ["Chrome", /Chrome\/([\d.]+)/],
        ];
        for (const [name, pattern] of browsers) {
            const match = pattern.exec(ua);
            if (match) return `${name} ${match[1]}`;
        }
        if (ua.includes("Safari")) {
            const safariVersion = /Version\/([\d.]+)/.exec(ua);
            if (safariVersion) return `Safari ${safariVersion[1]}`;
        }
        return unknown;
    }

    function detectOperatingSystem() {
        const ua = navigator.userAgent;
        if (/Windows NT 10/.test(ua)) return "Windows 10/11";
        if (/Windows/.test(ua)) return "Windows";
        const android = /Android ([\d.]+)/.exec(ua);
        if (android) return `Android ${android[1]}`;
        if (/iPhone|iPad/.test(ua)) {
            const match = /OS ([\d_]+)/.exec(ua);
            return match ? `iOS/iPadOS ${match[1].replaceAll("_", ".")}` : "iOS/iPadOS";
        }
        const macOS = /Mac OS X ([\d_]+)/.exec(ua);
        if (macOS) return `macOS ${macOS[1].replaceAll("_", ".")}`;
        if (/Linux/.test(ua)) return "Linux";
        return unknown;
    }

    function detectDevice() {
        const ua = navigator.userAgent;
        if (/iPad|Tablet/.test(ua)) return "tablet";
        if (/Mobi|Android/.test(ua)) return "mobile";
        return "desktop";
    }

    function sourcePath() {
        const existingValue = form.elements.page_path?.value;
        if (existingValue) return existingValue;
        let path = "";
        try {
            path = sessionStorage.getItem("bugReportSourcePath") || "";
            sessionStorage.removeItem("bugReportSourcePath");
        } catch (error) {
            console.debug("Session storage is unavailable; using the referrer as fallback.", error);
        }
        if (!path && document.referrer) {
            const referrer = new URL(document.referrer);
            if (referrer.origin === window.location.origin) path = referrer.pathname;
        }
        return path || window.location.pathname;
    }

    const device = detectDevice();
    const deviceLabels = {
        desktop: form.dataset.desktop,
        mobile: form.dataset.mobile,
        tablet: form.dataset.tablet,
    };
    const context = {
        page_path: sourcePath(),
        browser: detectBrowser(),
        operating_system: detectOperatingSystem(),
        device_type: device,
        viewport: `${window.innerWidth} × ${window.innerHeight}`,
        browser_language: navigator.language || unknown,
        browser_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || unknown,
    };

    for (const [name, value] of Object.entries(context)) {
        const input = form.elements[name];
        if (input) input.value = value;
    }

    document.getElementById("bugContextPage").textContent = form.dataset.currentPage;
    document.getElementById("bugContextBrowser").textContent = context.browser;
    document.getElementById("bugContextOs").textContent = context.operating_system;
    document.getElementById("bugContextDevice").textContent = deviceLabels[device] || unknown;
    document.getElementById("bugContextViewport").textContent = context.viewport;
    document.getElementById("bugContextLanguage").textContent = context.browser_language;
    document.getElementById("bugContextTimezone").textContent = context.browser_timezone;
})();
