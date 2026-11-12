# AI Core

[![Version](https://img.shields.io/github/v/release/blackkcold/ai-core?label=version)](https://github.com/blackkcold/ai-core/releases/latest)
[![CI](https://github.com/blackkcold/ai-core/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/blackkcold/ai-core/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
[![MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[English](README.md) · **简体中文**

基于 MIT 协议的轻量级、跨应用 AI 模型与网络搜索统一接入核心。

## 核心能力

- 22 个模型 Provider 配置、官方模型发现与免费模型发现
- 统一对话、工具调用、流式输出及多协议适配
- 19 个搜索来源：免密钥公共数据源、可选 API、自建搜索
- REST、MCP、安全网页读取、身份认证、缓存与用量管理
- Python、TypeScript、Swift、Kotlin 客户端
- Ollama / LM Studio 本地免费模型优先；可选 OpenRouter 免费模型路由

## 安装

```bash
git clone https://github.com/blackkcold/ai-core.git
cd ai-core
python -m pip install -e .
ai-core serve
```

默认地址：`http://127.0.0.1:8765`。**启动服务及默认公共搜索不需要厂商 API Key**。

## 无 API Key 的免费模型

先安装 [Ollama](https://ollama.com/download)，再执行：

```bash
ai-core setup-free                   # 下载 qwen3:0.6b（约 523 MB）
ai-core chat --prompt "你好"         # 自动发现并调用已安装的本地模型
ai-core free-models                  # 查看本地就绪状态与免费额度模型
```

也可以使用已启动并加载模型的 LM Studio。**未安装本地推理服务和模型时，无法保证无 Key 的在线大模型调用**。OpenRouter 等云端免费模型仍需要账户 Key；付费云模型默认关闭。

## 搜索

```bash
ai-core search "Python"
ai-core search "论文检索" --provider openalex
ai-core search "科技新闻" --provider hackernews
```

默认通用搜索使用 You.com 官方无密钥 MCP 免费档（服务商公布每日 100 次），研究、新闻和资料来源使用专门数据源。额度及可用性由服务商控制。REST/MCP 可使用 `category=research|news|developer|books` 指定检索类别。

## Docker

```bash
cp .env.example .env
export AI_CORE_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
docker compose up -d --build
# 可选本地推理：自动拉取约 523 MB 免费模型
docker compose --profile local-llm up -d --build
```

密钥、付费权限及预算需显式配置；容器内无法自动访问宿主机的本地模型服务。

## 文档

[Provider 指南](docs/PROVIDERS.md) · [集成部署](docs/INTEGRATION.md) · [兼容性](docs/COMPATIBILITY.md) · [维护指南](docs/MAINTENANCE.md) · [安全说明](docs/SECURITY.md)

## 开源协议

[MIT](LICENSE)
