#!/usr/bin/env python3
"""100 小游戏批量生产监督脚本：pi 生成 -> 自动验收 -> 日志。可断点续跑。
用法: nohup python3 supervise.py > supervisor.log 2>&1 &
"""
import concurrent.futures as cf
import json, os, subprocess, sys, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PI = os.path.expanduser("~/.local/bin/pi")
LOG = os.path.join(BASE, "progress.log")
PARALLEL = 3
TIMEOUT = 600  # 单个游戏最多 10 分钟

PROMPT_TMPL = """在当前目录创建 index.html，实现一个手机优先的「{name}」小游戏：{spec}。要求：
1. 单文件，HTML+CSS+JS 全内联，零外部依赖
2. 移动端优先：viewport meta、touch-action:none、禁止双击缩放和页面滚动，布局自适应手机屏幕
3. 操作必须适合触屏（上面玩法说明里已给出具体手势），键盘/鼠标兼容更佳
4. 中文界面；计分与最高分（localStorage 保存）；游戏结束/胜利弹窗与重开按钮；暂停按钮
5. 视觉精致，优先深色霓虹风（除非题材更适合其他风格）
6. 代码整洁，注释中文
写完后只回复 DONE"""

def load_games():
    games = []
    with open(os.path.join(BASE, "games.psv"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            d, name, emoji, spec = parts[0], parts[1], parts[2], "|".join(parts[3:])
            games.append({"dir": d, "name": name, "emoji": emoji, "spec": spec})
    return games

def valid(path):
    if not os.path.isfile(path):
        return False
    if os.path.getsize(path) < 8192:
        return False
    with open(path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # 脚本标签可能在很长的 <style> 之后，搜全文；同时要求有 html 骨架
    low = content.lower()
    return "<script" in low and "</html>" in low

def log(rec):
    rec["at"] = datetime.now().strftime("%H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['at']}] {rec['dir']}: {rec['status']}" + (f" ({rec.get('note','')})" if rec.get("note") else ""), flush=True)

def build(g):
    d = os.path.join(BASE, g["dir"])
    os.makedirs(d, exist_ok=True)
    idx = os.path.join(d, "index.html")
    if valid(idx):
        log({"dir": g["dir"], "status": "skip", "note": "已存在"})
        return True
    prompt = PROMPT_TMPL.format(name=g["name"], spec=g["spec"])
    t0 = time.time()
    try:
        p = subprocess.run(
            [PI, "-p", "--provider", "kimi", "--model", "kimi/k3.1-pro-highspeed",
             "--thinking", "low", "--no-session", prompt],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=TIMEOUT, cwd=d)
        out = (p.stdout or "").strip()
        ok = valid(idx) and "DONE" in out
        el = int(time.time() - t0)
        if ok:
            log({"dir": g["dir"], "status": "ok", "note": f"{el}s"})
            return True
        log({"dir": g["dir"], "status": "fail", "note": f"{el}s out={out[-80:]!r}"})
        return False
    except subprocess.TimeoutExpired:
        if valid(idx):
            log({"dir": g["dir"], "status": "ok", "note": "超时但文件有效"})
            return True
        log({"dir": g["dir"], "status": "timeout"})
        return False
    except Exception as e:
        log({"dir": g["dir"], "status": "error", "note": str(e)[:80]})
        return False

def main():
    games = load_games()
    todo = [g for g in games if g["spec"] != "DONE"]
    print(f"共 {len(games)} 个，待生产 {len(todo)} 个，{PARALLEL} 并行", flush=True)
    done_n = fail_n = 0
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futs = {ex.submit(build, g): g for g in todo}
        for fut in cf.as_completed(futs):
            if fut.result():
                done_n += 1
            else:
                fail_n += 1
    print(f"本轮结束：成功 {done_n}，失败 {fail_n}", flush=True)

if __name__ == "__main__":
    main()
