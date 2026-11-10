// ==UserScript==
// @name         GHN Auto Token Sync for Telegram Bot (Smart JWT v3.0)
// @namespace    http://tampermonkey.net/
// @version      3.0
// @description  Tự động đồng bộ Token Điều Phối GHN & Metabase Báo Cáo lên Cloud Render 24/7
// @author       Antigravity
// @match        https://nhanh.ghn.vn/*
// @match        https://baocao.ghn.vn/*
// @match        https://data-bi.ghn.vn/*
// @grant        GM_xmlhttpRequest
// @connect      ghn-xetre-telegram-bot.onrender.com
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let lastSentToken = "";
    let lastSentMbToken = "";
    const CLOUD_SYNC_URL = "https://ghn-xetre-telegram-bot.onrender.com/update_token";
    const LOCAL_SYNC_URL = "http://localhost:8989/update_token";

    function parseGhnJwt(token) {
        if (!token || typeof token !== "string" || token.length < 30) return null;
        try {
            const parts = token.split('.');
            if (parts.length >= 2) {
                const padded = parts[1] + '='.repeat((4 - parts[1].length % 4) % 4);
                const payload = JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')));
                if (payload.typ === 'coordinator' || payload.hid || payload.noc || payload.orgCode === 'ghnexpress' || payload.ssoId) {
                    return payload;
                }
            }
        } catch (e) {}
        return null;
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
                        console.log("%c[GHN Bot Sync] ☁️ Đã đồng bộ Token lên Cloud thành công!", "color: #28a745; font-weight: bold;");
                    }
                },
                onerror: function() {}
            });
        } else {
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: payload
            }).catch(() => {});
        }
    }

    function sendTokenToBot(token, force = false) {
        const payloadJson = parseGhnJwt(token);
        if (!payloadJson) return;
        
        const nowSec = Math.floor(Date.now() / 1000);
        const exp = payloadJson.exp || 0;
        if (exp > 0 && exp <= nowSec) return;

        if (!force && token === lastSentToken) return;
        lastSentToken = token;

        console.log("%c[GHN Bot Sync] 🚀 Đồng bộ Token: " + (payloadJson.noc || payloadJson.ssoId || '') + "...", "color: #0088cc; font-weight: bold;");
        const payload = JSON.stringify({ token: token });
        sendToUrl(CLOUD_SYNC_URL, payload, true);
        sendToUrl(LOCAL_SYNC_URL, payload, false);
    }

    function sendMetabaseJwt(jwt, rawUrl = "") {
        if (!jwt || jwt === lastSentMbToken) return;
        lastSentMbToken = jwt;
        console.log("%c[GHN Bot Sync] 📊 Đồng bộ Metabase JWT mới...", "color: #28a745; font-weight: bold;");
        const payload = JSON.stringify({ token: jwt, url: rawUrl });
        sendToUrl(CLOUD_SYNC_URL, payload, true);
        sendToUrl(LOCAL_SYNC_URL, payload, false);
        showToast("📊 Đã nạp Metabase JWT lên Cloud 24/7!");
    }

    function checkMetabaseInString(str) {
        if (!str || typeof str !== "string") return;
        const mbMatch = str.match(/embed\/dashboard\/([a-zA-Z0-9_\-\.]+)/);
        if (mbMatch) {
            const jwt = mbMatch[1].split('?')[0].split('/')[0];
            sendMetabaseJwt(jwt, str);
        }
    }

    function getBestGhnToken() {
        let bestToken = null;
        let maxExp = 0;
        const nowSec = Math.floor(Date.now() / 1000);

        function checkVal(val) {
            if (!val || typeof val !== "string" || !val.includes("eyJhbGciOi")) return;
            checkMetabaseInString(val);
            const matches = val.match(/eyJhbGciOi[a-zA-Z0-9_.\-]+/g) || [];
            for (const t of matches) {
                const p = parseGhnJwt(t);
                if (p && p.exp && p.exp > maxExp && p.exp > nowSec) {
                    maxExp = p.exp;
                    bestToken = t;
                } else if (p && (p.orgCode || p.ssoId)) {
                    sendTokenToBot(t, false);
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

        return bestToken;
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

    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === "string") {
            checkMetabaseInString(url);
        }
        return originalOpen.apply(this, [method, url, ...rest]);
    };

    // 2. Intercept Fetch API
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const reqUrl = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
            checkMetabaseInString(reqUrl);

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

    function checkMetabaseElements() {
        try {
            // 1. Quét phần tử Web Component <metabase-dashboard token="...">
            const mbDash = document.querySelector('metabase-dashboard');
            if (mbDash) {
                const tok = mbDash.getAttribute('token') || mbDash.token;
                if (tok && tok.includes('eyJhbGciOi')) {
                    sendMetabaseJwt(tok, "metabase-dashboard element");
                }
            }

            // 2. Quét tất cả iframes
            const iframes = document.querySelectorAll('iframe');
            iframes.forEach(ifm => {
                const src = ifm.src || '';
                checkMetabaseInString(src);
            });
        } catch (e) {}
    }

    async function checkBaocaoReportToken() {
        try {
            if (window.location.host.includes("baocao.ghn.vn")) {
                const repToken = localStorage.getItem("token_report");
                const repIp = localStorage.getItem("IP") || "not_found";
                if (repToken && repToken.length > 20) {
                    const syncPayload = JSON.stringify({ report_uuid: repToken, report_ip: repIp, token: repToken });
                    sendToUrl(CLOUD_SYNC_URL, syncPayload, true);
                    sendToUrl(LOCAL_SYNC_URL, syncPayload, false);

                    // Tự động kéo Metabase JWT 12 tiếng mới trực tiếp từ API báo cáo
                    const res = await fetch("https://baocao-api.ghn.vn/baocao-service/report/dashboard/metabase-token", {
                        method: "POST",
                        headers: {
                            "content-type": "application/json",
                            "token": repToken,
                            "remote-ip": repIp
                        },
                        body: JSON.stringify({
                            user_id: 3007413,
                            dashboard_id: 221
                        })
                    });
                    const d = await res.json();
                    if (d && d.data && d.data.token) {
                        sendMetabaseJwt(d.data.token, "baocao_api_direct");
                    }
                }
            }
        } catch (e) {}
    }

    function triggerSync() {
        const token = getBestGhnToken();
        if (token) {
            sendTokenToBot(token, true);
        }
        checkMetabaseElements();
        checkBaocaoReportToken();
    }

    window.addEventListener("load", triggerSync);
    window.addEventListener("focus", triggerSync);
    document.addEventListener("visibilitychange", function() {
        if (!document.hidden) triggerSync();
    });

    setInterval(triggerSync, 5 * 60 * 1000);
    setInterval(checkMetabaseElements, 15 * 1000);

})();
