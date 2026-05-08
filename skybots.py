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

# ================= 配置区 =================
TARGET_URL = "https://dash.skybots.tech/login"
DASHBOARD_URL = "https://dash.skybots.tech/projects"

ACCOUNT = os.environ.get("SKYBOTS_ACCOUNT", "")
PASSWORD = os.environ.get("SKYBOTS_PASSWORD", "")
PROXY = os.environ.get("skybots_PROXY_NODE", "")

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

# 强制暴露隐藏的 CF 盾
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

# 获取盾的绝对屏幕坐标
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

# 使用 Linux 底层工具进行物理点击
def os_hardware_click(x, y):
    try:
        # 激活浏览器窗口
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "chrome"], capture_output=True, text=True)
        w_ids = result.stdout.strip().split('\n')
        if w_ids and w_ids[0]:
            subprocess.run(["xdotool", "windowactivate", w_ids[0]], stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        
        # 移动并点击
        os.system(f"xdotool mousemove {int(x)} {int(y)} click 1")
        print(f"👆 已使用 xdotool 物理点击屏幕坐标 ({x}, {y})")
        return True
    except Exception as e:
        print(f"⚠️ xdotool 点击失败: {e}")
        return False

# ================= 主逻辑 =================
def main():
    if not ACCOUNT or not PASSWORD:
        print("❌ 缺少账号或密码环境变量")
        sys.exit(1)

    print("🔧 启动 SeleniumBase UC 模式浏览器...")
    opts = {
        "uc": True, 
        "test": True, 
        "headless": False, 
        "locale": "en", 
        "chromium_arg": "--disable-dev-shm-usage,--no-sandbox,--start-maximized"
    }
    if PROXY:
        opts["proxy"] = PROXY
        print(f"🛡️ 使用代理: {PROXY}")

    with SB(**opts) as sb:
        # 强制 xvfb 窗口大小
        sb.set_window_rect(0, 0, 1280, 720)
        
        try:
            print(f"🌐 访问目标网页: {TARGET_URL}")
            sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=6)
            time.sleep(5)

            if "projects" in sb.get_current_url():
                print("✅ 似乎已经处于登录状态！")
            else:
                print("🛡️ 正在解析登录表单...")
                # 兼容不同输入框
                user_sel = 'input[type="email"], input[name="email"], input[name="username"], input[type="text"]'
                sb.wait_for_element(user_sel, timeout=30)
                
                print("✏️ 填写账号密码...")
                sb.type(user_sel, ACCOUNT)
                sb.type('input[type="password"], input[name="password"]', PASSWORD)
                
                print("🛡️ 开始处理 Cloudflare 验证框...")
                time.sleep(3)

                # 将 CF 盾强制滚动到页面中央，确保 xdotool 能点到物理屏幕内
                cf_iframe_sel = "iframe[src*='cloudflare'], iframe[src*='turnstile']"
                if sb.is_element_present(cf_iframe_sel):
                    sb.scroll_to(cf_iframe_sel)
                    time.sleep(1)
                    # 随便点一下页面空白处，激活窗口焦点
                    sb.click('body', timeout=2) 
                    time.sleep(1)

                sb.execute_script(EXPAND_POPUP_JS)
                time.sleep(1)

                # 尝试突破 CF 盾
                cf_passed = False
                for attempt in range(5):
                    # 校验 1：判断底层 token 是否已生成
                    is_done = sb.execute_script("var cf = document.querySelector(\"input[name='cf-turnstile-response']\"); return cf && cf.value.length > 20;")
                    if is_done:
                        print("✅ CF 盾底层验证已通过！")
                        cf_passed = True
                        break
                    
                    print(f"🖱️ 尝试验证 (第 {attempt + 1} 次)...")
                    try:
                        # 方案 A：使用 SeleniumBase 原生专杀工具
                        sb.uc_gui_click_captcha()
                        print("⏳ 触发原生点击过盾，等待反应 (4秒)...")
                        time.sleep(4)
                    except Exception as e:
                        print(f"⚠️ 原生点击抛出异常: {e}")

                    # 校验 2：原生方法点完后，再次检查是否通过
                    if sb.execute_script("var cf = document.querySelector(\"input[name='cf-turnstile-response']\"); return cf && cf.value.length > 20;"):
                        print("✅ 原生方法点击成功！")
                        cf_passed = True
                        break

                    # 方案 B：使用获取坐标的底层硬件点击
                    print("⚠️ 原生未通过，尝试 xdotool 物理点击...")
                    coords = get_turnstile_coords(sb)
                    if coords:
                        # 加入随机偏移，防止被识别为机械点击，并兼容微小的坐标误差
                        click_x = coords['x'] + random.randint(-8, 8)
                        click_y = coords['y'] + random.randint(-4, 4)
                        
                        os_hardware_click(click_x, click_y)
                        print("⏳ 等待物理点击后的验证动画 (5秒)...")
                        time.sleep(5)
                    else:
                        print("⚠️ 仍未找到盾的位置坐标，等待重试...")
                        time.sleep(3)

                # 强校验拦截：如果 5 次都没过盾，拦截提交
                if not cf_passed:
                    print("❌ 警告：5 次尝试后 CF 盾仍未通过，登录极大概率会被拦截！")
                    sb.save_screenshot("cf_failed_state.png")
                    send_tg_photo("❌ 警告：CF 过盾失败，停止提交登录。", "cf_failed_state.png")
                    sys.exit(1) # 过盾失败，直接退出脚本，避免滥发无效请求
                else:
                    print("📤 盾已通过，提交登录...")
                    # 兼容法文和英文界面的提交按钮
                    sb.click('button[type="submit"], button:contains("Login"), button:contains("Se connecter")')
                
                print("⏳ 等待页面跳转...")
                time.sleep(10)
                
                if "projects" not in sb.get_current_url():
                    print("⚠️ URL 未变化，尝试直接访问 Dashboard...")
                    sb.uc_open_with_reconnect(DASHBOARD_URL, reconnect_time=5)
                    time.sleep(5)

            print("🚀 等待页面数据加载并查找续期按键...")
            sb.sleep(8) 
            
            # ================= 新增：提前抓取剩余时间并写入文件 =================
            expire_time_text = "未知"
            try:
                # 使用 XPath 查找包含 "Expire" 的节点，并获取它父级容器的文本
                expire_element = sb.wait_for_element('//*[contains(text(), "Expire")]/..', timeout=5)
                expire_time_text = expire_element.text.replace('\n', ' ').strip()
                print(f"⏱️ 当前抓取到的剩余时间: {expire_time_text}")
                
                # 写入供 Github Actions 解析
                with open("next_time.txt", "w", encoding="utf-8") as f:
                    f.write(expire_time_text)
                print("📝 已将时间写入 next_time.txt，准备供工作流调整时间使用")
            except Exception as e:
                print("⚠️ 无法在页面上找到剩余时间文本，将不写入文件。")
            # ==============================================================

            # 【高级容错逻辑】检测图 12 中的黄色提示消息
            too_early_sel = "//div[contains(., 'Renewal will be available 3 days before Expiration')]"
            if sb.is_element_visible(too_early_sel):
                print("⏰ 检测到'续期将于到期前 3 天提供'提示，暂无需续期。")
                shot_path = "renew_not_needed.png"
                sb.save_screenshot(shot_path)
                # 使用上面抓到的时间发送通知
                send_tg_photo(f"⏰ 暂无需续期。\n⏱️ 当前状态: {expire_time_text}", shot_path)
            else:
                # 修复选择器：支持英语(Renew)和法语(Renouveler)
                renew_selectors = [
                    'button:contains("Renew")', 
                    'button:contains("Renouveler")',
                    'a:contains("Renew")',
                    'a:contains("Renouveler")',
                    '//button[contains(., "Renew")]',
                    '//button[contains(., "Renouveler")]',
                    '//*[contains(text(), "Renew")]',
                    '//*[contains(text(), "Renouveler")]'
                ]
                found_btn = False
                
                for sel in renew_selectors:
                    if sb.is_element_visible(sel):
                        print(f"🔘 找到续期按键 (匹配器: {sel})，点击续期...")
                        sb.click(sel)
                        found_btn = True
                        break
                
                if found_btn:
                    print("⏳ 等待续期处理 (10秒)...")
                    sb.sleep(10)
                    
                    # 续期后，尝试重新抓取一下最新的时间来发通知，并更新文本
                    try:
                        expire_element = sb.wait_for_element('//*[contains(text(), "Expire")]/..', timeout=5)
                        expire_time_text = expire_element.text.replace('\n', ' ').strip()
                        print(f"⏱️ 续期后最新的剩余时间: {expire_time_text}")
                        # 覆盖写入最新的时间，确保 actions 基于成功续期后的时间计算
                        with open("next_time.txt", "w", encoding="utf-8") as f:
                            f.write(expire_time_text)
                    except Exception as e:
                        pass

                    shot_path = "renew_success.png"
                    sb.save_screenshot(shot_path)
                    
                    tg_msg = f"🎉 续期按钮已找到并点击！\n⏱️ 当前面板显示状态: {expire_time_text}"
                    send_tg_photo(tg_msg, shot_path)
                else:
                    print("❌ 未检测到续期按键。")
                    shot_path = "renew_error.png"
                    sb.save_screenshot(shot_path)
                    send_tg_photo("❌ 未检测到续期按键 (也未找到提前续期提示)。", shot_path)

        except Exception as e:
            print(f"❌ 运行报错: {e}")
            sb.save_screenshot("error.png")
            send_tg_photo(f"❌ 脚本运行异常: {e}", "error.png")
            sys.exit(1)

if __name__ == "__main__":
    main()
