"""共享配置和工具"""
import os

# 禁用系统代理
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
REQUEST_PROXIES = {'http': None, 'https': None}
