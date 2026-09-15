# Zotero RSS Digest

[English](README.en.md)

Zotero 10 插件：读取左侧 **订阅（RSS Feeds）**，按研究画像筛选，可选调用兼容 OpenAI 的 LLM 写成中文/英文卡片，再把感兴趣的文献一键存进「我的文库」。

**当前版本：0.2.17** · 兼容 **Zotero 10.0–10.0.\***（含 10.0.2）

[**下载 rss-digest.xpi（v0.2.17）**](https://github.com/kexiao-nj/zotero-rss-digest/raw/main/dist/rss-digest.xpi)

## 安装

1. 下载 [rss-digest.xpi](https://github.com/kexiao-nj/zotero-rss-digest/raw/main/dist/rss-digest.xpi)。
2. 在 Zotero：**工具 → 插件 → 齿轮 → Install Plugin From File…**，选择刚下载的 `.xpi`。
3. **完全退出并重启 Zotero**。

安装包也托管在仓库 [`dist/rss-digest.xpi`](https://github.com/kexiao-nj/zotero-rss-digest/blob/main/dist/rss-digest.xpi)。不要把本插件注册进 Zotero 自带设置页；设置在插件自己的面板里。

本地从源码打包：

```bash
python3 plugin/package_xpi.py
```

输出为 `build/rss-digest.xpi`。

## 使用

菜单：**工具 → RSS Digest**。主窗口上会盖一层面板（立即扫描 / 重新扫描 / 导出 Markdown / 结果 / 设置 / 关闭）。

| 操作 | 作用 |
|---|---|
| **立即扫描** | 只处理尚未见过、且落在扫描时间范围内的条目（增量）。 |
| **重新扫描** | 按设置里的时间范围再扫一遍，不跳过已见过的 GUID。默认最近 7 天。 |
| **导出 Markdown** | 把当前结果存成 `.md` 文件。需先有扫描结果。 |
| **结果** | 查看卡片。 |
| **设置** | API、语言、扫描时间范围、Collection、Topics / Keywords。改完后点 **保存设置**。 |
| **添加到我的文库** | 用 Zotero 自己的订阅翻译写入指定 Collection，并附一条提炼笔记。 |

高分条目**不会**自动入库，由你点选。

扫描进度会显示在结果页（读订阅 / LLM 提炼 / 补译 / 百分比）。关闭面板不会丢掉本次结果；结果也写在 Zotero 数据目录的 `rss-digest-state.json` 里。

## 设置说明

| 字段 | 含义 |
|---|---|
| Base URL / API Key / Model | 兼容 OpenAI 的接口（DeepSeek、OpenRouter、本地 vLLM 均可）。**不填 Key 则只做关键词筛选，不翻译、不调用 LLM。** |
| Interval (hours) | 后台定时扫描间隔，默认 6 小时。 |
| Lookback days / 起始–结束日期 | 只扫描这个时间范围内的条目。日期留空则按回看天数从今天往回算，**默认 7 天**。填了起始/结束日期则按该区间（结束日期留空则到今天）。「填入最近 N 天」会把回看天数写成具体日期。 |
| Digest language | **中文**：标题、摘要和提炼卡片译成简体中文，原标题/原文摘要仍保留。**English**：卡片为英文。 |
| Save-to collection | 入库集合名，不存在会自动创建，默认 `RSS Digest`。 |
| **Topics** | 课题方向，一行一个。与 Include 一起做匹配并加规则分；有 API Key 时作为 LLM 的研究画像。 |
| **Include keywords** | 希望留下的词，一行一个。在标题、摘要、期刊、作者、DOI 里做**不区分大小写的子串**匹配。 |
| **Exclude keywords** | 黑名单。命中任一排除词则直接跳过，不送给 LLM。 |

改完必须点 **保存设置**。**Test LLM** 会先保存再测接口。

## 打分（卡片上的 Score）

Score 是 **0–5 的相关度**，不是引用量。显示值优先用 LLM 分；没有则用规则分。

**规则分（先筛）**

- 命中 Exclude → 0 分，丢掉。
- Topics 与 Include **都为空** → 每篇先给 3 分。
- 一个 Include/Topic 都没命中 → 0 分，丢掉。
- 有命中 → `min(5, 2 + 不同关键词个数)`（1 个词 3 分，2 个词 4 分，3 个及以上 5 分）。
- 规则分 **低于 2** 的不进入后续步骤。

**LLM 分（再打）**

有 API Key 时，规则分过关的前 **30** 篇交给模型，按 Topics 再给 0–5 整数。超过 30 篇或 LLM 失败时退回规则分。LLM 分 **低于 3** 的不显示。

**建议**

| 分 | 建议 |
|---|---|
| ≥ 4 | 精读 |
| ≥ 3 | 扫摘要 |
| 更低 | 忽略 |

结果按最终分从高到低排列。

## 语言与翻译

选择中文且已填 API Key 时，插件会把标题、摘要、一句话、要点译成简体中文。LLM 漏译或失败时会再补译一轮。没有 API Key 时卡片保持原文。

## 数据位置

已见过的条目 GUID 与最近一次扫描结果：Zotero 数据目录下的 `rss-digest-state.json`（常见为 `~/Zotero/rss-digest-state.json`）。

## 开发说明

插件清单必须包含 `applications.zotero.id`、`update_url`、`strict_min_version`、`strict_max_version`（`10.0.*`），否则 Zotero 10 会拒绝安装。

不要调用 `Zotero.ftl.addResourceIds`，也不要 `PreferencePanes.register`：二者都会破坏 Zotero 自带设置页。

面板是盖在主窗口上的 HTML，而不是独立 chrome 窗口。控件使用 `textarea` 和可点击的 `div`（XUL 主窗口里 HTML `input`/`button` 往往点不到）。

## 自动更新

Zotero 自己检查更新，插件里不用再写一套更新逻辑。

1. 已安装的 XPI 里带有 `manifest.json` → `applications.zotero.update_url`，指向仓库里的 [`plugin/updates.json`](plugin/updates.json)。
2. Zotero 会定期（也可在 **工具 → 插件 → 齿轮 → Check for Updates**）拉取该 JSON。
3. 若 JSON 里的 `version` 比本机高，且 `update_hash`（XPI 的 SHA-256）匹配，就下载 `update_link` 并安装。

发布新版本：

1. 改 `plugin/manifest.json` 的 `version`（以及 README 里的版本号）。
2. 在仓库根目录运行 `python3 plugin/package_xpi.py`。脚本会写出 `dist/rss-digest.xpi`、`dist/rss-digest-<version>.xpi`，并写入带 `update_hash` 的 `plugin/updates.json`。
3. 把 `plugin/manifest.json`、`plugin/updates.json`、`dist/*.xpi` 提交并 **push 到 `main`**。`update_url` 读的是 GitHub 上的文件，不 push 就不会更新。

已安装 **0.2.17 及以后** 的用户会自动收到后续版本。更早手动装的包如果 `update_url` 还指向旧仓库，需要重新安装一次当前 XPI。

## 可选：Python CLI

仓库里仍有离线命令行 `zotero-rss`，适合不装插件、只出 Markdown 简报的场景。它通过复制 `zotero.sqlite` 读 Feeds（Local API 不暴露订阅）。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
zotero-rss probe
zotero-rss run --no-llm --no-enrich
```

配置见 `config/config.yaml` 与 `config/research_profile.yaml`。
