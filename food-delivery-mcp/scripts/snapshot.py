#!/usr/bin/env python3
"""简单截图 + XML 脚本，手动操作后运行"""

import uiautomator2 as u2
import sys
import os
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "debug_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    
    d = u2.connect()
    ts = datetime.now().strftime("%H%M%S")
    prefix = f"{ts}_{name}"
    
    # 截图
    png = os.path.join(OUTPUT_DIR, f"{prefix}.png")
    d.screenshot(png)
    
    # XML
    xml_path = os.path.join(OUTPUT_DIR, f"{prefix}.xml")
    with open(xml_path, "w") as f:
        f.write(d.dump_hierarchy())
    
    print(f"✅ 已保存: {prefix}.png / {prefix}.xml")

if __name__ == "__main__":
    main()

