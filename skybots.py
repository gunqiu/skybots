#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import random
import subprocess
import requests
from datetime import datetime
from seleniumbase import SB

# ================= 配置区（只需要 Discord Token） =================
TARGET_URL = "https://dash.skybots.tech/login"
DASHBOARD_URL = "https://dash.skybots.tech/projects"

# 只读取 DISCORD_TOKEN，不需要账号密码
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
PROXY = os.environ.get("skybots_PROXY_NODE", "").strip()

TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# ================= 辅助函数 =================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def send_tg_photo(caption, image_path):
    if not TG_TOKEN or not TG_CHAT_ID or not os.path.exists(image_path):
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        with open(image_path, "rb") as f:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": f"[🤖 Skybots] {now_str()}\n{caption}"}, files={"photo": f}, timeout=30)
        print("📨 TG 图片推送成功！")
    except Exception as e:
        print(f"⚠️ TG 推送失败: {e}")

# 注入 Discord Token 免密登录
def inject_discord_login(sb, token):
    # 注入 localStorage（Discord 登录态）
    sb.execute_script("""
        localStorage.setItem('token', arguments[0]);
        sessionStorage.setItem('token', arguments[0]);
    """, token)
    # 注入请求头
    sb.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
        'headers': {'Authorization': token}
    })
    print("✅ Discord Token 登录态注入完成（无需账号密码）")

EXPAND_POPUP_JS = """
(function() {
    var iframes = document.querySelectorAll('iframe');
    iframes.forEach(function(iframe) {
        if (iframe.src && (iframe.src.includes('challenges.cloudflare.com') || iframe.src.includes('turnstile'))) {
            iframe.style.width = '300px';
            iframe.style.height = '65px';
            iframe.style.minWidth = '300px';
            iframe.style.visibility = 'visible';
            iframe.style.opacity = '1';
        }
    });
})();
"""

def get_turnstile_coords(sb):
    return sb.execute_script("""
        var iframes = document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            var src = iframes[i].src || '';
            if (src.includes('cloudflare') || src.includes('turnstile')) {
                var rect = iframes[i].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    var screenX = window.screenX || 0;
                    var screenY = window.screenY || 0;
                    var outerHeight = window.outerHeight;
                    var innerHeight = window.innerHeight;
                    var chromeBarHeight = outerHeight - innerHeight;
                    var abs_x = Math.round(rect.x + 30) + screenX;
                    var abs_y = Math.round(rect.y + rect.height / 2) + screenY + chromeBarHeight;
                    return {x: abs_x, y: abs_y};
                }
            }
        }
        return null;
    """)

def os_hardware_click(x, y):
    try:
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "chrome"], capture_output=True, text=True)
        w_ids = result.stdout.strip().split('\n')
        if w_ids and w_ids[0]:
            subprocess.run(["xdotool", "windowactivate", w_ids[0]], stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        os.system(f"xdotool mousemove {int(x)} {int(y)} click 1")
        print(f"👆 物理点击 ({x}, {y})")
        return True
    except Exception as e:
        print(f"⚠️ xdotool 失败: {e}")
        return False

# ================= 主逻辑（Discord 一键登录版） =================
def main():
    # 只校验 Discord Token，不校验账号密码
    if not DISCORD_TOKEN:
        print("❌ 未配置 DISCORD_TOKEN（GitHub Secrets）")
        sys.exit(1)

    print("🔧 启动浏览器（Discord 免密登录）")
    opts = {
        "uc": True, "test": True, "headless": False,
        "locale": "en", "chromium_arg": "--disable-dev-shm-usage,--no-sandbox,--start-maximized"
    }
    if PROXY:
        opts["proxy"] = PROXY
        print(f"🛡️ 代理: {PROXY}")

    with SB(**opts) as sb:
        sb.set_window_rect(0, 0, 1280, 720)
        try:
            print(f"🌐 访问: {TARGET_URL}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)
            time.sleep(3)

            # 关键：注入 Discord 登录态（不需要点按钮、不需要账号密码）
            inject_discord_login(sb, DISCORD_TOKEN)
            time.sleep(2)

            # 点 Discord 登录按钮
            print("🔗 点击 Discord 登录按钮")
            sb.click('a[href*="discord"], button:contains("Discord")', timeout=15)
            time.sleep(5)

            # 处理 CF 验证
            sb.execute_script(EXPAND_POPUP_JS)
            time.sleep(1)
            cf_passed = False
            for attempt in range(5):
                is_done = sb.execute_script("var cf=document.querySelector('input[name=cf-turnstile-response]'); return cf&&cf.value.length>20;")
                if is_done:
                    print("✅ CF 验证通过")
                    cf_passed = True
                    break
                print(f"🖱️ 第 {attempt+1} 次过盾")
                try:
                    sb.uc_gui_click_captcha()
                    time.sleep(4)
                except:
                    pass
                coords = get_turnstile_coords(sb)
                if coords:
                    os_hardware_click(coords['x']+random.randint(-8,8), coords['y']+random.randint(-4,4))
                    time.sleep(5)

            if not cf_passed:
                sb.save_screenshot("cf_failed.png")
                send_tg_photo("❌ CF 验证失败", "cf_failed.png")
                sys.exit(1)

            # 进入面板
            print("⏳ 等待授权跳转...")
            time.sleep(10)
            if "projects" not in sb.get_current_url():
                sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=5)
                time.sleep(5)
            print("✅ 成功登录（Discord 免密）")

            # 抓取到期时间
            expire_time_text = "未知"
            try:
                expire_element = sb.wait_for_element('//*[contains(text(), "Expire")]/..', timeout=5)
                expire_time_text = expire_element.text.replace('\n', ' ').strip()
                print(f"⏱️ 到期时间: {expire_time_text}")
                with open("next_time.txt", "w", encoding="utf-8") as f:
                    f.write(expire_time_text)
            except:
                print("⚠️ 未抓到到期时间")

            # 检测是否需要续期
            if sb.is_element_visible("//div[contains(., 'Renewal will be available 3 days before Expiration')]"):
                sb.save_screenshot("no_need.png")
                send_tg_photo(f"⏰ 无需续期\n{expire_time_text}", "no_need.png")
            else:
                renew_selectors = ['button:contains("Renew")', 'button:contains("Renouveler")', 'a:contains("Renew")']
                for sel in renew_selectors:
                    if sb.is_element_visible(sel):
                        sb.click(sel)
                        print("✅ 已点击续期")
                        time.sleep(10)
                        sb.save_screenshot("renew_ok.png")
                        send_tg_photo(f"🎉 续期成功\n{expire_time_text}", "renew_ok.png")
                        break
                else:
                    sb.save_screenshot("no_btn.png")
                    send_tg_photo("❌ 未找到续期按钮", "no_btn.png")

        except Exception as e:
            print(f"❌ 异常: {e}")
            sb.save_screenshot("error.png")
            send_tg_photo(f"❌ 错误: {e}", "error.png")
            sys.exit(1)

if __name__ == "__main__":
    main()
