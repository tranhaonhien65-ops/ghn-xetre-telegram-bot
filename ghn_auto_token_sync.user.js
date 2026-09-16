// ==UserScript==
// @name         GHN Auto Token Sync for Telegram Bot
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Tự động đồng bộ Bearer Token từ nhanh.ghn.vn sang Telegram Bot
// @author       Antigravity
// @match        https://nhanh.ghn.vn/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let lastSentToken = "";
    const SYNC_URL = "http://localhost:8989/update_token";

    function sendTokenToBot(token) {
        if (!token || token === lastSentToken || token.length < 30) return;
        lastSentToken = token;

        console.log("%c[GHN Bot Sync] Đang đồng bộ Token mới sang Bot...", "color: #0088cc; font-weight: bold;");

        const payload = JSON.stringify({ token: token });

        if (typeof GM_xmlhttpRequest !== "undefined") {
            GM_xmlhttpRequest({
                method: "POST",
                url: SYNC_URL,
                headers: { "Content-Type": "application/json" },
                data: payload,
                onload: function(res) {
                    if (res.status === 200) {
                        console.log("%c[GHN Bot Sync] ✅ Đồng bộ Token thành công!", "color: #28a745; font-weight: bold;");
                        showToast("✅ Đã đồng bộ Token mới sang Telegram Bot!");
                    }
                },
                onerror: function(err) {
                    console.warn("[GHN Bot Sync] Chưa mở Bot hoặc không kết nối được localhost:8989");
                }
            });
        } else {
            fetch(SYNC_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: payload
            }).then(r => r.json()).then(data => {
                console.log("%c[GHN Bot Sync] ✅ Đồng bộ Token thành công!", "color: #28a745; font-weight: bold;");
                showToast("✅ Đã đồng bộ Token mới sang Telegram Bot!");
            }).catch(() => {});
        }
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

    // 3. Scan Storage on load
    window.addEventListener("load", function() {
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const val = localStorage.getItem(localStorage.key(i));
                if (val && val.includes("eyJhbGciOi")) {
                    const match = val.match(/eyJhbGciOi[a-zA-Z0-9_\.\-]+/);
                    if (match) sendTokenToBot(match[0]);
                }
            }
        } catch (e) {}
    });

})();
