"""PyInstaller 打包脚本 — 自动用 venv python 打包"""
import os
import sys
import subprocess

# 强制关闭正在运行的 exe
EXE_NAME = '鑫多多.exe'
try:
    import psutil
    for p in psutil.process_iter(['name']):
        if p.info['name'] == EXE_NAME:
            p.kill()
            print(f'已终止: {EXE_NAME}')
except ImportError:
    # 无 psutil 时用 taskkill
    subprocess.run(['taskkill', '/F', '/IM', EXE_NAME], capture_output=True)

PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv', 'Scripts', 'python.exe')
if not os.path.exists(PYTHON):
    print('错误：找不到 venv，请先创建虚拟环境并安装依赖')
    sys.exit(1)

if sys.executable.lower() != os.path.normpath(PYTHON).lower():
    print(f'重新以 venv python 执行: {PYTHON}')
    os.execv(PYTHON, [PYTHON, __file__])

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))

# 数据文件
import akshare, site
akshare_dir = os.path.dirname(os.path.abspath(akshare.__file__))
akshare_path = os.path.join(akshare_dir, 'file_fold')
datas = [
    (os.path.join(ROOT, 'front_end', 'templates'), 'front_end\\templates'),
    (os.path.join(ROOT, 'front_end', 'static'), 'front_end\\static'),
    (os.path.join(ROOT, 'back_end', 'data'), 'back_end\\data'),
    (akshare_path, 'akshare\\file_fold'),
]

# 隐式导入的服务模块
hidden_imports = [
    'services', 'services.__init__',
    'services.market_data', 'services.money_flow',
    'services.finance', 'services.search',
    'services.watchlist', 'services.utils',
    'services.technical_screen',
]

PyInstaller.__main__.run([
    os.path.join(ROOT, 'back_end', 'app.py'),
    '--name=鑫多多',
    '--onefile',
    '--console',
    '--clean',
    '--noconfirm',
    '--add-data=' + os.pathsep.join([datas[0][0], datas[0][1]]),
    '--add-data=' + os.pathsep.join([datas[1][0], datas[1][1]]),
    '--add-data=' + os.pathsep.join([datas[2][0], datas[2][1]]),
    '--add-data=' + os.pathsep.join([datas[3][0], datas[3][1]]),
] + [f'--hidden-import={m}' for m in hidden_imports])
