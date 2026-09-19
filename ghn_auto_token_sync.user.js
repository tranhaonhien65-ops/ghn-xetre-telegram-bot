// ==UserScript==
// @name         GHN Auto Token Sync for Telegram Bot (Smart JWT)
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  Tự động lọc token còn hạn mới nhất từ GHN và đồng bộ lên Cloud Render
// @author       Antigravity
// @match        https://nhanh.ghn.vn/*
// @grant        GM_xmlhttpRequest
// @connect      ghn-xetre-telegram-bot.onrender.com
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let lastSentToken = "";
    const CLOUD_SYNC_URL = "https://ghn-xetre-telegram-bot.onrender.com/update_token";
    const LOCAL_SYNC_URL = "http://localhost:8989/update_token";

    function decodeJwtExp(token) {
        try {
            const parts = token.split('.');
            if (parts.length >= 2) {
                const padded = parts[1] + '='.repeat((4 - parts[1].length % 4) % 4);
                const payload = JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')));
                return payload.exp || 0;
            }
        } catch (e) {}
        return 0;
    }

    function sendToUrl(url, payload, isCloud = false) {
        if (typeof GM_xmlhttpRequest !== "undefined") {
            GM_xmlhttpRequest({
                method: "POST",
                url: url,
                headers: { "Content-Type": "application/json" },
                data: payload,
                onload: function(res) {
                    if (res.status === 200 && isCloud) {
                        console.log("%c[GHN Bot Sync] ☁️ Đã nạp Token mới lên Cloud thành công!", "color: #28a745; font-weight: bold;");
                        showToast("☁️ Đã đồng bộ Token GHN mới lên Cloud (24/7)!");
                    }
                },
                onerror: function() {}
            });
        } else {
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: payload
            }).then(r => r.json()).then(data => {
                if (isCloud) {
                    showToast("☁️ Đã đồng bộ Token GHN mới lên Cloud (24/7)!");
                }
            }).catch(() => {});
        }
    }

    function sendTokenToBot(token, force = false) {
        if (!token || token.length < 30) return;
        const nowSec = Math.floor(Date.now() / 1000);
        const exp = decodeJwtExp(token);
        
        // Bỏ qua token đã hết hạn
        if (exp > 0 && exp <= nowSec) {
            console.warn("[GHN Bot Sync] Bỏ qua token đã hết hạn:", exp);
            return;
        }

        if (!force && token === lastSentToken) return;
        lastSentToken = token;

        console.log("%c[GHN Bot Sync] 🚀 Đang gửi Token còn hạn lên Cloud (Hạn: " + (exp > 0 ? new Date(exp * 1000).toLocaleString('vi-VN') : 'N/A') + ")...", "color: #0088cc; font-weight: bold;");
        const payload = JSON.stringify({ token: token });

        sendToUrl(CLOUD_SYNC_URL, payload, true);
        sendToUrl(LOCAL_SYNC_URL, payload, false);
    }

    function getBestTokenFromStorage() {
        let bestToken = null;
        let maxExp = 0;
        const nowSec = Math.floor(Date.now() / 1000);

        function checkVal(val) {
            if (!val || typeof val !== "string" || !val.includes("eyJhbGciOi")) return;
            const matches = val.match(/eyJhbGciOi[a-zA-Z0-9_.\-]+/g) || [];
            for (const t of matches) {
                const exp = decodeJwtExp(t);
                if (exp > maxExp) {
                    maxExp = exp;
                    bestToken = t;
                }
            }
        }

        try {
            for (let i = 0; i < localStorage.length; i++) {
                checkVal(localStorage.getItem(localStorage.key(i)));
            }
            for (let i = 0; i < sessionStorage.length; i++) {
                checkVal(sessionStorage.getItem(sessionStorage.key(i)));
            }
            if (document.cookie) {
                checkVal(document.cookie);
            }
        } catch (e) {}

        if (bestToken && maxExp > nowSec) {
            return bestToken;
        }
        return null;
    }

    function showToast(message) {
        if (!document.body) return;
        const toast = document.createElement("div");
        toast.innerText = message;
        toast.style.position = "fixed";
        toast.style.bottom = "20px";
        toast.style.right = "20px";
        toast.style.backgroundColor = "#0088cc";
        toast.style.color = "#fff";
        toast.style.padding = "10px 18px";
        toast.style.borderRadius = "8px";
        toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
        toast.style.zIndex = "999999";
        toast.style.fontSize = "13px";
        toast.style.fontWeight = "bold";
        toast.style.transition = "opacity 0.5s ease";
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }

    // 1. Intercept XMLHttpRequest
    const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
        if (header.toLowerCase() === "authorization" && value && value.startsWith("Bearer ")) {
            const token = value.replace("Bearer ", "").trim();
            sendTokenToBot(token);
        }
        return originalSetRequestHeader.apply(this, arguments);
    };

    // 2. Intercept Fetch API
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            if (args[1] && args[1].headers) {
                let auth = "";
                if (args[1].headers instanceof Headers) {
                    auth = args[1].headers.get("Authorization") || args[1].headers.get("authorization") || "";
                } else if (typeof args[1].headers === "object") {
                    auth = args[1].headers["Authorization"] || args[1].headers["authorization"] || "";
                }
                if (auth.startsWith("Bearer ")) {
                    sendTokenToBot(auth.replace("Bearer ", "").trim());
                }
            }
        } catch (e) {}
        return originalFetch.apply(this, args);
    };

    function triggerSync() {
        const token = getBestTokenFromStorage();
        if (token) {
            sendTokenToBot(token, true);
        }
    }

    // 3. Auto sync on load, focus, visibility
    window.addEventListener("load", triggerSync);
    window.addEventListener("focus", triggerSync);
    document.addEventListener("visibilitychange", function() {
        if (!document.hidden) {
            triggerSync();
        }
    });

    // 4. Periodic re-sync mỗi 5 phút
    setInterval(triggerSync, 5 * 60 * 1000);

})();
